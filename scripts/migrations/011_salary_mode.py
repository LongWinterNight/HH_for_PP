"""
Миграция 011: период выплаты.

Зачем. hh.ru отдаёт `salary_range.mode` — «За месяц», «За час», «За
смену», — а мы его не собирали: часовая ставка ложилась в базу как
месячный оклад. Разбор — в `docs/data-issues.md`, запись 15.

Накопленным записям период проставить неоткуда: в базе его нет, а
дозапрашивать восемь тысяч вакансий по секунде на каждую — больше двух
часов ради поля, которое приедет само при следующем сборе. Поэтому
миграция дозапрашивает период только тем, кого правило E8 пометило
неправдоподобными: именно там сомнение мешает человеку, и именно там
часовых ставок больше всего.

Запуск:
    python scripts/migrations/011_salary_mode.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/011_salary_mode.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.api_client import HHAPIClient  # noqa: E402
from src.salary_mode import период_из_ответа  # noqa: E402


def есть_колонка(conn: sqlite3.Connection) -> bool:
    return "salary_mode" in [row[1] for row in conn.execute("PRAGMA table_info(vacancies)")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 011: период выплаты")
    parser.add_argument("--db", default="data/hh_vacancies.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--без-дозапроса", action="store_true",
                        help="только колонка, к источнику не ходить")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"База не найдена: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.isolation_level = None

    try:
        колонка_есть = есть_колонка(conn)
        помеченные = conn.execute(
            "SELECT vacancy_id FROM vacancies WHERE salary_doubt IS NOT NULL"
        ).fetchall()

        print(f"База: {db_path}")
        if not колонка_есть:
            print("  добавится колонка salary_mode")
        print(f"  записей с пометкой E8: {len(помеченные)}")
        print("  остальным период приедет при следующем сборе — он есть в поисковой выдаче")

        if args.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not args.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        if not колонка_есть:
            conn.execute("ALTER TABLE vacancies ADD COLUMN salary_mode VARCHAR(20)")

        if args.без_дозапроса:
            print("\nКолонка добавлена, дозапрос пропущен.")
            return 0

        клиент = HHAPIClient()
        проставлено, исчезло = 0, 0

        for (ид,) in помеченные:
            данные = клиент.get_vacancy_details(ид)
            if not данные:
                # Вакансию сняли с публикации — период узнать негде, и это
                # нормально: пустое значение честнее выдуманного.
                исчезло += 1
                continue
            период = период_из_ответа(данные)
            if период:
                conn.execute(
                    "UPDATE vacancies SET salary_mode = ? WHERE vacancy_id = ?", (период, ид)
                )
                проставлено += 1

        сводка = conn.execute(
            "SELECT salary_mode, COUNT(*) FROM vacancies WHERE salary_mode IS NOT NULL"
            " GROUP BY salary_mode ORDER BY COUNT(*) DESC"
        ).fetchall()

        print(f"\nГотово: период проставлен у {проставлено} записей, {исчезло} уже нет у источника.")
        for период, сколько in сводка:
            print(f"  {период}: {сколько}")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
