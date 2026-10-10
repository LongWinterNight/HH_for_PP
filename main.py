#!/usr/bin/env python3
"""
HH.ru Analytics — Главная точка входа (ETL Pipeline).

Два этапа:
1. Сбор — вакансии с HH.ru API; разбор навыков и запись в SQLite идут
   внутри сбора, тем же кодом, что и сбор с экрана
2. Анализ — формирование отчётов

Использование:
    python main.py              # Сбор и анализ
    python main.py --collect    # Только сбор
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
from src.storage import VacancyStorage
from src.analyzer import VacancyAnalyzer
from src.advanced_analyzer import AdvancedAnalytics

# Инициализируем логгер
logger = get_logger(__name__)


def run_collection(
    keywords: list[str] | None = None,
    max_pages: int | None = None,
    days_back: int | None = None,
    incremental: bool = False,
    use_cache: bool = False
) -> dict:
    """
    Этап 1: Сбор вакансий с HH.ru (Extract).

    Args:
        keywords: Список поисковых запросов (или из конфига)
        max_pages: Максимум страниц (или из конфига)
        days_back: За сколько дней собирать (или из конфига)
        incremental: Не запрашивать карточки известных вакансий
        use_cache: Брать ответы поиска из кэша

    Returns:
        Словарь со статистикой сбора
    """
    logger.info("=" * 60)
    logger.info("ЭТАП 1: Сбор вакансий (Extract)")
    logger.info("=" * 60)

    def показать_ход(event):
        """
        Ход сбора в консоли. Строится на тех же событиях, что и прогресс
        в веб-интерфейсе: один механизм на оба способа запуска, а не
        прогресс-бар в одном месте и подмена методов в другом.
        """
        if event.stage == "keyword_started":
            print(f"\n[{event.keyword_index}/{event.keywords_total}] {event.keyword}")
        elif event.stage == "page_fetched":
            ожидалось = f" из ~{event.found}" if event.found else ""
            print(f"\r  собрано {event.collected}{ожидалось}", end="", flush=True)
        elif event.stage == "keyword_saved":
            print(f"\r  собрано {event.collected} — сохранено")
        elif event.stage == "finished":
            print(f"\nВсего собрано: {event.collected}")

    # Создаём сборщик с параметрами
    collector = VacancyCollector(
        max_pages=max_pages,
        days_back=days_back,
        incremental=incremental,
        use_cache=use_cache,
        on_progress=показать_ход
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


def _этап_упразднён(флаг: str) -> None:
    """
    Сказать, почему этапа больше нет, вместо падения или молчания.

    Обработка и загрузка были отдельными шагами, пока сбор клал сырые
    файлы, а в базу их переносил второй проход через CSV. Теперь сбор
    сам разбирает вакансии и пишет их в базу — тем же кодом, что и сбор
    с экрана. Второй путь разбора удалён 11.09.2026 (S11), а загрузка
    из CSV заменяла таблицу целиком: вместе с ней исчезло бы всё
    собранное после последней выгрузки.
    """
    logger.warning(
        f"{флаг} больше не нужен: сбор сам разбирает вакансии и пишет их в базу. "
        f"Этап пропущен, база не тронута."
    )


def run_analysis() -> dict:
    """
    Этап 2: Анализ и отчёты (Analyze).

    Returns:
        Словарь с путями к отчётам
    """
    logger.info("=" * 60)
    logger.info("ЭТАП 2: Анализ и отчёты (Analyze)")
    logger.info("=" * 60)

    # Данные — из базы, а не из CSV: файл выгружал удалённый путь
    # обработки, и анализ по нему считал бы вакансии на день последней
    # выгрузки, не замечая ни одного сбора после неё.
    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
    finally:
        storage.close()

    if df.empty:
        logger.warning("В базе нет вакансий. Сначала запустите сбор (--collect)")
        return {}

    # Создаём анализатор
    analyzer = VacancyAnalyzer(df)

    # Выводим сводку в консоль
    analyzer.print_summary()

    # Собираем Excel-отчёт по правилам дизайн-системы: четыре листа,
    # девять колонок, срез выборки первым листом.
    from src.report_xlsx import описать_срез, собрать_отчёт
    report_path = собрать_отчёт(df, срез=описать_срез(df))
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

    # Обработки и загрузки отдельными этапами нет: сбор разбирает
    # вакансии и пишет их в базу сам.
    results["analysis"] = run_analysis()

    # Итоговая статистика
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    logger.info("\n" + "=" * 60)
    logger.info("📊 ИТОГОВАЯ СТАТИСТИКА")
    logger.info("=" * 60)
    logger.info(f"Собрано вакансий: {results['collection'].get('unique', 0)}")
    logger.info(f"Новых в базе: {results['collection'].get('new', 0)}")
    logger.info(f"Обновлено в базе: {results['collection'].get('updated', 0)}")
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
  python main.py                      # Сбор и анализ
  python main.py --collect            # Только сбор вакансий
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
        help="Упразднён: сбор разбирает вакансии сам"
    )
    parser.add_argument(
        "--load",
        action="store_true",
        help="Упразднён: сбор пишет в базу сам"
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

    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Не запрашивать карточки вакансий, уже лежащих в базе (сами вакансии обновляются)"
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Брать ответы поиска из кэша, если они там есть"
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
                days_back=args.days_back,
                incremental=args.incremental,
                use_cache=args.cache
            )

        if args.process:
            _этап_упразднён("--process")

        if args.load:
            _этап_упразднён("--load")

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
