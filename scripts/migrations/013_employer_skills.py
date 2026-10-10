"""
Миграция 013: навыки, названные работодателем.

Зачем. hh.ru отдаёт `key_skills` — список, который работодатель заполнил
руками в отдельном поле вакансии. Продукт его не читал вовсе: навыки
искались словарём по тексту описания, и всё, чего в словаре нет,
исчезало. По замеру на файлах сборов терялось 77 % упоминаний — 402 из
477 уникальных названий: 1С-Битрикс, Adobe Photoshop, amoCRM, A/B тесты.

Колонка `employer_skills` хранит их как есть, без приведения к нашим
категориям: раскладывать по hard/soft/tools не по чему — категорию мы
знаем только для тех навыков, что уже есть в словарях.

Старые записи остаются без значения намеренно: восстановить его можно
только из файлов сборов, и это делает отдельный скрипт
`scripts/maintenance/обогащение_навыками.py`, а не миграция. Миграция
меняет схему, данные наполняет тот, кто умеет их читать.

Запуск:
    python scripts/migrations/013_employer_skills.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/013_employer_skills.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

КОЛОНКИ = {
    "employer_skills": "TEXT",
}


def каких_колонок_нет(conn: sqlite3.Connection) -> list:
    есть = {row[1] for row in conn.execute("PRAGMA table_info(vacancies)")}
    return [имя for имя in КОЛОНКИ if имя not in есть]


def main() -> int:
    разбор = argparse.ArgumentParser(description="Миграция 013: навыки работодателя")
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
        нет_колонок = каких_колонок_нет(conn)
        if not нет_колонок:
            print(f"{путь}: миграция 013 уже применена.")
            return 0

        всего = conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]

        print(f"База: {путь}")
        print(f"  добавятся колонки: {', '.join(нет_колонок)}")
        print(f"  записей в базе: {всего} — останутся без навыков работодателя")
        print("  наполнить их из файлов сборов: "
              "python scripts/maintenance/обогащение_навыками.py --yes")

        if аргументы.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not аргументы.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        conn.execute("BEGIN IMMEDIATE")
        for имя in нет_колонок:
            conn.execute(f"ALTER TABLE vacancies ADD COLUMN {имя} {КОЛОНКИ[имя]}")
        conn.execute("COMMIT")

        print("\nГотово: колонка для навыков работодателя добавлена.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
