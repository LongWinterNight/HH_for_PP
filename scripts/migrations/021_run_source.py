"""
Миграция 021: источник запуска и просьба об остановке у сбора.

Зачем. Сбор по расписанию идёт отдельным процессом, а не внутри
приложения. Приложению нужно отличать его запись от следа собственного
умершего сбора — иначе перезапуск приложения помечал бы идущий сбор
оборванным, — а человеку на экране истории нужно видеть, кто запускал.
Остановить такой сбор с экрана можно только записью в базу, которую
сбор сам прочитает.

Что делает миграция: добавляет в `parser_runs` две колонки —
`source` (`screen` у всех прежних запусков: расписания до сих пор не
было) и `stop_requested`.

Запуск:
    python scripts/migrations/021_run_source.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/021_run_source.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ТАБЛИЦА = "parser_runs"
КОЛОНКИ = {
    "source": "VARCHAR(20) DEFAULT 'screen'",
    "stop_requested": "BOOLEAN DEFAULT 0",
}


def есть_колонка(conn: sqlite3.Connection, таблица: str, имя: str) -> bool:
    return any(строка[1] == имя for строка in conn.execute(f"PRAGMA table_info({таблица})"))


def применить(conn: sqlite3.Connection) -> list:
    """Добавить недостающие колонки. Возвращает добавленные."""
    добавлены = []
    for имя, тип in КОЛОНКИ.items():
        if есть_колонка(conn, ТАБЛИЦА, имя):
            continue
        conn.execute(f"ALTER TABLE {ТАБЛИЦА} ADD COLUMN {имя} {тип}")
        добавлены.append(имя)
    if "source" in добавлены:
        conn.execute(f"UPDATE {ТАБЛИЦА} SET source = 'screen' WHERE source IS NULL")
    return добавлены


def main() -> int:
    разбор = argparse.ArgumentParser(description="Миграция 021: источник запуска сбора")
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
        недостаёт = [имя for имя in КОЛОНКИ if not есть_колонка(conn, ТАБЛИЦА, имя)]
        if not недостаёт:
            print("Колонки уже есть — делать нечего.")
            return 0

        запусков = conn.execute(f"SELECT COUNT(*) FROM {ТАБЛИЦА}").fetchone()[0]
        print(f"Появятся колонки {ТАБЛИЦА}: {', '.join(недостаёт)}.")
        print(f"Прежние запуски ({запусков}) получат источник «screen».")
        if аргументы.dry_run:
            print("Сухой прогон: база не тронута.")
            return 0

        копия = путь.parent / "backups" / f"до_021_{datetime.now():%Y%m%d_%H%M}.db"
        копия.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(путь, копия)
        print(f"Копия базы: {копия}")

        with conn:
            применить(conn)
        print("Готово.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
