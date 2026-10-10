"""
Миграция 015: качество сбора в истории запусков.

Зачем. «Собрано 1 891» ничего не говорит о том, годятся ли записи для
аналитики. Вакансия без карточки несёт 2,4 навыка против 14,7 у той, у
которой карточка есть; запрос, прочитанный не до конца, даёт недобор и
запрещает гасить пропавшие вакансии. Всё это измерялось запросами к
базе руками и задним числом — а значит, ухудшение сбора замечалось не
раньше, чем кто-то догадается посмотреть.

Три колонки хранят числа по каждому запуску:

    q_with_details      сколько записей получили карточку вакансии
    q_without_skills    сколько записей не дали ни одного навыка
    q_incomplete        сколько запросов прочитаны не до конца

Считать их по базе задним числом нельзя: там лежат записи всех сборов
сразу, и сегодняшнее ухудшение в них тонет. Поэтому старые строки
остаются без значений — восстановить их неоткуда.

Запуск:
    python scripts/migrations/015_run_quality.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/015_run_quality.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ТАБЛИЦА = "parser_runs"

КОЛОНКИ = {
    "q_with_details": "INTEGER",
    "q_without_skills": "INTEGER",
    "q_incomplete": "INTEGER",
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
    разбор = argparse.ArgumentParser(description="Миграция 015: качество сбора")
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
            print(f"{путь}: миграция 015 уже применена.")
            return 0

        всего = conn.execute(f"SELECT COUNT(*) FROM {ТАБЛИЦА}").fetchone()[0]

        print(f"База: {путь}")
        print(f"  добавятся колонки: {', '.join(нет_колонок)}")
        print(f"  записей о сборах: {всего} — останутся без значений")
        print("  новые сборы заполнят их сами")

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

        print("\nГотово: качество сбора хранится вместе с его итогом.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
