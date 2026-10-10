"""
Миграция 019: список запросов сбора живёт в базе.

Зачем. Запросы правились в конфиге — человек, который не открывает
файлы, изменить их не мог. На экране «Сбор данных» список появился, но
жил только в памяти вкладки: обновление страницы стирало его, и всё
приходилось набирать заново.

База, а не конфиг: конфиг — это то, с чем продукт приехал, а список
запросов человек меняет каждую неделю. Тем же путём раньше переехали
почта и пауза между запросами (миграция 006).

Что делает миграция: добавляет колонку `search_queries` в
`app_settings` — список строк в JSON. Пустая колонка означает «человек
ничего не задал», и это не то же самое, что пустой список: сбор в обоих
случаях не запускается, но экран при первом открытии предлагает список
из конфига как заготовку.

Запуск:
    python scripts/migrations/019_search_queries.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/019_search_queries.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ТАБЛИЦА = "app_settings"
КОЛОНКА = "search_queries"
ТИП = "TEXT"


def есть_колонка(conn: sqlite3.Connection, таблица: str, имя: str) -> bool:
    return имя in {row[1] for row in conn.execute(f"PRAGMA table_info({таблица})")}


def бэкап(db_path: Path) -> Path:
    """
    Копия базы перед изменением схемы.

    Не осторожность ради осторожности: однажды сбор уже стёр базу
    целиком, и с тех пор в проекте правило — перед миграцией копия.
    """
    метка = datetime.now().strftime("%Y%m%d_%H%M%S")
    куда = db_path.parent / "backups" / f"{db_path.stem}_до_019_{метка}.db"
    куда.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, куда)
    return куда


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 019: запросы сбора в базе")
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
        таблицы = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if ТАБЛИЦА not in таблицы:
            print(f"Таблицы {ТАБЛИЦА} нет — не та база.")
            return 1

        if есть_колонка(conn, ТАБЛИЦА, КОЛОНКА):
            print(f"{db_path}: миграция 019 уже применена.")
            return 0

        print(f"База: {db_path}")
        print(f"  у настроек появится колонка {КОЛОНКА}: список запросов в JSON")
        print("  существующие настройки не меняются — колонка пустая")

        if args.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not args.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        куда = бэкап(db_path)
        print(f"\nКопия базы: {куда}")

        conn.execute(f"ALTER TABLE {ТАБЛИЦА} ADD COLUMN {КОЛОНКА} {ТИП}")
        print(f"Готово: колонка {КОЛОНКА} добавлена.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
