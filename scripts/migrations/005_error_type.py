"""
Миграция 005: причина отказа отдельным полем.

Зачем. Когда сбор падает, в истории остаётся текст исключения — иногда
вроде `search_with_progress() got an unexpected keyword argument`. По
такой строке нельзя ни понять причину, ни выбрать действие: «токен
протух» и «сеть недоступна» требуют разного, а выглядят одинаково.

Поле `error_type` хранит причину коротким кодом, по которому интерфейс
выбирает объяснение и предлагает следующий шаг.

Запуск:
    python scripts/migrations/005_error_type.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/005_error_type.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def есть_колонка(conn: sqlite3.Connection) -> bool:
    return "error_type" in [row[1] for row in conn.execute("PRAGMA table_info(parser_runs)")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 005: причина отказа")
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
        if есть_колонка(conn):
            print(f"{db_path}: миграция 005 уже применена, делать нечего.")
            return 0

        с_ошибками = conn.execute(
            "SELECT COUNT(*) FROM parser_runs WHERE error_message IS NOT NULL"
        ).fetchone()[0]

        print(f"База: {db_path}")
        print("  добавится колонка error_type")
        print(f"  запусков с ошибкой в истории: {с_ошибками}"
              " — причина у них останется пустой, этих данных не существует")

        if args.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not args.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ALTER TABLE parser_runs ADD COLUMN error_type VARCHAR(50)")
        conn.execute("COMMIT")

        if not есть_колонка(conn):
            print("Проверка не прошла: колонка не создана")
            return 1

        print("\nКолонка error_type добавлена.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
