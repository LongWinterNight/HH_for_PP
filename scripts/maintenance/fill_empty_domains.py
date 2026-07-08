#!/usr/bin/env python3
"""
Точечный сбор вакансий для пустых доменов.
Заполняет: Образование, Спорт, Красота, HORECA, Логистика
"""

import sys
from pathlib import Path

# Добавляем корень проекта в path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.collector import VacancyCollector
from src.processor import VacancyProcessor
from src.storage import VacancyStorage

# =============================================================================
# Приоритетные домены для заполнения
# =============================================================================

PRIORITY_DOMAINS = {
    "Образование": [
        "Учитель", "Преподаватель", "Репетитор", "Воспитатель",
        "Учитель начальных классов", "Учитель математики", "Учитель английского",
        "Преподаватель вуза", "Учитель физики", "Учитель информатики",
        "Педагог", "Тьютор", "Методист", "Учитель химии", "Учитель биологии"
    ],
    
    "Спорт и фитнес": [
        "Фитнес-тренер", "Персональный тренер", "Тренер по футболу",
        "Инструктор по йоге", "Тренер по плаванию", "Тренер тренажерного зала",
        "Инструктор по фитнесу", "Тренер по боксу", "Тренер по теннису",
        "Массажист", "Инструктор ЛФК", "Тренер по бегу"
    ],
    
    "Красота": [
        "Парикмахер", "Косметолог", "Мастер маникюра", "Визажист",
        "Стилист", "Бровист", "Лэшмейкер", "Мастер депиляции",
        "Мастер педикюра", "Эстетист", "Массажист лицо",
        "Перманентный макияж", "Тренер по красоте"
    ],
    
    "Рестораны и питание": [
        "Повар", "Официант", "Бармен", "Шеф-повар", "Су-шеф",
        "Кондитер", "Бариста", "Пекарь", "Повар горячий цех",
        "Повар холодный цех", "Управляющий рестораном", "Хостес"
    ],
    
    "Логистика": [
        "Логист", "Складской работник", "Кладовщик", "Менеджер по закупкам",
        "Специалист по ВЭД", "Менеджер по снабжению", "Заведующий складом",
        "Водитель-экспедитор", "Комплектовщик", "Оператор склада",
        "Диспетчер", "Менеджер по логистике"
    ]
}


def collect_for_domain(domain_name: str, queries: list[str], max_pages: int = 2):
    """Собрать вакансии для конкретного домена."""
    print(f"\n{'='*60}")
    print(f"🔍 Сбор для домена: {domain_name}")
    print(f"{'='*60}")
    
    # Создаем сборщик
    collector = VacancyCollector(max_pages=max_pages, days_back=30)
    
    try:
        total_collected = 0
        
        # Собираем по каждому запросу
        for i, query in enumerate(queries, 1):
            print(f"  [{i}/{len(queries)}] Запрос: {query}")
            
            try:
                result = collector._collect_by_keyword(query, delay_between_pages=0.3)
                if result:
                    print(f"      ✅ Собрано: {len(result)} вакансий")
                    total_collected += len(result)
            except Exception as e:
                print(f"      ⚠️  Ошибка: {e}")
            
            # Небольшая пауза между запросами
            import time
            time.sleep(0.5)
        
        print(f"\n  💾 Всего для домена '{domain_name}': {total_collected} вакансий")
        return total_collected
        
    except KeyboardInterrupt:
        print("\n  ⚠️  Прервано пользователем")
        return 0
    
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
    print("🎯 ТОЧЕЧНОЕ ЗАПОЛНЕНИЕ ПУСТЫХ ДОМЕНОВ")
    print("="*60)
    
    from datetime import datetime
    print(f"Время начала: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Собираем для каждого приоритетного домена
    domains_to_collect = [
        ("Образование", PRIORITY_DOMAINS["Образование"]),
        ("Спорт и фитнес", PRIORITY_DOMAINS["Спорт и фитнес"]),
        ("Красота", PRIORITY_DOMAINS["Красота"]),
        ("Рестораны и питание", PRIORITY_DOMAINS["Рестораны и питание"]),
        ("Логистика", PRIORITY_DOMAINS["Логистика"])
    ]
    
    total_collected = 0
    for domain_name, queries in domains_to_collect:
        collected = collect_for_domain(
            domain_name=domain_name,
            queries=queries,
            max_pages=2  # 2 страницы = ~200 вакансий на запрос
        )
        total_collected += collected
        
        # Пауза между доменами
        import time
        time.sleep(1)
    
    print("\n" + "="*60)
    print(f"✅ Сбор завершен! Всего собрано: {total_collected} вакансий")
    print("="*60)
    
    # Обработка и загрузка
    if total_collected > 0:
        process_and_load()
        
        # Пересоздаем каталог профессий
        print("\n📚 Пересоздание каталога профессий...")
        import subprocess
        subprocess.run(["python", str(project_root / "create_professions_catalog.py")])
        subprocess.run(["python", str(project_root / "aggressive_categorization.py")])
        subprocess.run(["python", str(project_root / "final_distribution.py")])
        
        print("\n✅ КАТАЛОГ ОБНОВЛЕН!")
    else:
        print("\n⚠️  Данные не собраны, каталог не обновлялся")
    
    print("\n" + "="*60)
    print("🎉 ГОТОВО!")
    print("="*60)
    print(f"Время окончания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n📌 Обнови страницу в браузере (Ctrl+Shift+R)")
    print("="*60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Прервано пользователем")
        sys.exit(0)
