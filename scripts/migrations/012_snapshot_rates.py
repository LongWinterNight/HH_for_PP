"""
Миграция 012: курс своего дня в снимках метрик.

Зачем. Снимок хранит медианы по каждой валюте, но не курс, по которому
их можно привести к рублям. Пересчитать старый снимок сегодняшним курсом
нельзя: разница двух таких чисел смешает два движения — рынок и валюту.
Если рубль за месяц упал на десять процентов, эквивалент сумовых
зарплат вырастет на те же десять, и график покажет рост зарплат там,
где выросла только цена валюты.

Что добавляется. `rate_date` — день котировок, `rates` — сами котировки
строкой JSON. Вместе с `medians_by_currency`, которые уже лежат в
снимке, этого достаточно, чтобы посчитать рублёвую медиану того дня
задним числом.

Старые снимки остаются без курса. Проставлять им сегодняшние котировки
значило бы записать в историю то, чего в тот день не было: пусто
честнее правдоподобной выдумки.

Запуск:
    python scripts/migrations/012_snapshot_rates.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/012_snapshot_rates.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

КОЛОНКИ = {
    "rate_date": "DATETIME",
    "rates": "TEXT",
}


def каких_колонок_нет(conn: sqlite3.Connection) -> list:
    есть = {row[1] for row in conn.execute("PRAGMA table_info(metrics_snapshots)")}
    return [имя for имя in КОЛОНКИ if имя not in есть]


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 012: курс в снимках метрик")
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
        таблицы = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "metrics_snapshots" not in таблицы:
            print("Таблицы metrics_snapshots нет. Сначала: "
                  "python scripts/migrations/007_metrics_snapshots.py --yes")
            return 1

        нет_колонок = каких_колонок_нет(conn)
        if not нет_колонок:
            print(f"{db_path}: миграция 012 уже применена.")
            return 0

        всего = conn.execute("SELECT COUNT(*) FROM metrics_snapshots").fetchone()[0]

        print(f"База: {db_path}")
        print(f"  добавятся колонки: {', '.join(нет_колонок)}")
        print(f"  снимков в истории: {всего} — останутся без курса, "
              "он появится у новых")

        if args.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not args.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        conn.execute("BEGIN IMMEDIATE")
        for имя in нет_колонок:
            conn.execute(
                f"ALTER TABLE metrics_snapshots ADD COLUMN {имя} {КОЛОНКИ[имя]}"
            )
        conn.execute("COMMIT")

        print("\nГотово: снимок теперь хранит курс своего дня.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
