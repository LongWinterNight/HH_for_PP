"""
Миграция 016: состояние обхода переживает перезапуск.

Зачем. Сбор идёт фоновой задачей внутри веб-процесса и живёт минуты, а
с резкой запроса на срезы (S4‑2) — десятки минут. Перезапуск сервера
посреди работы означал «начинать заново»: собранное оставалось в базе,
но какие запросы уже пройдены, знала только память процесса. Сбор из
семи запросов, оборванный на шестом, повторял все шесть.

Колонка `progress_state` хранит это одним JSON: какие запросы пройдены
целиком, какой шёл в момент обрыва и на какой странице. Отдельными
колонками это не хранится намеренно — набор полей будет меняться
вместе с устройством обхода (срезы по регионам, окна дат), и каждая
такая перемена стоила бы миграции.

Старые записи остаются без значения: чего не записывали, того не
восстановить.

Запуск:
    python scripts/migrations/016_run_progress.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/016_run_progress.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ТАБЛИЦА = "parser_runs"

КОЛОНКИ = {
    "progress_state": "TEXT",
}


def каких_колонок_нет(conn: sqlite3.Connection) -> list:
    есть = {row[1] for row in conn.execute(f"PRAGMA table_info({ТАБЛИЦА})")}
    return [имя for имя in КОЛОНКИ if имя not in есть]


def таблица_есть(conn: sqlite3.Connection) -> bool:
    строка = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (ТАБЛИЦА,)
    ).fetchone()
    return строка is not None


def main() -> int:
    разбор = argparse.ArgumentParser(description="Миграция 016: состояние обхода")
    разбор.add_argument("--db", default="data/hh_vacancies.db")
    разбор.add_argument("--dry-run", action="store_true")
    разбор.add_argument("--yes", action="store_true")
    аргументы = разбор.parse_args()

    путь = Path(аргументы.db)
    if not путь.exists():
        print(f"База не найдена: {путь}")
        return 1

    conn = sqlite3.connect(путь)
    conn.isolation_level = None

    try:
        if not таблица_есть(conn):
            print(f"{путь}: таблицы {ТАБЛИЦА} ещё нет — она появится при первом сборе.")
            return 0

        нет_колонок = каких_колонок_нет(conn)
        if not нет_колонок:
            print(f"{путь}: миграция 016 уже применена.")
            return 0

        всего = conn.execute(f"SELECT COUNT(*) FROM {ТАБЛИЦА}").fetchone()[0]

        print(f"База: {путь}")
        print(f"  добавятся колонки: {', '.join(нет_колонок)}")
        print(f"  записей о сборах: {всего} — останутся без значения")
        print("  состояние появится у сборов, запущенных после миграции")

        if аргументы.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not аргументы.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        conn.execute("BEGIN IMMEDIATE")
        for имя in нет_колонок:
            conn.execute(f"ALTER TABLE {ТАБЛИЦА} ADD COLUMN {имя} {КОЛОНКИ[имя]}")
        conn.execute("COMMIT")

        print("\nГотово: обход сбора теперь переживает перезапуск.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
