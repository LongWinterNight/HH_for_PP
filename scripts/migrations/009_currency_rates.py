"""
Миграция 009: таблица официальных курсов валют.

Зачем. Зарплаты идут в девяти валютах, и сравнить их человеку нечем.
Рублёвый эквивалент по курсу ЦБ отвечает на этот вопрос — но курс нужно
где-то держать: ходить к источнику на каждый показ страницы незачем
(курс за день не меняется), а при недоступности ЦБ вчерашний курс с
честной подписью лучше, чем пустое место.

Таблица заполняется сразу при миграции: курсы на сегодня забираются у
ЦБ, чтобы после прогона пересчёт уже работал.

Запуск:
    python scripts/migrations/009_currency_rates.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/009_currency_rates.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.cbr_rates import запросить  # noqa: E402

СОЗДАНИЕ = """
CREATE TABLE IF NOT EXISTS currency_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    currency VARCHAR(10) NOT NULL,
    rate_date DATETIME NOT NULL,
    value FLOAT NOT NULL,
    fetched_at DATETIME NOT NULL,
    CONSTRAINT uq_currency_rate_date UNIQUE (currency, rate_date)
)
"""


def есть_таблица(conn: sqlite3.Connection) -> bool:
    return bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='currency_rates'"
    ).fetchone())


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 009: курсы валют")
    parser.add_argument("--db", default="data/hh_vacancies.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--без-загрузки", action="store_true",
                        help="только создать таблицу, к ЦБ не ходить")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"База не найдена: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.isolation_level = None

    try:
        уже_есть = есть_таблица(conn)
        print(f"База: {db_path}")
        print("  таблица currency_rates уже есть" if уже_есть
              else "  создастся таблица currency_rates")

        курсы = None
        if not args.без_загрузки:
            try:
                курсы = запросить()
                print(f"  курсы ЦБ на {курсы.на_дату:%d.%m.%Y}: {len(курсы.значения)} валют")
            except Exception as e:
                # Недоступность источника не повод не создавать таблицу:
                # курсы приедут при первом же обновлении.
                print(f"  ЦБ недоступен ({type(e).__name__}) — таблица будет пустой")

        if args.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not args.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        conn.execute("BEGIN IMMEDIATE")
        conn.execute(СОЗДАНИЕ)
        if курсы:
            сейчас = datetime.now()
            conn.executemany(
                "INSERT OR REPLACE INTO currency_rates (currency, rate_date, value, fetched_at)"
                " VALUES (?, ?, ?, ?)",
                [(код, datetime.combine(курсы.на_дату, datetime.min.time()), значение, сейчас)
                 for код, значение in курсы.значения.items()],
            )
        conn.execute("COMMIT")

        сколько = conn.execute("SELECT COUNT(*) FROM currency_rates").fetchone()[0]
        print(f"\nГотово: таблица создана, курсов в ней {сколько}.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
