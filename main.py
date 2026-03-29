#!/usr/bin/env python3
"""
HH.ru Analytics — Главная точка входа (ETL Pipeline).

Этот скрипт запускает полный цикл обработки данных:
1. Extract — сбор вакансий с HH.ru API
2. Transform — обработка и извлечение навыков
3. Load — сохранение в SQLite
4. Analyze — формирование отчётов

Использование:
    python main.py              # Полный пайплайн
    python main.py --collect    # Только сбор
    python main.py --process    # Только обработка
    python main.py --analyze    # Только анализ

Важно: Перед запуском убедитесь, что:
    1. В .env указан HH_USER_EMAIL
    2. Установлены все зависимости (pip install -r requirements.txt)
    3. Вы готовы соблюдать лимиты API HH.ru (1 запрос/сек)
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Добавляем корень проекта в path для импортов
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config import settings
from src.utils import get_logger, ensure_dir
from src.api_client import HHAPIClient
from src.collector import VacancyCollector
from src.processor import VacancyProcessor
from src.storage import VacancyStorage
from src.analyzer import VacancyAnalyzer
from src.advanced_analyzer import AdvancedAnalytics

# Инициализируем логгер
logger = get_logger(__name__)


def run_collection(
    keywords: list[str] | None = None,
    max_pages: int | None = None,
    days_back: int | None = None
) -> dict:
    """
    Этап 1: Сбор вакансий с HH.ru (Extract).

    Args:
        keywords: Список поисковых запросов (или из конфига)
        max_pages: Максимум страниц (или из конфига)
        days_back: За сколько дней собирать (или из конфига)

    Returns:
        Словарь со статистикой сбора
    """
    logger.info("=" * 60)
    logger.info("ЭТАП 1: Сбор вакансий (Extract)")
    logger.info("=" * 60)

    # Создаём сборщик с параметрами
    collector = VacancyCollector(
        max_pages=max_pages,
        days_back=days_back
    )

    try:
        # Запускаем сбор
        result = collector.collect_all(
            keywords=keywords,
            save_raw=True
        )

        # Выводим статистику
        logger.info(f"✅ Сбор завершён")
        logger.info(f"   Всего собрано: {result['total']}")
        logger.info(f"   Уникальных: {result['unique']}")
        logger.info(f"   Файлов сохранено: {len(result['files'])}")

        return result

    except KeyboardInterrupt:
        logger.warning("Сбор прерван пользователем")
        return {"total": 0, "unique": 0, "files": []}
    except Exception as e:
        logger.error(f"Ошибка при сборе: {type(e).__name__} - {e}")
        raise
    finally:
        collector.close()


def run_processing() -> dict:
    """
    Этап 2: Обработка вакансий (Transform).

    Returns:
        Словарь со статистикой обработки
    """
    logger.info("=" * 60)
    logger.info("ЭТАП 2: Обработка данных (Transform)")
    logger.info("=" * 60)

    # Создаём процессор
    processor = VacancyProcessor()

    # Обрабатываем все JSON файлы
    df = processor.process_all(
        save_csv=True,
        save_parquet=True
    )

    if df.empty:
        logger.warning("Нет данных для обработки")
        return {"processed": 0}

    # Получаем статистику по навыкам
    skills_stats = processor.get_skills_statistics(df)

    logger.info(f"✅ Обработка завершена")
    logger.info(f"   Обработано вакансий: {len(df)}")
    logger.info(f"   Уникальных навыков: {len(skills_stats.get('top_hard_skills', {})) + len(skills_stats.get('top_tools', {}))}")

    return {
        "processed": len(df),
        "skills_stats": skills_stats
    }


def run_loading() -> dict:
    """
    Этап 3: Загрузка в базу данных (Load).

    Returns:
        Словарь со статистикой загрузки
    """
    logger.info("=" * 60)
    logger.info("ЭТАП 3: Загрузка в БД (Load)")
    logger.info("=" * 60)

    # Проверяем наличие CSV файла
    csv_path = settings.processed_data_dir / "vacancies_processed.csv"

    if not csv_path.exists():
        logger.warning("CSV файл не найден. Сначала запустите обработку (--process)")
        return {"loaded": 0}

    # Загружаем CSV
    import pandas as pd
    df = pd.read_csv(csv_path)

    # Создаём хранилище
    storage = VacancyStorage()

    try:
        # Сохраняем в БД
        count = storage.save_dataframe(df)

        logger.info(f"✅ Загрузка завершена")
        logger.info(f"   Сохранено записей: {count}")

        return {"loaded": count}

    except Exception as e:
        logger.error(f"Ошибка при загрузке: {type(e).__name__} - {e}")
        raise
    finally:
        storage.close()


def run_analysis() -> dict:
    """
    Этап 4: Анализ и отчёты (Analyze).

    Returns:
        Словарь с путями к отчётам
    """
    logger.info("=" * 60)
    logger.info("ЭТАП 4: Анализ и отчёты (Analyze)")
    logger.info("=" * 60)

    # Проверяем наличие CSV файла
    csv_path = settings.processed_data_dir / "vacancies_processed.csv"

    if not csv_path.exists():
        logger.warning("CSV файл не найден. Сначала запустите обработку (--process)")
        return {}

    # Загружаем данные
    import pandas as pd
    df = pd.read_csv(csv_path)

    # Создаём анализатор
    analyzer = VacancyAnalyzer(df)

    # Выводим сводку в консоль
    analyzer.print_summary()

    # Генерируем Excel-отчёт
    report_path = analyzer.generate_excel_report()
    logger.info(f"✅ Excel-отчёт: {report_path}")

    # Экспорт в CSV
    csv_stats_path = analyzer.export_to_csv()
    logger.info(f"✅ CSV-статистика: {csv_stats_path}")

    # === Расширенная аналитика ===
    logger.info("-" * 60)
    logger.info("📊 Расширенная аналитика")
    logger.info("-" * 60)

    advanced_analytics = AdvancedAnalytics(df)

    # Выводим расширенную сводку
    advanced_analytics.print_advanced_summary()

    # Генерируем детальный отчёт
    detailed_report_path = advanced_analytics.generate_detailed_excel_report()
    logger.info(f"✅ Детальный отчёт: {detailed_report_path}")

    return {
        "excel_report": str(report_path),
        "csv_stats": str(csv_stats_path),
        "advanced_report": str(detailed_report_path)
    }


def run_full_pipeline(
    keywords: list[str] | None = None,
    max_pages: int | None = None,
    days_back: int | None = None
) -> dict:
    """
    Запуск полного ETL пайплайна.

    Args:
        keywords: Поисковые запросы
        max_pages: Максимум страниц
        days_back: За сколько дней собирать

    Returns:
        Словарь с результатами всех этапов
    """
    logger.info("\n" + "=" * 60)
    logger.info("🚀 ЗАПУСК ПОЛНОГО ETL ПАЙПЛАЙНА")
    logger.info("=" * 60)
    logger.info(f"Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    start_time = datetime.now()

    results = {}

    # Этап 1: Сбор
    results["collection"] = run_collection(
        keywords=keywords,
        max_pages=max_pages,
        days_back=days_back
    )

    # Этап 2: Обработка
    results["processing"] = run_processing()

    # Этап 3: Загрузка
    results["loading"] = run_loading()

    # Этап 4: Анализ
    results["analysis"] = run_analysis()

    # Итоговая статистика
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    logger.info("\n" + "=" * 60)
    logger.info("📊 ИТОГОВАЯ СТАТИСТИКА")
    logger.info("=" * 60)
    logger.info(f"Собрано вакансий: {results['collection'].get('unique', 0)}")
    logger.info(f"Обработано вакансий: {results['processing'].get('processed', 0)}")
    logger.info(f"Загружено в БД: {results['loading'].get('loaded', 0)}")
    logger.info(f"Время выполнения: {duration:.2f} сек ({duration/60:.2f} мин)")
    logger.info("=" * 60)

    return results


def main() -> int:
    """
    Главная функция с разбором аргументов командной строки.

    Returns:
        Код выхода (0 — успех, 1 — ошибка)
    """
    # Парсер аргументов
    parser = argparse.ArgumentParser(
        description="HH.ru Analytics — ETL система для анализа вакансий",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python main.py                      # Полный пайплайн
  python main.py --collect            # Только сбор вакансий
  python main.py --process            # Только обработка
  python main.py --analyze            # Только анализ
  python main.py --collect --analyze  # Сбор и анализ
  python main.py --keywords "Python" "LLM"  # Сбор по конкретным запросам
        """
    )

    # Режимы работы
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Только сбор вакансий (Extract)"
    )
    parser.add_argument(
        "--process",
        action="store_true",
        help="Только обработка данных (Transform)"
    )
    parser.add_argument(
        "--load",
        action="store_true",
        help="Только загрузка в БД (Load)"
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Только анализ и отчёты (Analyze)"
    )

    # Параметры сбора
    parser.add_argument(
        "--keywords",
        nargs="+",
        type=str,
        help="Поисковые запросы (например: Python LLM Data)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Максимум страниц для сбора (по умолчанию из конфига)"
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=None,
        help="За сколько дней собирать (по умолчанию из конфига)"
    )

    # Настройки
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Тестовый запуск без реальных запросов"
    )

    args = parser.parse_args()

    # Проверка: если ни один режим не указан — запускаем полный пайплайн
    if not any([args.collect, args.process, args.load, args.analyze]):
        logger.info("Режим не указан — запускаем полный пайплайн")
        run_full_pipeline(
            keywords=args.keywords,
            max_pages=args.max_pages,
            days_back=args.days_back
        )
    else:
        # Запускаем указанные этапы
        if args.collect:
            run_collection(
                keywords=args.keywords,
                max_pages=args.max_pages,
                days_back=args.days_back
            )

        if args.process:
            run_processing()

        if args.load:
            run_loading()

        if args.analyze:
            run_analysis()

    return 0


if __name__ == "__main__":
    """Точка входа скрипта."""
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Прервано пользователем")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
        sys.exit(1)
