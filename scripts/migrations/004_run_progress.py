"""
Миграция 004: ход сбора хранится в базе.

Зачем. Состояние идущего сбора жило в памяти процесса. Перезапуск
сервера уносил его с собой: фоновая задача умирала, а запись о запуске
навсегда оставалась со статусом «running». В истории такие запуски
выглядят как вечно идущие, и отличить их от настоящей работы нечем.

Пять полей: процент, текущий запрос, страница, ожидаемый объём и отметка
живости. По последней видно, дышит ли процесс: запись со статусом
«running» и старой отметкой — это след оборвавшегося сбора.

Запуск:
    python scripts/migrations/004_run_progress.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/004_run_progress.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

NEW_COLUMNS = [
    ("progress_percent", "INTEGER DEFAULT 0"),
    ("current_keyword", "VARCHAR(500)"),
    ("current_page", "INTEGER DEFAULT 0"),
    ("found_estimate", "INTEGER"),
    ("heartbeat_at", "DATETIME"),
]


def columns_of(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute("PRAGMA table_info(parser_runs)")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 004: ход сбора в базе")
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
        существующие = columns_of(conn)
        недостающие = [(имя, тип) for имя, тип in NEW_COLUMNS if имя not in существующие]

        if not недостающие:
            print(f"{db_path}: миграция 004 уже применена, делать нечего.")
            return 0

        зависшие = conn.execute(
            "SELECT COUNT(*) FROM parser_runs WHERE status = 'running'"
        ).fetchone()[0]

        print(f"База: {db_path}")
        print(f"  добавится колонок: {len(недостающие)} ({', '.join(и for и, _ in недостающие)})")
        if зависшие:
            print(f"  запусков в статусе «running»: {зависшие} — они получат отметку живости"
                  f" и будут разобраны при следующем старте приложения")

        if args.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not args.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        conn.execute("BEGIN IMMEDIATE")
        for имя, тип in недостающие:
            conn.execute(f"ALTER TABLE parser_runs ADD COLUMN {имя} {тип}")
        conn.execute("COMMIT")

        проблемы = [имя for имя, _ in NEW_COLUMNS if имя not in columns_of(conn)]
        if проблемы:
            print("Проверки не прошли, нет колонок: " + ", ".join(проблемы))
            return 1

        print("\nКолонки добавлены. Ход сбора теперь можно писать в базу.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
