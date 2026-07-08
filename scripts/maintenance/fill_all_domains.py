#!/usr/bin/env python3
"""
Скрипт для сбора вакансий по всем доменам через HH.ru API.
Заполняет базу данных для всех разделов.
"""

import requests
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Добавляем корень проекта в path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config import settings
from src.api_client import HHAPIClient
from src.collector import VacancyCollector
from src.processor import VacancyProcessor
from src.storage import VacancyStorage

# =============================================================================
# Поисковые запросы для каждого домена
# =============================================================================

DOMAIN_QUERIES = {
    # IT - уже есть много
    "IT": [
        "Python разработчик", "Java разработчик", "Frontend разработчик",
        "Системный аналитик", "DevOps инженер", "QA инженер", "Тестировщик",
        "Data Scientist", "ML инженер", "1С программист"
    ],
    
    # Продажи - нужно больше
    "SALES": [
        "Менеджер по продажам", "Менеджер по работе с клиентами",
        "Торговый представитель", "Аккаунт менеджер", "Руководитель отдела продаж",
        "Менеджер B2B", "Специалист по холодным звонкам", "Бизнес-девелопер"
    ],
    
    # Административный
    "ADMIN": [
        "Офис-менеджер", "Секретарь", "Администратор", "Помощник руководителя",
        "Делопроизводитель", "Координатор", "Специалист по документообороту"
    ],
    
    # Медицина
    "MEDICINE": [
        "Врач", "Медсестра", "Врач терапевт", "Врач педиатр",
        "Стоматолог", "Фармацевт", "Врач косметолог", "Медицинская сестра",
        "Врач хирург", "Врач невролог", "Врач кардиолог", "Фельдшер"
    ],
    
    # Транспорт
    "TRANSPORT": [
        "Водитель", "Водитель курьер", "Водитель такси", "Дальнобойщик",
        "Диспетчер", "Курьер", "Логист", "Менеджер по транспорту"
    ],
    
    # Творчество
    "CREATIVE": [
        "Дизайнер", "Графический дизайнер", "Веб-дизайнер", "Дизайнер интерьера",
        "Фотограф", "Видеограф", "Монтажер", "3D дизайнер", "Иллюстратор"
    ],
    
    # Охрана
    "SECURITY": [
        "Охранник", "Сторож", "Сотрудник охраны", "Вахтер",
        "Специалист по безопасности", "Телохранитель"
    ],
    
    # Маркетинг
    "MARKETING": [
        "Маркетолог", "Интернет-маркетолог", "SMM менеджер", "Контент-менеджер",
        "SEO специалист", "Таргетолог", "Директолог", "Бренд-менеджер",
        "PR-менеджер", "Копирайтер"
    ],
    
    # HR
    "HR": [
        "Рекрутер", "HR-менеджер", "HR бизнес-партнер", "Специалист по подбору персонала",
        "Менеджер по обучению", "HR-директор", "Специалист по кадровому делопроизводству"
    ],
    
    # Финансы
    "FINANCE": [
        "Бухгалтер", "Финансовый аналитик", "Аудитор", "Финансовый директор",
        "Налоговый консультант", "Специалист по налогам", "Казначей"
    ],
    
    # Производство
    "PRODUCTION": [
        "Инженер", "Технолог", "Инженер-конструктор", "Инженер-проектировщик",
        "Мастер участка", "Начальник производства", "Специалист по качеству"
    ],
    
    # Юриспруденция
    "LEGAL": [
        "Юрист", "Юрисконсульт", "Адвокат", "Юрист по гражданскому праву",
        "Юрист по налоговому праву", "Патентный поверенный"
    ],
    
    # СМИ
    "MEDIA": [
        "Журналист", "Редактор", "Копирайтер", "Контент-менеджер",
        "PR-менеджер", "Пресс-секретарь", "Корреспондент"
    ],
    
    # Строительство
    "CONSTRUCTION": [
        "Строитель", "Прораб", "Сметчик", "Инженер ПГС", "Архитектор",
        "Геодезист", "Монтажник", "Отделочник"
    ],
    
    # Образование
    "EDUCATION": [
        "Учитель", "Преподаватель", "Репетитор", "Воспитатель",
        "Учитель начальных классов", "Учитель математики", "Учитель английского",
        "Преподаватель вуза", "Методист", "Тьютор"
    ],
    
    # Спорт
    "SPORT": [
        "Фитнес-тренер", "Персональный тренер", "Тренер по футболу",
        "Инструктор по йоге", "Тренер по плаванию", "Аниматор",
        "Менеджер по туризму", "Гид", "Турагент"
    ],
    
    # Красота
    "BEAUTY": [
        "Парикмахер", "Косметолог", "Мастер маникюра", "Визажист",
        "Стилист", "Бровист", "Лэшмейкер", "Массажист", "Эстетист"
    ],
    
    # HORECA
    "HORECA": [
        "Повар", "Официант", "Бармен", "Шеф-повар", "Су-шеф",
        "Кондитер", "Бариста", "Управляющий рестораном", "Хостес"
    ],
    
    # Логистика
    "LOGISTICS": [
        "Логист", "Складской работник", "Кладовщик", "Менеджер по закупкам",
        "Специалист по ВЭД", "Менеджер по снабжению", "Заведующий складом"
    ],
    
    # Розница
    "RETAIL": [
        "Продавец", "Продавец-консультант", "Кассир", "Мерчандайзер",
        "Управляющий магазином", "Директор магазина", "Товаровед"
    ]
}


def collect_for_domain(domain_name: str, queries: list[str], max_pages: int = 3, days_back: int = 30):
    """Собрать вакансии для конкретного домена."""
    print(f"\n{'='*60}")
    print(f"🔍 Сбор для домена: {domain_name}")
    print(f"{'='*60}")
    
    # Создаем сборщик
    collector = VacancyCollector(max_pages=max_pages, days_back=days_back)
    
    try:
        # Собираем по каждому запросу
        for query in queries:
            print(f"  📌 Запрос: {query}")
            result = collector._collect_by_keyword(query, delay_between_pages=0.5)
            if result:
                print(f"     ✅ Собрано: {len(result)} вакансий")
            time.sleep(0.5)
        
        # Сохраняем всё
        all_vacancies = list(collector._seen_ids)
        print(f"\n  💾 Всего собрано уникальных: {len(all_vacancies)}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        return False
    
    finally:
        collector.close()


def process_and_load():
    """Обработать и загрузить данные."""
    print("\n" + "="*60)
    print("🔄 Обработка и загрузка данных")
    print("="*60)
    
    # Обработка
    processor = VacancyProcessor()
    df = processor.process_all(save_csv=True, save_parquet=True)
    
    if df.empty:
        print("❌ Нет данных для обработки")
        return False
    
    print(f"✅ Обработано вакансий: {len(df)}")
    
    # Загрузка в БД
    storage = VacancyStorage()
    count = storage.save_dataframe(df)
    print(f"✅ Загружено в БД: {count} записей")
    
    storage.close()
    return True


def main():
    """Главная функция."""
    print("="*60)
    print("🚀 ЗАПОЛНЕНИЕ БАЗЫ ДАННЫХ ПО ВСЕМ ДОМЕНАМ")
    print("="*60)
    print(f"Время начала: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Собираем для каждого домена
    domains_to_collect = [
        # Приоритетные (мало данных)
        ("Образование", DOMAIN_QUERIES["EDUCATION"]),
        ("Спорт", DOMAIN_QUERIES["SPORT"]),
        ("Красота", DOMAIN_QUERIES["BEAUTY"]),
        ("Рестораны", DOMAIN_QUERIES["HORECA"]),
        ("Логистика", DOMAIN_QUERIES["LOGISTICS"]),
        ("Розница", DOMAIN_QUERIES["RETAIL"]),
        
        # Средние
        ("Медицина", DOMAIN_QUERIES["MEDICINE"]),
        ("Транспорт", DOMAIN_QUERIES["TRANSPORT"]),
        ("Творчество", DOMAIN_QUERIES["CREATIVE"]),
        ("Охрана", DOMAIN_QUERIES["SECURITY"]),
        ("Маркетинг", DOMAIN_QUERIES["MARKETING"]),
        ("HR", DOMAIN_QUERIES["HR"]),
        ("Финансы", DOMAIN_QUERIES["FINANCE"]),
        ("Производство", DOMAIN_QUERIES["PRODUCTION"]),
        ("Юриспруденция", DOMAIN_QUERIES["LEGAL"]),
        ("СМИ", DOMAIN_QUERIES["MEDIA"]),
        ("Строительство", DOMAIN_QUERIES["CONSTRUCTION"]),
        
        # Большие (уже есть данные)
        ("Административный", DOMAIN_QUERIES["ADMIN"]),
        ("Продажи", DOMAIN_QUERIES["SALES"]),
        # IT уже достаточно
    ]
    
    collected_count = 0
    for domain_name, queries in domains_to_collect:
        success = collect_for_domain(
            domain_name=domain_name,
            queries=queries,
            max_pages=2,  # 2 страницы = ~200 вакансий на запрос
            days_back=30  # 30 дней
        )
        
        if success:
            collected_count += 1
        
        # Пауза между доменами
        time.sleep(2)
    
    print("\n" + "="*60)
    print(f"✅ Сборы завершены: {collected_count}/{len(domains_to_collect)} доменов")
    print("="*60)
    
    # Обработка и загрузка
    if collected_count > 0:
        process_and_load()
    
    print("\n" + "="*60)
    print("🎉 ЗАПОЛНЕНИЕ ЗАВЕРШЕНО!")
    print("="*60)
    print(f"Время окончания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Пересоздаем каталог профессий
    print("\n📚 Пересоздание каталога профессий...")
    import subprocess
    subprocess.run(["python", str(project_root / "create_professions_catalog.py")])
    subprocess.run(["python", str(project_root / "aggressive_categorization.py")])
    subprocess.run(["python", str(project_root / "final_distribution.py")])
    
    print("\n✅ ГОТОВО! Обновите страницу в браузере.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Прервано пользователем")
        sys.exit(0)
