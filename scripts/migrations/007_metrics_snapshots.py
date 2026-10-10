"""
Миграция 007: снимки метрик.

Зачем. Тренды считались сравнением периодов внутри одного снимка базы, и
это давало бессмыслицу: источник отдаёт только открытые вакансии, поэтому
чем старше день публикации, тем меньше его вакансий дожило до сбора. На
реальных данных выходило «+246 % за неделю» — не рост рынка, а затухание
архива.

Снимок фиксирует состояние базы на свою дату. Разница между двумя
снимками означает ровно то, что написано.

Запуск:
    python scripts/migrations/007_metrics_snapshots.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/007_metrics_snapshots.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

TABLE_DDL = """
CREATE TABLE metrics_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    taken_at DATETIME NOT NULL,
    run_id INTEGER,
    source VARCHAR(20) DEFAULT 'measured',
    active_vacancies INTEGER DEFAULT 0,
    total_vacancies INTEGER DEFAULT 0,
    unique_companies INTEGER DEFAULT 0,
    unique_regions INTEGER DEFAULT 0,
    with_salary INTEGER,
    median_salary_rub FLOAT,
    salary_sample_rub INTEGER,
    medians_by_currency TEXT,
    created_at DATETIME
)
"""

# Имя индекса совпадает с тем, что создаёт SQLAlchemy для Column(index=True).
INDEX_DDL = "CREATE INDEX ix_metrics_snapshots_taken_at ON metrics_snapshots(taken_at)"


def таблица_есть(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='metrics_snapshots'"
    ).fetchone()
    return row is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 007: снимки метрик")
    parser.add_argument("--db", default="data/hh_vacancies.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"База не найдена: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.isolation_level = None

    try:
        if таблица_есть(conn):
            print(f"{db_path}: миграция 007 уже применена, делать нечего.")
            return 0

        сборов = conn.execute(
            "SELECT COUNT(*) FROM parser_runs WHERE status = 'completed'"
        ).fetchone()[0]

        print(f"База: {db_path}")
        print("  создастся таблица metrics_snapshots и индекс по дате")
        print(f"  успешных сборов в истории: {сборов} — по ним можно восстановить точки"
              " скриптом reconstruct_snapshots.py")

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

        if not таблица_есть(conn):
            print("Проверка не прошла: таблица не создана")
            return 1

        print("\nТаблица metrics_snapshots создана, индекс на месте.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
