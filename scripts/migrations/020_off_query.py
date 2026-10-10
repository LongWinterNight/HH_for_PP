"""
Миграция 020: признак «найдена не по запросу» у вакансии.

Зачем. Источник искал слова запроса во всех полях, включая название
компании: по «Арт-директор» пришла 331 вакансия ресторанов «АРТ РЕСТ».
Они входили в медианы и частоты навыков профессии. Удалять их нельзя —
правило, по которому они узнаются, приближённое, и ошибку удаления не
вернуть. Поэтому вакансия помечается, а аналитика и список её
пропускают.

Что делает миграция: добавляет колонку `off_query` в `vacancies`.
Ноль — по запросу либо судить не по чему; единица — слов запроса в
вакансии нет. Саму пометку ставит
`scripts/maintenance/пометить_не_по_запросу.py`.

Запуск:
    python scripts/migrations/020_off_query.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/020_off_query.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ТАБЛИЦА = "vacancies"
КОЛОНКА = "off_query"
ТИП = "INTEGER NOT NULL DEFAULT 0"


def есть_колонка(conn: sqlite3.Connection, таблица: str, имя: str) -> bool:
    return any(строка[1] == имя for строка in conn.execute(f"PRAGMA table_info({таблица})"))


def main() -> int:
    разбор = argparse.ArgumentParser(description="Миграция 020: признак «не по запросу»")
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
        if есть_колонка(conn, ТАБЛИЦА, КОЛОНКА):
            print(f"Колонка {КОЛОНКА} уже есть — делать нечего.")
            return 0

        print(f"Появится колонка {ТАБЛИЦА}.{КОЛОНКА} ({ТИП}) и индекс по ней.")
        if аргументы.dry_run:
            print("Сухой прогон: база не тронута.")
            return 0

        копия = путь.parent / "backups" / f"до_020_{datetime.now():%Y%m%d_%H%M}.db"
        копия.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(путь, копия)
        print(f"Копия базы: {копия}")

        with conn:
            conn.execute(f"ALTER TABLE {ТАБЛИЦА} ADD COLUMN {КОЛОНКА} {ТИП}")
            conn.execute(f"CREATE INDEX IF NOT EXISTS ix_{ТАБЛИЦА}_{КОЛОНКА} ON {ТАБЛИЦА} ({КОЛОНКА})")
        print("Готово.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
