"""
Миграция 006: настройки сбора в базе.

Зачем. Почта для запросов и пауза между ними жили в словаре в памяти
процесса и в файле окружения. Почту дописывали в `.env` заменой по
регулярному выражению — способ, при котором строка в комментарии
попадает под замену наравне с настоящей. Пауза же не доходила до клиента
вовсе: он всегда создавался со значением по умолчанию.

Две колонки в таблице настроек приложения: почта и пауза. Первичные
значения берутся из окружения при первом запуске, дальше источник
истины — база.

Прокси сюда не переносится: строка подключения может содержать пароль, а
настройки видны всем, у кого есть доступ к сайту. Он остаётся настройкой
окружения.

Запуск:
    python scripts/migrations/006_collection_settings.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/006_collection_settings.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

# Настройки лежат в .env, а он подгружается только через конфиг
# приложения. Без этого миграция не увидит уже настроенную почту и
# потребует ввести её заново.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

NEW_COLUMNS = [
    ("hh_user_email", "VARCHAR(200)"),
    ("request_delay", "FLOAT DEFAULT 1.0"),
]


def columns_of(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute("PRAGMA table_info(app_settings)")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 006: настройки сбора")
    parser.add_argument("--db", default="data/hh_vacancies.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"База не найдена: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.isolation_level = None

    try:
        существующие = columns_of(conn)
        недостающие = [(имя, тип) for имя, тип in NEW_COLUMNS if имя not in существующие]

        if not недостающие:
            print(f"{db_path}: миграция 006 уже применена, делать нечего.")
            return 0

        почта_из_окружения = os.getenv("HH_USER_EMAIL", "")
        пауза_из_окружения = os.getenv("API_REQUEST_DELAY", "1.0")

        print(f"База: {db_path}")
        print(f"  добавится колонок: {len(недостающие)} ({', '.join(и for и, _ in недостающие)})")
        print(f"  первичные значения из окружения: почта "
              f"{'задана' if почта_из_окружения else 'не задана'}, пауза {пауза_из_окружения}")

        if args.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not args.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        conn.execute("BEGIN IMMEDIATE")
        for имя, тип in недостающие:
            conn.execute(f"ALTER TABLE app_settings ADD COLUMN {имя} {тип}")

        # Переносим то, что уже настроено в окружении: иначе после
        # миграции сбор потребует ввести почту заново.
        if почта_из_окружения:
            conn.execute(
                "UPDATE app_settings SET hh_user_email = ? WHERE hh_user_email IS NULL",
                (почта_из_окружения,),
            )
        try:
            conn.execute(
                "UPDATE app_settings SET request_delay = ? WHERE request_delay IS NULL",
                (float(пауза_из_окружения),),
            )
        except ValueError:
            pass

        conn.execute("COMMIT")

        отсутствуют = [имя for имя, _ in NEW_COLUMNS if имя not in columns_of(conn)]
        if отсутствуют:
            print("Проверка не прошла, нет колонок: " + ", ".join(отсутствуют))
            return 1

        строка = conn.execute(
            "SELECT hh_user_email, request_delay FROM app_settings LIMIT 1"
        ).fetchone()
        print(f"\nКолонки добавлены. В настройках: почта "
              f"{'есть' if строка and строка[0] else 'не задана'}, пауза "
              f"{строка[1] if строка else '—'}")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
