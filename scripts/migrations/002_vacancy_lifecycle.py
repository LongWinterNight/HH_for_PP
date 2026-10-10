"""
Миграция 002: жизненный цикл вакансии.

Зачем. По записи в базе нельзя было сказать ничего о её судьбе: когда
вакансию увидели впервые, когда в последний раз, жива ли она ещё на
источнике и каким запросом нашлась. Без первого нельзя строить динамику
(дата публикации — не дата попадания в базу), без второго и третьего
архив неотличим от текущего рынка, без четвёртого непонятно, почему
вакансия вообще здесь оказалась.

Пять колонок:
    first_seen_at   когда запись впервые попала в базу
    last_seen_at    когда источник в последний раз её отдал
    is_active       жива ли на источнике
    source_keyword  каким запросом (или запросами) найдена
    has_details     собрано ли описание вакансии

Значения существующим записям проставляются осторожно: first_seen_at по
дате публикации — нижняя честная оценка, точнее восстанавливается из
data/raw отдельным скриптом (scripts/maintenance/backfill_lifecycle.py).
has_details ставится в 0: определить задним числом по содержимому базы
нельзя, а выдавать незнание за «описания нет» — меньшее зло, чем за
«описание есть».

В отличие от миграции 001 таблица не пересоздаётся: SQLite умеет
добавлять колонки, а менять типы или ключи здесь не требуется.

Запуск:
    python scripts/migrations/002_vacancy_lifecycle.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/002_vacancy_lifecycle.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

NEW_COLUMNS = [
    ("first_seen_at", "DATETIME"),
    ("last_seen_at", "DATETIME"),
    ("is_active", "BOOLEAN DEFAULT 1"),
    ("source_keyword", "VARCHAR(500)"),
    ("has_details", "BOOLEAN DEFAULT 0"),
]

NEW_INDEXES = [
    # Активность фильтрует почти каждую выборку аналитики.
    ("idx_is_active", "vacancies(is_active)"),
    # По первой встрече считаются снимки метрик и прирост базы.
    ("idx_first_seen_at", "vacancies(first_seen_at)"),
]


def columns_of(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute("PRAGMA table_info(vacancies)")]


def indexes_of(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute("PRAGMA index_list(vacancies)")]


def already_migrated(conn: sqlite3.Connection) -> bool:
    return all(name in columns_of(conn) for name, _ in NEW_COLUMNS)


def migrate(conn: sqlite3.Connection) -> dict:
    existing = set(columns_of(conn))

    conn.execute("BEGIN IMMEDIATE")

    for name, definition in NEW_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE vacancies ADD COLUMN {name} {definition}")

    # Верхняя граница первой встречи: к моменту миграции запись в базе
    # уже была, значит увидели её не позже. Точная дата восстанавливается
    # скриптом бэкфилла по файлам сборов.
    #
    # Дата публикации сюда не годится, хотя и выглядит подходящей: это
    # другая величина. Вакансию, опубликованную в марте, мы могли увидеть
    # в сентябре, и подстановка published_at объявила бы, что база знает
    # её с марта. Прирост базы тогда превратился бы в появление вакансий
    # на рынке — ровно та подмена, из-за которой тренды и оказались
    # недостоверными.
    conn.execute("UPDATE vacancies SET first_seen_at = COALESCE(first_seen_at, created_at)")
    # Последний контакт с источником: все записи в базе пришли из
    # последнего сбора, то есть на момент миграции они были живы.
    conn.execute("UPDATE vacancies SET last_seen_at = COALESCE(last_seen_at, created_at)")
    conn.execute("UPDATE vacancies SET is_active = 1 WHERE is_active IS NULL")
    conn.execute("UPDATE vacancies SET has_details = 0 WHERE has_details IS NULL")

    for name, target in NEW_INDEXES:
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")

    conn.execute("COMMIT")

    return {
        "rows": conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0],
        "with_first_seen": conn.execute(
            "SELECT COUNT(*) FROM vacancies WHERE first_seen_at IS NOT NULL"
        ).fetchone()[0],
    }


def verify(conn: sqlite3.Connection, expected_rows: int) -> list[str]:
    problems: list[str] = []

    cols = columns_of(conn)
    for name, _ in NEW_COLUMNS:
        if name not in cols:
            problems.append(f"нет колонки {name}")

    idx = indexes_of(conn)
    for name, _ in NEW_INDEXES:
        if name not in idx:
            problems.append(f"нет индекса {name}")

    total = conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]
    if total != expected_rows:
        problems.append(f"строк {total}, было {expected_rows}")

    empty_first_seen = conn.execute(
        "SELECT COUNT(*) FROM vacancies WHERE first_seen_at IS NULL"
    ).fetchone()[0]
    if empty_first_seen:
        problems.append(f"{empty_first_seen} записей без first_seen_at")

    inactive = conn.execute("SELECT COUNT(*) FROM vacancies WHERE is_active IS NULL").fetchone()[0]
    if inactive:
        problems.append(f"{inactive} записей без is_active")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 002: жизненный цикл вакансии")
    parser.add_argument("--db", default="data/hh_vacancies.db", help="путь к базе")
    parser.add_argument("--dry-run", action="store_true", help="только показать, что будет сделано")
    parser.add_argument("--yes", action="store_true", help="выполнить без вопроса")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"База не найдена: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.isolation_level = None

    try:
        cols = columns_of(conn)
        if "created_at" not in cols:
            print("Сначала нужна миграция 001: в таблице нет created_at.")
            return 1

        if already_migrated(conn):
            print(f"{db_path}: миграция 002 уже применена, делать нечего.")
            return 0

        rows = conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]
        missing = [name for name, _ in NEW_COLUMNS if name not in cols]

        print(f"База: {db_path}")
        print(f"  строк: {rows}")
        print(f"  добавится колонок: {len(missing)} ({', '.join(missing)})")
        print(f"  добавится индексов: {len(NEW_INDEXES)}")

        if args.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not args.yes:
            print("\nЗапустите с --yes, чтобы применить. Копию базы сделайте заранее.")
            return 1

        result = migrate(conn)
        print(f"\nКолонки добавлены. Записей: {result['rows']}, "
              f"с first_seen_at: {result['with_first_seen']}")

        problems = verify(conn, rows)
        if problems:
            print("Проверки не прошли:")
            for p in problems:
                print(f"  - {p}")
            return 1

        print("Проверки пройдены: колонки, индексы, заполненность first_seen_at и is_active.")
        print("Дальше: scripts/maintenance/backfill_lifecycle.py — уточнит даты и запросы по data/raw.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
