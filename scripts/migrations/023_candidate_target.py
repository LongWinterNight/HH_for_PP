"""
Миграция 023: кандидат в словарь помнит, во что он слит (S10‑12a, S10‑12b).

Зачем. Кнопками «В словарь» и «Отклонить» не решается один навык в
нескольких написаниях: «ИИ», «AI» и «ИИ-инструменты» — сотни вакансий,
разбитые на три кандидата. Нужны ещё два решения:
- «это написание навыка словаря» — кандидат уходит в `synonyms` словаря;
- «это написание другого кандидата» — встречи обоих считаются вместе, а
  когда канон подтверждён, написания уходят в словарь вместе с ним.

Для обоих кандидат должен помнить цель. Колонка `target`:
- у слитого с кандидатом (`status = 'merged'`) — ключ кандидата‑канона;
- у ставшего написанием навыка словаря (`section = 'synonym'`) — канон словаря.

Существующие данные не меняются.

Запуск:
    python scripts/migrations/023_candidate_target.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/023_candidate_target.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

КОЛОНКИ = {
    "target": "VARCHAR(200)",
}


def есть_колонка(conn: sqlite3.Connection, таблица: str, имя: str) -> bool:
    return any(строка[1] == имя for строка in conn.execute(f"PRAGMA table_info({таблица})"))


def применить(conn: sqlite3.Connection) -> None:
    for имя, тип in КОЛОНКИ.items():
        if not есть_колонка(conn, "skill_candidates", имя):
            conn.execute(f"ALTER TABLE skill_candidates ADD COLUMN {имя} {тип}")


def main() -> int:
    разбор = argparse.ArgumentParser(description="Миграция 023: цель слияния кандидата")
    разбор.add_argument("--db", required=True, help="путь к базе")
    разбор.add_argument("--dry-run", action="store_true", help="показать, что изменится")
    разбор.add_argument("--yes", action="store_true", help="применить")
    аргументы = разбор.parse_args()

    путь = Path(аргументы.db)
    if not путь.exists():
        print(f"База не найдена: {путь}")
        return 1
    if not аргументы.dry_run and not аргументы.yes:
        print("Нужен --dry-run или --yes.")
        return 2

    conn = sqlite3.connect(путь)
    try:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skill_candidates'").fetchone() is None:
            print("Таблицы skill_candidates нет — сначала миграция 022.")
            return 1
        новые = [имя for имя in КОЛОНКИ if not есть_колонка(conn, "skill_candidates", имя)]
        if not новые:
            print("Колонка уже есть — делать нечего.")
            return 0
        print(f"Появятся колонки skill_candidates: {', '.join(новые)}. Существующие данные не меняются.")
        if аргументы.dry_run:
            print("Сухой прогон: база не тронута.")
            return 0

        копия = путь.parent / "backups" / f"до_023_{datetime.now():%Y%m%d_%H%M}.db"
        копия.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(копия) as куда:
            conn.backup(куда)
        print(f"Копия базы: {копия}")

        with conn:
            применить(conn)
        print("Готово.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
