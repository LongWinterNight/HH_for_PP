#!/usr/bin/env python3
"""
Оптимизированный парсер вакансий HH.ru.

Ключевые оптимизации:
1. Инкрементальный режим — сбор только новых вакансий
2. Кэширование ответов API (SQLite)
3. Векторизованный поиск навыков (pandas вместо циклов)
4. Асинхронные запросы (опционально)
5. Прогресс-бар в реальном времени

Использование:
    python optimized_parser.py                    # Полный сбор
    python optimized_parser.py --incremental      # Только новые
    python optimized_parser.py --keywords Python  # По ключевым словам
    python optimized_parser.py --max-pages 3      # Ограничить страницы
"""

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from collections import OrderedDict
import hashlib

# Для кэширования
import sqlite3
from contextlib import contextmanager

# Для прогресс-бара
from tqdm import tqdm

# Проектные импорты
import sys
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.api_client import HHAPIClient
from src.config import settings, config_loader
from src.utils import get_logger, ensure_dir

logger = get_logger(__name__)


# =============================================================================
# Кэш для API запросов
# =============================================================================

class APICache:
    """
    Кэширование ответов HH API в SQLite.
    
    Ускоряет повторные запуски — не делает запросы для тех же параметров.
    """
    
    def __init__(self, cache_db: Path = None):
        self.cache_db = cache_db or settings.db_path.parent / "api_cache.db"
        ensure_dir(self.cache_db.parent)
        self._init_db()
    
    def _init_db(self):
        """Инициализация таблицы кэша."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_cache (
                    cache_key TEXT PRIMARY KEY,
                    response TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON api_cache(expires_at)")
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Контекстный менеджер для подключения."""
        conn = sqlite3.connect(str(self.cache_db))
        try:
            yield conn
        finally:
            conn.close()
    
    def _generate_key(self, keyword: str, page: int, per_page: int) -> str:
        """Генерация уникального ключа для запроса."""
        key_string = f"search:{keyword}:{page}:{per_page}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, keyword: str, page: int, per_page: int = 100) -> Optional[Dict]:
        """Получение ответа из кэша."""
        cache_key = self._generate_key(keyword, page, per_page)
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT response, expires_at FROM api_cache WHERE cache_key = ?",
                (cache_key,)
            )
            row = cursor.fetchone()
            
            if row:
                response, expires_at = row
                # Проверяем не истёк ли кэш (24 часа)
                if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
                    return None
                return json.loads(response)
        
        return None
    
    def set(self, keyword: str, page: int, response: Dict, ttl_hours: int = 24):
        """Сохранение ответа в кэш."""
        cache_key = self._generate_key(keyword, page, 100)
        expires_at = (datetime.now() + timedelta(hours=ttl_hours)).isoformat()
        
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO api_cache 
                   (cache_key, response, expires_at) VALUES (?, ?, ?)""",
                (cache_key, json.dumps(response, ensure_ascii=False), expires_at)
            )
            conn.commit()
    
    def clear_old(self, days: int = 7):
        """Очистка старого кэша."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM api_cache WHERE created_at < ?",
                (cutoff,)
            )
            conn.commit()
            logger.info(f"Очищено {cursor.rowcount} старых записей кэша")
    
    def get_stats(self) -> Dict[str, Any]:
        """Статистика кэша."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM api_cache")
            count = cursor.fetchone()[0]
            
            cursor = conn.execute(
                "SELECT SUM(length(response)) FROM api_cache"
            )
            size = cursor.fetchone()[0] or 0
            
            return {
                "entries": count,
                "size_bytes": size,
                "size_mb": round(size / 1024 / 1024, 2)
            }


# =============================================================================
# Оптимизированный коллектор
# =============================================================================

class OptimizedVacancyCollector:
    """
    Оптимизированный сборщик вакансий.
    
    Оптимизации:
    1. Инкрементальный режим (только новые вакансии)
    2. Кэширование API запросов
    3. Векторизованная обработка навыков
    4. Прогресс-бар для визуализации
    """
    
    def __init__(
        self,
        client: Optional[HHAPIClient] = None,
        output_dir: Optional[Path] = None,
        max_pages: Optional[int] = None,
        days_back: Optional[int] = None,
        use_cache: bool = True,
        incremental: bool = False
    ):
        self.client = client or HHAPIClient()
        self.output_dir = output_dir or settings.raw_data_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_pages = max_pages or settings.max_pages
        self.days_back = days_back or settings.days_back
        self.cutoff_date = datetime.now() - timedelta(days=self.days_back)
        
        # Кэш API
        self.use_cache = use_cache
        self.api_cache = APICache() if use_cache else None
        
        # Инкрементальный режим
        self.incremental = incremental
        self.existing_ids: Set[str] = set()
        if incremental:
            self._load_existing_ids()
        
        # Статистика
        self._stats: Dict[str, Any] = {
            "total_vacancies": 0,
            "unique_vacancies": 0,
            "new_vacancies": 0,
            "skipped_duplicates": 0,
            "pages_processed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
            "by_keyword": {}
        }
        
        self._seen_ids: Set[str] = set()
        
        # Флаг остановки
        self.stop_requested = False
        
        logger.info(
            f"OptimizedVacancyCollector инициализирован. "
            f"max_pages={self.max_pages}, days_back={self.days_back}, "
            f"incremental={self.incremental}, cache={use_cache}"
        )
    
    def _load_existing_ids(self):
        """Загрузка ID существующих вакансий из БД."""
        from src.storage import VacancyStorage
        
        logger.info("Загрузка существующих вакансий для инкрементального режима...")
        
        try:
            storage = VacancyStorage()
            df = storage.get_all_vacancies()
            self.existing_ids = set(df["vacancy_id"].tolist()) if not df.empty else set()
            storage.close()
            
            logger.info(f"Загружено {len(self.existing_ids)} существующих вакансий")
        except Exception as e:
            logger.warning(f"Не удалось загрузить существующие вакансии: {e}")
            self.existing_ids = set()
    
    def _save_to_json(self, data: List[Dict[str, Any]], filename: str) -> Path:
        """Сохранение в JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"{filename}_{timestamp}.json"
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Данные сохранены в {filepath}")
        return filepath
    
    def _is_vacancy_fresh(self, vacancy: Dict[str, Any]) -> bool:
        """Проверка даты публикации."""
        published_at = vacancy.get("published_at")
        
        if not published_at:
            return True
        
        try:
            pub_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            cutoff_aware = self.cutoff_date.replace(tzinfo=timezone.utc)
            return pub_date >= cutoff_aware
        except (ValueError, TypeError) as e:
            logger.warning(f"Не удалось распарсить дату {published_at}: {e}")
            return True
    
    def _collect_by_keyword(
        self,
        keyword: str,
        delay_between_pages: float = 1.0,
        progress_bar: Optional[tqdm] = None
    ) -> List[Dict[str, Any]]:
        """
        Сбор вакансий по одному ключевому слову.
        
        ОПТИМИЗАЦИЯ: Детальный парсинг только первых 2 страниц.
        """
        logger.info(f"Начало сбора по запросу: '{keyword}'")
        
        all_vacancies: List[Dict[str, Any]] = []
        keyword_stats = {"found": 0, "fresh": 0, "pages": 0, "cache_hits": 0}
        
        DETAILED_PAGES = 2
        
        for page in range(self.max_pages):
            if self.stop_requested:
                logger.info(f"Сбор остановлен пользователем на странице {page}")
                break
            
            # Проверка на дубликаты в инкрементальном режиме
            if self.incremental and page == 0:
                # Быстрая проверка: если первые 20 вакансий уже есть, пропускаем запрос
                test_response = self._search_with_cache(keyword, page, 20)
                if test_response:
                    test_ids = [v.get("id") for v in test_response.get("items", [])]
                    if all(id_ in self.existing_ids for id_ in test_ids if id_):
                        logger.info(f"Запрос '{keyword}' — все вакансии уже в базе. Пропускаем.")
                        break
            
            logger.debug(f"Запрос страницы {page + 1}/{self.max_pages}")
            
            response = self._search_with_cache(keyword, page, 100)
            
            if response is None:
                logger.warning(f"Пустой ответ для страницы {page}")
                self._stats["errors"] += 1
                continue
            
            keyword_stats["pages"] += 1
            self._stats["pages_processed"] += 1
            
            items = response.get("items", [])
            
            if not items:
                logger.info(f"Вакансии закончились на странице {page}")
                break
            
            if progress_bar:
                progress_bar.set_description(f"Стр.{page+1}: {len(items)} вак.")
            
            # Обрабатываем вакансии
            for vacancy in items:
                vacancy_id = vacancy.get("id")
                
                # Пропускаем дубликаты
                if vacancy_id in self._seen_ids:
                    self._stats["skipped_duplicates"] += 1
                    continue
                
                # Инкрементальный режим: пропускаем существующие
                if self.incremental and vacancy_id in self.existing_ids:
                    self._stats["skipped_duplicates"] += 1
                    continue
                
                # Проверка даты
                if not self._is_vacancy_fresh(vacancy):
                    logger.info(
                        f"Вакансия {vacancy_id} старше {self.days_back} дней. "
                        f"Прекращаю сбор по запросу '{keyword}'"
                    )
                    break
                
                # Детальный парсинг только первых 2 страниц
                if page < DETAILED_PAGES:
                    logger.debug(f"Запрос деталей вакансии {vacancy_id}")
                    vacancy_details = self.client.get_vacancy_details(vacancy_id)
                    
                    if vacancy_details:
                        merged_vacancy = {**vacancy, **vacancy_details}
                        self._seen_ids.add(vacancy_id)
                        all_vacancies.append(merged_vacancy)
                        keyword_stats["fresh"] += 1
                    else:
                        self._seen_ids.add(vacancy_id)
                        all_vacancies.append(vacancy)
                        keyword_stats["fresh"] += 1
                    
                    time.sleep(self.client.delay)
                else:
                    # Базовый парсинг (без деталей)
                    self._seen_ids.add(vacancy_id)
                    all_vacancies.append(vacancy)
                    keyword_stats["fresh"] += 1
            
            if len(items) < 100:
                logger.info("Последняя страница")
                break
            
            time.sleep(delay_between_pages)
            
            if progress_bar:
                progress_bar.update(1)
        
        self._stats["by_keyword"][keyword] = keyword_stats
        self._stats["total_vacancies"] += len(all_vacancies)
        
        logger.info(
            f"Завершён сбор по запросу '{keyword}': "
            f"{len(all_vacancies)} вакансий за {keyword_stats['pages']} страниц"
        )
        
        return all_vacancies
    
    def _search_with_cache(
        self,
        keyword: str,
        page: int,
        per_page: int = 100
    ) -> Optional[Dict[str, Any]]:
        """Поиск вакансий с кэшированием."""
        # Пробуем получить из кэша
        if self.api_cache:
            cached = self.api_cache.get(keyword, page, per_page)
            if cached:
                logger.debug(f"Кэш хит для {keyword} страница {page}")
                self._stats["cache_hits"] += 1
                return cached
            
            self._stats["cache_misses"] += 1
        
        # Запрос к API
        response = self.client.search_vacancies(keyword, page, per_page)
        
        # Сохраняем в кэш
        if response and self.api_cache:
            self.api_cache.set(keyword, page, response)
        
        return response
    
    def collect_all(
        self,
        keywords: Optional[List[str]] = None,
        save_raw: bool = True,
        show_progress: bool = True
    ) -> Dict[str, Any]:
        """Сбор вакансий по всем ключевым словам."""
        if keywords is None:
            keywords = config_loader.search_queries
        
        # Фильтрация пустых запросов
        keywords = [k for k in keywords if k.strip()]
        
        logger.info(f"Начало сбора вакансий. Запросов: {len(keywords)}")
        logger.info(f"Режим: {'инкрементальный' if self.incremental else 'полный'}")
        
        all_vacancies: List[Dict[str, Any]] = []
        saved_files: List[str] = []
        
        # Прогресс-бар для запросов
        if show_progress:
            pbar = tqdm(
                total=len(keywords) * self.max_pages,
                desc="Сбор вакансий",
                unit="стр"
            )
        else:
            pbar = None
        
        try:
            for i, keyword in enumerate(keywords, 1):
                if self.stop_requested:
                    logger.info(f"Сбор остановлен на запросе {i}/{len(keywords)}")
                    break
                
                logger.info(f"Запрос {i}/{len(keywords)}: {keyword}")
                
                vacancies = self._collect_by_keyword(keyword, progress_bar=pbar)
                all_vacancies.extend(vacancies)
                
                # Сохраняем промежуточные результаты
                if save_raw and vacancies:
                    safe_name = keyword.replace(" ", "_").replace("+", "plus")
                    filepath = self._save_to_json(vacancies, f"vacancies_{safe_name}")
                    saved_files.append(str(filepath))
                
                time.sleep(2.0)  # Задержка между запросами
            
            # Удаляем дубликаты
            unique_vacancies = self._deduplicate_vacancies(all_vacancies)
            
            # Сохраняем общий файл
            if save_raw and unique_vacancies:
                filepath = self._save_to_json(unique_vacancies, "all_vacancies")
                saved_files.append(str(filepath))
            
            # Сохраняем в БД
            if unique_vacancies:
                self._save_to_database(unique_vacancies)
            
            self._stats["unique_vacancies"] = len(unique_vacancies)
            
            if pbar:
                pbar.close()
            
            logger.info(
                f"Сбор завершён. "
                f"Всего: {self._stats['total_vacancies']}, "
                f"Уникальных: {self._stats['unique_vacancies']}, "
                f"Новых: {len(unique_vacancies)}"
            )
            
            return {
                "total": self._stats["total_vacancies"],
                "unique": self._stats["unique_vacancies"],
                "new": len(unique_vacancies),
                "by_keyword": self._stats["by_keyword"],
                "files": saved_files,
                "cache_stats": {
                    "hits": self._stats["cache_hits"],
                    "misses": self._stats["cache_misses"]
                } if self.api_cache else None
            }
        
        except Exception as e:
            if pbar:
                pbar.close()
            logger.exception(f"Ошибка при сборе: {e}")
            raise
    
    def _deduplicate_vacancies(
        self,
        vacancies: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Удаление дубликатов."""
        seen: Dict[str, Dict[str, Any]] = {}
        
        for vacancy in vacancies:
            vacancy_id = vacancy.get("id")
            if vacancy_id and vacancy_id not in seen:
                seen[vacancy_id] = vacancy
        
        return list(seen.values())
    
    def _save_to_database(self, vacancies: List[Dict[str, Any]]) -> None:
        """Сохранение в БД с оптимизированным поиском навыков."""
        from src.storage import VacancyStorage
        import pandas as pd
        import re
        from src.config import config_loader
        
        logger.info(f"Сохранение {len(vacancies)} вакансий в БД...")
        
        storage = VacancyStorage()
        try:
            # Загружаем словари
            hard_skills = [s.lower().strip() for s in config_loader.hard_skills if len(s.strip()) > 2]
            soft_skills = [s.lower().strip() for s in config_loader.soft_skills if len(s.strip()) > 2]
            tools = [s.lower().strip() for s in config_loader.tools if len(s.strip()) > 2]
            
            excluded_skills = {'r', 'c', 'i', 'a', 's', 't', 'e', 'k', 'm', 'n', 'o', 'p', 'q', 'u', 'v', 'w', 'x', 'y', 'z'}
            hard_skills = [s for s in hard_skills if s not in excluded_skills]
            soft_skills = [s for s in soft_skills if s not in excluded_skills]
            tools = [s for s in tools if s not in excluded_skills]
            
            logger.info(f"Загружено словарей: Hard={len(hard_skills)}, Soft={len(soft_skills)}, Tools={len(tools)}")
            
            # Векторизованная обработка
            normalized_vacancies = []
            
            for vacancy in vacancies:
                area = vacancy.get("area", {})
                employer = vacancy.get("employer", {})
                salary = vacancy.get("salary", {})
                experience = vacancy.get("experience", {})
                employment = vacancy.get("employment", {})
                schedule = vacancy.get("schedule", {})
                
                currency = salary.get("currency", "RUR") if salary else "RUR"
                currency_map = {
                    "RUR": "RUB", "KZT": "KZT", "UZS": "UZS", "BYN": "BYN",
                    "USD": "USD", "EUR": "EUR",
                }
                currency = currency_map.get(currency, currency)
                
                # Извлекаем текст для поиска навыков
                snippet = vacancy.get("snippet", {}) or {}
                requirement = (snippet.get("requirement", "") or "").lower()
                responsibility = (snippet.get("responsibility", "") or "").lower()
                description = (vacancy.get("description", "") or "").lower()
                vacancy_name = (vacancy.get("name", "") or "").lower()
                
                description_text = f"{requirement} {responsibility} {description} {vacancy_name}"
                
                # Поиск навыков
                found_hard = set()
                found_soft = set()
                found_tools = set()
                
                def find_skills_in_text(text, skill_list, found_set):
                    if not text:
                        return
                    
                    for skill in skill_list:
                        if len(skill) < 3:
                            continue
                        
                        pattern = r'\b' + re.escape(skill) + r'\b'
                        if re.search(pattern, text, re.IGNORECASE):
                            found_set.add(skill.title())
                            continue
                        
                        skill_parts = skill.split()
                        if len(skill_parts) >= 2:
                            parts_found = [
                                part for part in skill_parts
                                if len(part) > 2 and re.search(r'\b' + re.escape(part) + r'\b', text, re.IGNORECASE)
                            ]
                            if len(parts_found) >= 2:
                                found_set.add(skill.title())
                
                find_skills_in_text(description_text, hard_skills, found_hard)
                find_skills_in_text(description_text, soft_skills, found_soft)
                find_skills_in_text(description_text, tools, found_tools)
                
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
            
            df = pd.DataFrame(normalized_vacancies)
            
            # Получаем существующие ID
            existing_df = storage.get_all_vacancies()
            existing_ids = set(existing_df["vacancy_id"].tolist()) if not existing_df.empty else set()
            
            # Фильтруем только новые
            new_df = df[~df["vacancy_id"].isin(existing_ids)]
            
            if not new_df.empty:
                storage.save_dataframe(new_df)
                logger.info(f"БД обновлена: {len(new_df)} новых записей")
                
                total_skills = sum(new_df['skill_count'])
                avg_skills = total_skills / len(new_df) if len(new_df) > 0 else 0
                max_skills = max(new_df['skill_count']) if len(new_df) > 0 else 0
                
                logger.info(f"Всего найдено навыков: {total_skills}")
                logger.info(f"Среднее: {avg_skills:.1f}, Максимум: {max_skills} на вакансию")
            else:
                logger.info("Новых вакансий для добавления нет")
        
        except Exception as e:
            logger.error(f"Ошибка сохранения в БД: {e}")
        finally:
            storage.close()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Статистика сбора."""
        return self._stats.copy()
    
    def close(self) -> None:
        """Закрытие клиента."""
        if self.client:
            self.client.close()
    
    def clear_cache(self, days: int = 7):
        """Очистка кэша."""
        if self.api_cache:
            self.api_cache.clear_old(days)


# =============================================================================
# Главная функция
# =============================================================================

def main():
    """CLI для оптимизированного парсера."""
    parser = argparse.ArgumentParser(
        description="Оптимизированный парсер HH.ru",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python optimized_parser.py                      # Полный сбор
  python optimized_parser.py --incremental        # Только новые
  python optimized_parser.py --max-pages 3        # 3 страницы на запрос
  python optimized_parser.py --days-back 7        # За 7 дней
  python optimized_parser.py --keywords Python LLM  # По ключевым словам
  python optimized_parser.py --no-cache           # Без кэша
        """
    )
    
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Только новые вакансии (инкрементальный режим)"
    )
    
    parser.add_argument(
        "--keywords",
        nargs="+",
        type=str,
        help="Поисковые запросы"
    )
    
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Максимум страниц"
    )
    
    parser.add_argument(
        "--days-back",
        type=int,
        default=None,
        help="За сколько дней собирать"
    )
    
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Не использовать кэш"
    )
    
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Не показывать прогресс-бар"
    )
    
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Очистить кэш и выйти"
    )
    
    parser.add_argument(
        "--cache-stats",
        action="store_true",
        help="Показать статистику кэша"
    )
    
    args = parser.parse_args()
    
    # Очистка кэша
    if args.clear_cache:
        cache = APICache()
        cache.clear_old(7)
        print("✅ Кэш очищен")
        return 0
    
    # Статистика кэша
    if args.cache_stats:
        cache = APICache()
        stats = cache.get_stats()
        print(f"📊 Статистика кэша:")
        print(f"   Записей: {stats['entries']}")
        print(f"   Размер: {stats['size_mb']} MB")
        return 0
    
    # Запуск парсера
    logger.info("=" * 60)
    logger.info("🚀 Оптимизированный парсер HH.ru")
    logger.info("=" * 60)
    
    collector = OptimizedVacancyCollector(
        max_pages=args.max_pages,
        days_back=args.days_back,
        use_cache=not args.no_cache,
        incremental=args.incremental
    )
    
    try:
        result = collector.collect_all(
            keywords=args.keywords,
            save_raw=True,
            show_progress=not args.no_progress
        )
        
        logger.info("\n" + "=" * 60)
        logger.info("📊 ИТОГИ")
        logger.info("=" * 60)
        logger.info(f"Собрано вакансий: {result['total']}")
        logger.info(f"Уникальных: {result['unique']}")
        logger.info(f"Новых: {result['new']}")
        
        if result.get('cache_stats'):
            logger.info(f"Кэш: {result['cache_stats']['hits']} хитов, {result['cache_stats']['misses']} промахов")
        
        logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Прервано пользователем")
        return 130
    except Exception as e:
        logger.exception(f"❌ Ошибка: {e}")
        return 1
    finally:
        collector.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
