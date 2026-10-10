"""
Миграция 008: причина сомнения в зарплате.

Зачем. В данных источника есть зарплаты, которых не бывает: «18 EUR»,
«400 UZS», «от 50 до 100 000 ₽». Они портят минимум по валюте — на
экране и в отчёте он показывал «от 7 ₽» вместо пяти тысяч. Решение
записано в `docs/data-issues.md`, запись 13: запись не удаляем, а
помечаем причину сомнения; агрегаты считаются без помеченных.

Колонка `salary_doubt` хранит причину словами, а не голым признаком:
человеку, увидевшему пометку, нужно понимать, что именно с числом не
так. Пусто — с зарплатой всё в порядке.

Пороги живут в `src/salary_sanity.py` и однажды изменятся; тогда
признак пересчитывается тем же скриптом — повторный запуск безопасен.

Запуск:
    python scripts/migrations/008_salary_doubt.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/008_salary_doubt.py --db data/hh_vacancies.db --yes
    python scripts/migrations/008_salary_doubt.py --пересчитать --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.salary_sanity import причина_сомнения  # noqa: E402


def есть_колонка(conn: sqlite3.Connection) -> bool:
    return "salary_doubt" in [row[1] for row in conn.execute("PRAGMA table_info(vacancies)")]


def посчитать(conn: sqlite3.Connection) -> list:
    """Собрать причины по всем записям с зарплатой."""
    # Период выплаты появился позже (миграция 011): на базе, где его ещё
    # нет, запрос упал бы, а пересчёт нужен и там.
    есть_период = "salary_mode" in [row[1] for row in conn.execute("PRAGMA table_info(vacancies)")]
    поле = "salary_mode" if есть_период else "NULL"

    строки = conn.execute(
        f"SELECT id, salary_from, salary_to, salary_currency, {поле} FROM vacancies "
        "WHERE salary_from IS NOT NULL OR salary_to IS NOT NULL"
    ).fetchall()

    к_записи = []
    for ид, от, до, валюта, период in строки:
        причина = причина_сомнения(от, до, валюта, период)
        if причина:
            к_записи.append((причина, ид))
    return к_записи


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 008: сомнительные зарплаты")
    parser.add_argument("--db", default="data/hh_vacancies.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--пересчитать", action="store_true",
                        help="переставить пометки после правки порогов")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"База не найдена: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.isolation_level = None

    try:
        колонка_есть = есть_колонка(conn)
        if колонка_есть and not args.пересчитать:
            print(f"{db_path}: миграция 008 уже применена. "
                  "Для перестановки пометок после правки порогов: --пересчитать")
            return 0

        к_записи = посчитать(conn)
        всего = conn.execute(
            "SELECT COUNT(*) FROM vacancies WHERE salary_from IS NOT NULL OR salary_to IS NOT NULL"
        ).fetchone()[0]

        print(f"База: {db_path}")
        if not колонка_есть:
            print("  добавится колонка salary_doubt")
        print(f"  записей с зарплатой: {всего}")
        доля = len(к_записи) / всего * 100 if всего else 0
        print(f"  будет помечено сомнительными: {len(к_записи)} ({доля:.1f} %)")

        причины = {}
        for причина, _ in к_записи:
            причины[причина] = причины.get(причина, 0) + 1
        for причина, сколько in sorted(причины.items(), key=lambda п: -п[1]):
            print(f"    {сколько:>4}  {причина}")

        print("\n  Ни одна запись не удаляется: вакансии остаются в списке и в выгрузке,")
        print("  из расчёта минимума, медианы и средней они исключаются.")

        if args.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not args.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        conn.execute("BEGIN IMMEDIATE")
        if not колонка_есть:
            conn.execute("ALTER TABLE vacancies ADD COLUMN salary_doubt VARCHAR(60)")
        else:
            # Пересчёт: сначала снимаем прежние пометки, иначе запись,
            # переставшая быть сомнительной после правки порогов, так и
            # осталась бы помеченной.
            conn.execute("UPDATE vacancies SET salary_doubt = NULL WHERE salary_doubt IS NOT NULL")
        conn.executemany("UPDATE vacancies SET salary_doubt = ? WHERE id = ?", к_записи)
        conn.execute("COMMIT")

        помечено = conn.execute(
            "SELECT COUNT(*) FROM vacancies WHERE salary_doubt IS NOT NULL"
        ).fetchone()[0]
        if помечено != len(к_записи):
            print(f"Проверка не прошла: помечено {помечено}, ожидалось {len(к_записи)}")
            return 1

        print(f"\nГотово: помечено {помечено} записей.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
