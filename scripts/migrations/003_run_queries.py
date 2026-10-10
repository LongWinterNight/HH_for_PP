"""
Миграция 003: разбивка сбора по поисковым запросам.

Зачем. История сборов отвечает на вопрос «сколько собрали», но не на
вопрос «почему столько». Сбор из семи запросов, принёсший мало вакансий,
выглядит одинаково и когда рынок пуст, и когда четыре запроса упали на
отказе источника, и когда всё уже было в базе. Разбивка по запросам
делает эти случаи различимыми.

Таблица заполняется после каждого сбора: строка на запрос.

Запуск:
    python scripts/migrations/003_run_queries.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/003_run_queries.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

TABLE_DDL = """
CREATE TABLE run_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    keyword VARCHAR(500) NOT NULL,
    status VARCHAR(20) DEFAULT 'partial',
    found INTEGER,
    pages INTEGER DEFAULT 0,
    vacancies_new INTEGER DEFAULT 0,
    vacancies_updated INTEGER DEFAULT 0,
    from_cache INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    created_at DATETIME
)
"""

# Имя индекса совпадает с тем, что создаёт SQLAlchemy для Column(index=True):
# иначе первый же create_all() добавит рядом второй индекс по тому же полю.
INDEX_DDL = "CREATE INDEX ix_run_queries_run_id ON run_queries(run_id)"


def table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='run_queries'"
    ).fetchone()
    return row is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 003: разбивка сбора по запросам")
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
        if table_exists(conn):
            print(f"{db_path}: миграция 003 уже применена, делать нечего.")
            return 0

        runs = conn.execute("SELECT COUNT(*) FROM parser_runs").fetchone()[0]
        print(f"База: {db_path}")
        print(f"  запусков в истории: {runs}")
        print("  создастся таблица run_queries и индекс по run_id")
        print("  прошлые запуски останутся без разбивки: этих данных не существует")

        if args.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not args.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        conn.execute("BEGIN IMMEDIATE")
        conn.execute(TABLE_DDL)
        conn.execute(INDEX_DDL)
        conn.execute("COMMIT")

        problems = []
        if not table_exists(conn):
            problems.append("таблица не создана")
        indexes = [r[1] for r in conn.execute("PRAGMA index_list(run_queries)")]
        if "ix_run_queries_run_id" not in indexes:
            problems.append("нет индекса по run_id")

        if problems:
            print("Проверки не прошли:")
            for p in problems:
                print(f"  - {p}")
            return 1

        print("\nТаблица run_queries создана, индекс на месте.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
