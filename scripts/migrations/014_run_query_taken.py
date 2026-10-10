"""
Миграция 014: сколько вакансий запрос взял из выдачи.

Зачем. В разбивке сбора по запросам уже есть `found` — сколько вакансий
источник обещал по запросу. Сколько мы из них реально прочитали, не
записывалось нигде: `vacancies_new` и `vacancies_updated` считают
изменения в базе, а не прочитанные записи выдачи. Вакансия, встреченная
раньше по другому запросу, в оба этих числа не попадает — и запрос,
прочитавший тысячу записей, выглядел в истории как принёсший ноль.

Из-за этого главная беда сбора оставалась невидимой: источник отдаёт не
больше 2000 вакансий на запрос (у нас предел ещё ниже — 10 страниц по
100), и по популярному запросу мы видим малую часть. Разрыв между
`found` и `taken` — это и есть то, чего мы не увидели.

Колонка `taken` хранит число записей выдачи, прочитанных по запросу:
все страницы, которые мы успели пройти, включая вакансии, уже
встреченные по другим запросам, и те, что отсеялись по возрасту. Именно
это число сравнимо с `found`.

Старые строки остаются без значения: восстановить его неоткуда — что
прочитал сбор месяц назад, знал только тот сбор.

Запуск:
    python scripts/migrations/014_run_query_taken.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/014_run_query_taken.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ТАБЛИЦА = "run_queries"

КОЛОНКИ = {
    "taken": "INTEGER",
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
    разбор = argparse.ArgumentParser(description="Миграция 014: взято из выдачи")
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
            # Таблица создаётся самим приложением при первом запуске.
            # Миграция не должна её выдумывать: схему знает модель.
            print(f"{путь}: таблицы {ТАБЛИЦА} ещё нет — она появится при первом сборе.")
            return 0

        нет_колонок = каких_колонок_нет(conn)
        if not нет_колонок:
            print(f"{путь}: миграция 014 уже применена.")
            return 0

        всего = conn.execute(f"SELECT COUNT(*) FROM {ТАБЛИЦА}").fetchone()[0]

        print(f"База: {путь}")
        print(f"  добавятся колонки: {', '.join(нет_колонок)}")
        print(f"  строк разбивки: {всего} — останутся без значения")
        print("  новые сборы заполнят его сами")

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

        print("\nГотово: колонка «взято» добавлена в разбивку по запросам.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
