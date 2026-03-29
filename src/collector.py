"""
Модуль для сбора вакансий с HH.ru (ETL Extract).

Содержит класс VacancyCollector, который:
- Использует HHAPIClient для поиска вакансий
- Перебирает страницы результатов (пагинация)
- Сохраняет сырые данные в JSON
- Фильтрует по ключевым словам и дате публикации

Важно: Сбор большого количества вакансий может занять время.
Всегда соблюдайте лимиты API HH.ru (не более 1 запроса в секунду).
"""

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Set

from src.api_client import HHAPIClient
from src.config import settings, config_loader
from src.utils import get_logger

# Инициализируем логгер для модуля
logger = get_logger(__name__)


class VacancyCollector:
    """
    Сборщик вакансий с HH.ru.

    Реализует логику поэтапного сбора данных:
    1. Поиск по каждому ключевому слову из конфига
    2. Перебор страниц результатов (до max_pages)
    3. Фильтрация по дате публикации
    4. Сохранение сырых данных в JSON

    Атрибуты:
        client (HHAPIClient): Клиент для работы с API
        output_dir (Path): Директория для сохранения данных
        max_pages (int): Максимальное количество страниц для сбора
        days_back (int): За сколько дней собирать вакансии

    Пример использования:
        >>> collector = VacancyCollector()
        >>> collector.collect_all()  # Сбор по всем запросам из конфига
        >>> stats = collector.get_statistics()
        >>> print(f"Собрано вакансий: {stats['total']}")
    """

    def __init__(
        self,
        client: Optional[HHAPIClient] = None,
        output_dir: Optional[Path] = None,
        max_pages: Optional[int] = None,
        days_back: Optional[int] = None
    ) -> None:
        """
        Инициализация сборщика.

        Args:
            client: Готовый HHAPIClient. Если None, создаётся новый
            output_dir: Директория для сохранения. Если None, берётся из конфига
            max_pages: Максимум страниц для сбора. Если None, берётся из конфига
            days_back: За сколько дней собирать. Если None, берётся из конфига
        """
        # Создаём или используем готовый клиент
        self.client = client or HHAPIClient()

        # Директория для сохранения сырых данных
        self.output_dir = output_dir or settings.raw_data_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Параметры сбора из конфига или параметров
        self.max_pages = max_pages or settings.max_pages
        self.days_back = days_back or settings.days_back

        # Вычисляем дату отсечки — вакансии старше не собираем
        self.cutoff_date = datetime.now() - timedelta(days=self.days_back)

        # Статистика сбора
        self._stats: Dict[str, Any] = {
            "total_vacancies": 0,
            "unique_vacancies": 0,
            "pages_processed": 0,
            "errors": 0,
            "by_keyword": {}
        }

        # Множество ID уже собранных вакансий (для избежания дубликатов)
        self._seen_ids: Set[str] = set()

        logger.info(
            f"VacancyCollector инициализирован. "
            f"max_pages={self.max_pages}, days_back={self.days_back}"
        )

    def _save_to_json(self, data: List[Dict[str, Any]], filename: str) -> Path:
        """
        Сохранение данных в JSON файл.

        Args:
            data: Список словарей с данными вакансий
            filename: Имя файла (без расширения)

        Returns:
            Полный путь к сохранённому файлу

        Note:
            Файл сохраняется в директории data/raw/
            Имя файла включает timestamp для уникальности
        """
        # Формируем имя файла с датой и временем
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"{filename}_{timestamp}.json"

        # Сохраняем с красивым форматированием (indent=2)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Данные сохранены в {filepath}")
        return filepath

    def _is_vacancy_fresh(self, vacancy: Dict[str, Any]) -> bool:
        """
        Проверка даты публикации вакансии.

        Args:
            vacancy: Словарь с данными вакансии из API

        Returns:
            True, если вакансия опубликована за последние days_back дней

        Note:
            HH.ru возвращает поле 'published_at' в формате ISO 8601
            Пример: "2024-01-15T10:30:00+0300"
        """
        published_at = vacancy.get("published_at")

        if not published_at:
            # Если даты нет, считаем вакансию свежей (не фильтруем)
            return True

        try:
            # Парсим дату публикации
            # Формат ISO 8601 с часовым поясом
            pub_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))

            # Приводим cutoff_date к timezone-aware для корректного сравнения
            cutoff_aware = self.cutoff_date.replace(tzinfo=timezone.utc)

            # Сравниваем с датой отсечки
            return pub_date >= cutoff_aware

        except (ValueError, TypeError) as e:
            # Если не удалось распарсить дату, не фильтруем вакансию
            logger.warning(f"Не удалось распарсить дату {published_at}: {e}")
            return True

    def _collect_by_keyword(
        self,
        keyword: str,
        delay_between_pages: float = 1.0
    ) -> List[Dict[str, Any]]:
        """
        Сбор вакансий по одному ключевому слову.

        Args:
            keyword: Ключевое слово для поиска
            delay_between_pages: Задержка между страницами в секундах

        Returns:
            Список словарей с данными вакансий

        Note:
            ДЕТАЛЬНЫЙ ПАРСИНГ ТОЛЬКО ПЕРВЫХ 2 СТРАНИЦ (200 вакансий)
            Остальные страницы - базовая информация (для скорости)
        """
        logger.info(f"Начало сбора по запросу: '{keyword}'")

        all_vacancies: List[Dict[str, Any]] = []
        keyword_stats = {"found": 0, "fresh": 0, "pages": 0}
        
        # Детальный парсинг только первых 2 страниц
        DETAILED_PAGES = 2

        # Перебираем страницы
        for page in range(self.max_pages):
            # Проверяем флаг остановки
            if hasattr(self, 'stop_requested') and self.stop_requested:
                logger.info(f"Сбор остановлен пользователем на странице {page}")
                break
            
            logger.debug(f"Запрос страницы {page + 1}/{self.max_pages}")

            # Запрашиваем страницу вакансий
            response = self.client.search_vacancies(
                keyword=keyword,
                page=page,
                per_page=100
            )

            if response is None:
                logger.warning(f"Пустой ответ для страницы {page}")
                self._stats["errors"] += 1
                continue

            # Обновляем статистику
            keyword_stats["pages"] += 1
            self._stats["pages_processed"] += 1

            items = response.get("items", [])

            # Если вакансий нет — прекращаем перебор страниц
            if not items:
                logger.info(f"Вакансии закончились на странице {page}")
                break

            logger.info(f"Получено {len(items)} вакансий со страницы {page}")

            # Обрабатываем каждую вакансию
            for vacancy in items:
                vacancy_id = vacancy.get("id")

                # Пропускаем дубликаты
                if vacancy_id in self._seen_ids:
                    continue

                # Проверяем дату публикации
                if not self._is_vacancy_fresh(vacancy):
                    logger.info(
                        f"Вакансия {vacancy_id} старше {self.days_back} дней. "
                        f"Прекращаю сбор по запросу '{keyword}'"
                    )
                    break

                # ДЕТАЛЬНЫЙ ПАРСИНГ ТОЛЬКО ДЛЯ ПЕРВЫХ 2 СТРАНИЦ
                if page < DETAILED_PAGES:
                    logger.debug(f"Запрос деталей вакансии {vacancy_id} (страница {page})")
                    vacancy_details = self.client.get_vacancy_details(vacancy_id)
                    
                    if vacancy_details:
                        merged_vacancy = {**vacancy, **vacancy_details}
                        self._seen_ids.add(vacancy_id)
                        all_vacancies.append(merged_vacancy)
                        keyword_stats["fresh"] += 1
                        logger.info(f"Получены детали вакансии {vacancy_id}")
                    else:
                        logger.warning(f"Не удалось получить детали вакансии {vacancy_id}")
                        self._seen_ids.add(vacancy_id)
                        all_vacancies.append(vacancy)
                        keyword_stats["fresh"] += 1

                    # Задержка между запросами деталей
                    time.sleep(self.client.delay)
                else:
                    # БАЗОВЫЙ ПАРСИНГ (без деталей) - быстро
                    self._seen_ids.add(vacancy_id)
                    all_vacancies.append(vacancy)
                    keyword_stats["fresh"] += 1

            # Проверяем, не закончились ли вакансии
            if len(items) < 100:
                logger.info("Последняя страница (меньше 100 вакансий)")
                break

            # Задержка между страницами
            time.sleep(delay_between_pages)

        # Сохраняем статистику
        self._stats["by_keyword"][keyword] = keyword_stats
        self._stats["total_vacancies"] += len(all_vacancies)

        logger.info(
            f"Завершён сбор по запросу '{keyword}': "
            f"{len(all_vacancies)} вакансий за {keyword_stats['pages']} страниц"
        )

        return all_vacancies

    def collect_all(
        self,
        keywords: Optional[List[str]] = None,
        save_raw: bool = True
    ) -> Dict[str, Any]:
        """
        Сбор вакансий по всем ключевым словам.

        Args:
            keywords: Список ключевых слов. Если None, берётся из конфига
            save_raw: Сохранять ли сырые данные в JSON

        Returns:
            Словарь с результатами сбора:
            {
                "total": int,              # Всего собрано
                "unique": int,             # Уникальных (без дублей)
                "by_keyword": Dict,        # Статистика по запросам
                "files": List[str]         # Сохранённые файлы
            }

        Note:
            Метод последовательно перебирает все ключевые слова.
            Дубликаты автоматически удаляются по ID вакансии.
        """
        # Берём ключевые слова из конфига или параметра
        if keywords is None:
            keywords = config_loader.search_queries

        logger.info(f"Начало сбора вакансий. Запросов: {len(keywords)}")
        logger.info(f"Запросы: {', '.join(keywords)}")

        all_vacancies: List[Dict[str, Any]] = []
        saved_files: List[str] = []

        # Последовательно собираем по каждому запросу
        for i, keyword in enumerate(keywords, 1):
            logger.info(f"Запрос {i}/{len(keywords)}: {keyword}")

            vacancies = self._collect_by_keyword(keyword)
            all_vacancies.extend(vacancies)

            # Сохраняем промежуточные результаты для каждого запроса
            if save_raw and vacancies:
                # Очищаем имя файла от спецсимволов
                safe_name = keyword.replace(" ", "_").replace("+", "plus")
                filepath = self._save_to_json(vacancies, f"vacancies_{safe_name}")
                saved_files.append(str(filepath))

            # Небольшая задержка между запросами (дополнительная защита)
            if i < len(keywords):
                time.sleep(2.0)

        # Удаляем дубликаты окончательно (на случай пересечений)
        unique_vacancies = self._deduplicate_vacancies(all_vacancies)

        # Сохраняем общий файл со всеми вакансиями
        if save_raw and unique_vacancies:
            filepath = self._save_to_json(unique_vacancies, "all_vacancies")
            saved_files.append(str(filepath))

        # Сохраняем в БД с удалением дубликатов
        if unique_vacancies:
            self._save_to_database(unique_vacancies)

        # Обновляем финальную статистику
        self._stats["unique_vacancies"] = len(unique_vacancies)

        logger.info(
            f"Сбор завершён. "
            f"Всего: {self._stats['total_vacancies']}, "
            f"Уникальных: {self._stats['unique_vacancies']}"
        )

        return {
            "total": self._stats["total_vacancies"],
            "unique": self._stats["unique_vacancies"],
            "by_keyword": self._stats["by_keyword"],
            "files": saved_files
        }

    def _save_to_database(self, vacancies: List[Dict[str, Any]]) -> None:
        """
        Сохранение вакансий в БД с СИСТЕМНЫМ извлечением навыков.

        Args:
            vacancies: Список вакансий для сохранения
        """
        from src.storage import VacancyStorage
        import pandas as pd
        import re
        from src.config import config_loader

        logger.info(f"Сохранение {len(vacancies)} вакансий в БД...")

        storage = VacancyStorage()
        try:
            # Загружаем словари навыков для поиска
            hard_skills = [s.lower().strip() for s in config_loader.hard_skills if len(s.strip()) > 2]
            soft_skills = [s.lower().strip() for s in config_loader.soft_skills if len(s.strip()) > 2]
            tools = [s.lower().strip() for s in config_loader.tools if len(s.strip()) > 2]

            # Исключаем слишком короткие и общие навыки
            excluded_skills = {'r', 'c', 'i', 'a', 's', 't', 'e', 'k', 'm', 'n', 'o', 'p', 'q', 'u', 'v', 'w', 'x', 'y', 'z'}
            hard_skills = [s for s in hard_skills if s not in excluded_skills]
            soft_skills = [s for s in soft_skills if s not in excluded_skills]
            tools = [s for s in tools if s not in excluded_skills]

            logger.info(f"Загружено словарей: Hard={len(hard_skills)}, Soft={len(soft_skills)}, Tools={len(tools)}")

            # Нормализуем данные для БД
            normalized_vacancies = []
            for vacancy in vacancies:
                # Извлекаем простые значения из вложенных структур
                area = vacancy.get("area", {})
                employer = vacancy.get("employer", {})
                salary = vacancy.get("salary", {})
                experience = vacancy.get("experience", {})
                employment = vacancy.get("employment", {})
                schedule = vacancy.get("schedule", {})

                # Правильное извлечение валюты
                currency = salary.get("currency", "RUR") if salary else "RUR"
                # Маппинг валют HH.ru
                currency_map = {
                    "RUR": "RUB",  # Российский рубль
                    "KZT": "KZT",  # Казахстанский тенге
                    "UZS": "UZS",  # Узбекский сум
                    "BYN": "BYN",  # Белорусский рубль
                    "USD": "USD",  # Доллар
                    "EUR": "EUR",  # Евро
                }
                currency = currency_map.get(currency, currency)

                # Извлекаем описание для поиска навыков
                # ПОЛЕ 1: snippet (требования и обязанности из поиска)
                snippet = vacancy.get("snippet", {}) or {}
                requirement = (snippet.get("requirement", "") or "").lower()
                responsibility = (snippet.get("responsibility", "") or "").lower()
                
                # ПОЛЕ 2: description (полное описание из деталей)
                description = (vacancy.get("description", "") or "").lower()
                
                # Объединяем весь текст для поиска навыков
                description_text = f"{requirement} {responsibility} {description}"
                
                # Также ищем в названии
                vacancy_name = (vacancy.get("name", "") or "").lower()
                description_text = f"{description_text} {vacancy_name}"

                # УЛУЧШЕННЫЙ ПОИСК НАВЫКОВ
                found_hard = set()
                found_soft = set()
                found_tools = set()

                # Поиск с учётом вариантов написания
                def find_skills_in_text(text, skill_list, found_set):
                    """Поиск навыков в тексте с учётом вариаций."""
                    if not text:
                        return
                    
                    for skill in skill_list:
                        # Пропускаем слишком короткие навыки
                        if len(skill) < 3:
                            continue
                        
                        # Поиск по точному совпадению (целое слово)
                        # Используем regex для поиска целых слов
                        pattern = r'\b' + re.escape(skill) + r'\b'
                        if re.search(pattern, text, re.IGNORECASE):
                            found_set.add(skill.title())
                            continue
                        
                        # Для soft skills - более либеральный поиск
                        # Ищем части навыка (для составных)
                        skill_parts = skill.split()
                        if len(skill_parts) >= 2:
                            # Ищем все части навыка в тексте
                            parts_found = []
                            for part in skill_parts:
                                if len(part) > 2:  # Пропускаем короткие части
                                    part_pattern = r'\b' + re.escape(part) + r'\b'
                                    if re.search(part_pattern, text, re.IGNORECASE):
                                        parts_found.append(part)
                            
                            # Если найдено большинство частей (минимум 2)
                            if len(parts_found) >= 2:
                                found_set.add(skill.title())
                        
                        # Поиск с вариациями написания
                        skill_variants = [
                            skill,
                            skill.replace('+', ' plus').replace('.', ''),
                            skill.replace('-', ' ').replace('.', ''),
                            skill.replace('_', ' '),
                        ]
                        for variant in skill_variants:
                            if len(variant) > 2:
                                variant_pattern = r'\b' + re.escape(variant) + r'\b'
                                if re.search(variant_pattern, text, re.IGNORECASE):
                                    found_set.add(skill.title())
                                    break
                
                # Ищем во всём описании (требования + обязанности)
                find_skills_in_text(description_text, hard_skills, found_hard)
                find_skills_in_text(description_text, soft_skills, found_soft)
                find_skills_in_text(description_text, tools, found_tools)

                # Дополнительно ищем в названии вакансии
                vacancy_name = vacancy.get("name", "").lower()
                find_skills_in_text(vacancy_name, hard_skills, found_hard)
                find_skills_in_text(vacancy_name, tools, found_tools)
                
                # Для soft skills также ищем в описании компании и условиях
                company_description = str(vacancy.get("employer", {})).lower()
                find_skills_in_text(company_description, soft_skills, found_soft)

                # Конвертируем в списки и сортируем
                hard_skills_list = sorted(list(found_hard))
                soft_skills_list = sorted(list(found_soft))
                tools_list = sorted(list(found_tools))

                normalized = {
                    "id": vacancy.get("id"),
                    "vacancy_id": vacancy.get("id"),
                    "vacancy_name": vacancy.get("name", ""),
                    "published_at": vacancy.get("published_at"),
                    "salary_from": salary.get("from") if salary else None,
                    "salary_to": salary.get("to") if salary else None,
                    "salary_currency": currency,
                    "employer_name": employer.get("name", "") if employer else "",
                    "employer_id": employer.get("id", "") if employer else "",
                    "employer_url": employer.get("url", "") if employer else "",
                    "vacancy_url": vacancy.get("alternate_url", ""),
                    "experience": experience.get("name", "") if experience else "",
                    "employment": employment.get("name", "") if employment else "",
                    "schedule": schedule.get("name", "") if schedule else "",
                    "area": area.get("name", "") if area else "",
                    # Улучшенные навыки из описания
                    "all_skills": ", ".join(hard_skills_list + soft_skills_list + tools_list),
                    "hard_skills": ", ".join(hard_skills_list),
                    "soft_skills": ", ".join(soft_skills_list),
                    "tools": ", ".join(tools_list),
                    "skill_count": len(hard_skills_list) + len(soft_skills_list) + len(tools_list),
                    "hard_skill_count": len(hard_skills_list),
                    "soft_skill_count": len(soft_skills_list),
                    "tools_count": len(tools_list),
                }
                normalized_vacancies.append(normalized)

            # Создаем DataFrame
            df = pd.DataFrame(normalized_vacancies)

            # Получаем существующие ID
            existing_df = storage.get_all_vacancies()
            existing_ids = set(existing_df["vacancy_id"].tolist()) if not existing_df.empty else set()

            # Фильтруем только новые вакансии (для избежания дубликатов)
            new_df = df[~df["vacancy_id"].isin(existing_ids)]

            if not new_df.empty:
                storage.save_dataframe(new_df)
                logger.info(f"БД обновлена: {len(new_df)} новых записей добавлено")
                
                # Статистика по навыкам
                total_skills = sum(new_df['skill_count'])
                avg_skills = total_skills / len(new_df) if len(new_df) > 0 else 0
                max_skills = max(new_df['skill_count']) if len(new_df) > 0 else 0
                
                logger.info(f"Всего найдено навыков: {total_skills}")
                logger.info(f"Среднее: {avg_skills:.1f}, Максимум: {max_skills} на вакансию")
                
                # Топ-10 навыков
                all_skills_combined = []
                for skills_str in new_df['hard_skills'].dropna():
                    if skills_str:
                        all_skills_combined.extend([s.strip() for s in skills_str.split(',')])
                
                if all_skills_combined:
                    from collections import Counter
                    skill_counts = Counter(all_skills_combined)
                    top_10 = skill_counts.most_common(10)
                    logger.info(f"Топ-10 навыков: {top_10}")
            else:
                logger.info("Новых вакансий для добавления нет")

        except Exception as e:
            logger.error(f"Ошибка сохранения в БД: {e}")
        finally:
            storage.close()

    def _deduplicate_vacancies(
        self,
        vacancies: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Удаление дубликатов вакансий по ID.

        Args:
            vacancies: Список вакансий (возможно с дублями)

        Returns:
            Список уникальных вакансий

        Note:
            Используем OrderedDict-подобную логику через dict для сохранения порядка
        """
        seen: Dict[str, Dict[str, Any]] = {}

        for vacancy in vacancies:
            vacancy_id = vacancy.get("id")
            if vacancy_id and vacancy_id not in seen:
                seen[vacancy_id] = vacancy

        return list(seen.values())

    def get_statistics(self) -> Dict[str, Any]:
        """
        Получение статистики сбора.

        Returns:
            Словарь со статистикой:
            - total_vacancies: всего собрано
            - unique_vacancies: уникальных
            - pages_processed: обработано страниц
            - errors: количество ошибок
            - by_keyword: детализация по запросам
        """
        return self._stats.copy()

    def close(self) -> None:
        """Закрытие клиента и освобождение ресурсов."""
        if self.client:
            self.client.close()


# =============================================================================
# Блок для тестирования модуля
# =============================================================================

if __name__ == "__main__":
    """
    Пример использования VacancyCollector для тестирования.

    Перед запуском убедитесь:
    1. Настроен .env (HH_USER_EMAIL)
    2. Существует config.yaml с search_queries
    3. Готовы ждать — сбор может занять несколько минут

    Запуск: python -m src.collector
    """

    import logging
    logging.getLogger("src").setLevel(logging.INFO)

    print("=" * 60)
    print("Тестирование VacancyCollector")
    print("=" * 60)

    # Создаём сборщик с уменьшенными лимитами для быстрого теста
    collector = VacancyCollector(
        max_pages=2,  # Только 2 страницы для теста
        days_back=7   # Только за последнюю неделю
    )

    try:
        # Собираем по тестовым запросам (мало запросов для скорости)
        test_keywords = ["Python developer", "Data Scientist"]

        print(f"\n📥 Сбор вакансий по запросам: {', '.join(test_keywords)}")
        print("-" * 60)

        result = collector.collect_all(
            keywords=test_keywords,
            save_raw=True
        )

        # Выводим результаты
        print("\n" + "=" * 60)
        print("📊 Результаты сбора")
        print("=" * 60)
        print(f"✅ Всего собрано: {result['total']}")
        print(f"✅ Уникальных: {result['unique']}")
        print(f"📁 Сохранено файлов: {len(result['files'])}")

        # Детализация по запросам
        print("\n📈 По запросам:")
        for keyword, stats in result['by_keyword'].items():
            print(f"  • {keyword}: {stats['fresh']} вакансий ({stats['pages']} страниц)")

        # Список файлов
        print("\n💾 Сохранённые файлы:")
        for filepath in result['files']:
            print(f"  📄 {filepath}")

    except KeyboardInterrupt:
        print("\n\n⚠️ Сбор прерван пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {type(e).__name__} - {e}")
        logger.exception("Детальная информация об ошибке")
    finally:
        collector.close()
        print("\n" + "=" * 60)
        print("Тестирование завершено!")
        print("=" * 60)
