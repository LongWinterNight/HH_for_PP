"""
Миграция 010: рублёвый эквивалент зарплаты.

Зачем. Зарплаты идут в девяти валютах, и человеку нечем их сравнить:
19 000 000 сум и 300 000 рублей стоят в списке рядом. Колонки
`salary_from_rub` и `salary_to_rub` хранят пересчёт по официальному курсу
ЦБ, а `rate_date` — дату курса, которую обязана называть подпись на
экране: без неё «≈ 139 000 ₽» ничем не подтверждено.

Почему храним, а не считаем при показе. Пересчёт нужен и в сортировке, и
в агрегатах, которые пишутся сырым SQL: без колонки правило пришлось бы
повторять в каждом запросе. Курс берётся один на всю выборку — на дату
последнего сбора, — поэтому число не дрожит день ото дня.

Валюта, которой нет в котировках, остаётся без эквивалента. Пусто здесь
важнее нуля: ноль выглядит как настоящая зарплата.

Запуск:
    python scripts/migrations/010_salary_rub.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/010_salary_rub.py --db data/hh_vacancies.db --yes
    python scripts/migrations/010_salary_rub.py --пересчитать --yes   # после обновления курса
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.cbr_rates import Курсы  # noqa: E402

КОЛОНКИ = {
    "salary_from_rub": "FLOAT",
    "salary_to_rub": "FLOAT",
    "rate_date": "DATETIME",
}


def каких_колонок_нет(conn: sqlite3.Connection) -> list:
    есть = {row[1] for row in conn.execute("PRAGMA table_info(vacancies)")}
    return [имя for имя in КОЛОНКИ if имя not in есть]


def курсы_из_базы(conn: sqlite3.Connection):
    """Последние известные курсы. Их кладёт миграция 009."""
    дата = conn.execute("SELECT MAX(rate_date) FROM currency_rates").fetchone()
    дата = дата[0] if дата else None
    if not дата:
        return None

    строки = conn.execute(
        "SELECT currency, value FROM currency_rates WHERE rate_date = ?", (дата,)
    ).fetchall()
    return Курсы(
        на_дату=datetime.fromisoformat(дата).date() if isinstance(дата, str) else дата.date(),
        значения=dict(строки),
    )


def посчитать(conn: sqlite3.Connection, курсы: Курсы) -> tuple:
    """Пересчитать все зарплаты. Возвращает (что записать, сколько без курса)."""
    строки = conn.execute(
        "SELECT id, salary_from, salary_to, salary_currency FROM vacancies "
        "WHERE salary_from IS NOT NULL OR salary_to IS NOT NULL"
    ).fetchall()

    момент = datetime.combine(курсы.на_дату, datetime.min.time())
    к_записи, без_курса = [], 0

    for ид, от, до, валюта in строки:
        курс = курсы.рублей_за(валюта)
        if курс is None:
            без_курса += 1
            continue
        к_записи.append((
            round(от * курс) if от is not None else None,
            round(до * курс) if до is not None else None,
            момент,
            ид,
        ))

    return к_записи, без_курса


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 010: зарплата в рублях")
    parser.add_argument("--db", default="data/hh_vacancies.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--пересчитать", action="store_true",
                        help="переставить эквиваленты после обновления курса")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"База не найдена: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.isolation_level = None

    try:
        нет_колонок = каких_колонок_нет(conn)
        if not нет_колонок and not args.пересчитать:
            print(f"{db_path}: миграция 010 уже применена. "
                  "Для пересчёта после обновления курса: --пересчитать")
            return 0

        курсы = курсы_из_базы(conn)
        if not курсы:
            print("В базе нет курсов. Сначала: python scripts/migrations/009_currency_rates.py --yes")
            return 1

        к_записи, без_курса = посчитать(conn, курсы)

        print(f"База: {db_path}")
        if нет_колонок:
            print(f"  добавятся колонки: {', '.join(нет_колонок)}")
        print(f"  курс ЦБ на {курсы.на_дату:%d.%m.%Y}")
        print(f"  пересчитано записей: {len(к_записи)}")
        if без_курса:
            print(f"  без эквивалента (валюты нет в котировках): {без_курса}")

        if args.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not args.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        conn.execute("BEGIN IMMEDIATE")
        for имя in нет_колонок:
            conn.execute(f"ALTER TABLE vacancies ADD COLUMN {имя} {КОЛОНКИ[имя]}")
        conn.executemany(
            "UPDATE vacancies SET salary_from_rub = ?, salary_to_rub = ?, rate_date = ? WHERE id = ?",
            к_записи,
        )
        conn.execute("COMMIT")

        посчитано = conn.execute(
            "SELECT COUNT(*) FROM vacancies WHERE salary_from_rub IS NOT NULL"
        ).fetchone()[0]
        print(f"\nГотово: эквивалент есть у {посчитано} записей.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
