"""
Миграция 017: ключ записи — источник плюс идентификатор.

Зачем. Вакансия узнаётся по `vacancy_id`, и уникальность стоит на нём
одном. Пока источник один, это работает. Второй источник — другой сайт
РФ, Китая, Европы — ломает всё молча: идентификаторы у сайтов свои, и
«137176862» на одном не имеет никакого отношения к «137176862» на
другом. Уникальный индекс объявил бы их одной вакансией, и одна затёрла
бы другую.

Дешевле сделать это сейчас. Миграция ключа на живой базе тем дороже,
чем позже: сегодня в базе 8 700 записей одного источника, и все они
достоверно принадлежат hh.ru.

Что делает миграция:

    1. добавляет колонку `source` со значением 'hh.ru' у всех записей;
    2. снимает уникальность с `vacancy_id`;
    3. ставит уникальность на пару (source, vacancy_id).

Второй шаг — единственный необратимый: в SQLite индекс пересоздаётся,
а не изменяется. Поэтому перед запуском делается копия базы, и путь к
ней печатается.

Запуск:
    python scripts/migrations/017_source_key.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/017_source_key.py --db data/hh_vacancies.db --yes
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
КОЛОНКА = "source"

# Чем помечаются записи, собранные до появления второго источника. Все
# они собраны с hh.ru — другого источника у продукта не было.
ИСТОЧНИК_ПО_УМОЛЧАНИЮ = "hh.ru"

СТАРЫЙ_ИНДЕКС = "ix_vacancies_vacancy_id"
НОВЫЙ_ИНДЕКС = "ux_vacancies_source_vacancy"


def колонки(conn: sqlite3.Connection) -> set:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({ТАБЛИЦА})")}


def индексы(conn: sqlite3.Connection) -> set:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?",
            (ТАБЛИЦА,),
        )
    }


def main() -> int:
    разбор = argparse.ArgumentParser(description="Миграция 017: ключ источник + идентификатор")
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
        есть_колонки = колонки(conn)
        есть_индексы = индексы(conn)

        нужна_колонка = КОЛОНКА not in есть_колонки
        нужен_индекс = НОВЫЙ_ИНДЕКС not in есть_индексы
        лишний_индекс = СТАРЫЙ_ИНДЕКС in есть_индексы

        if not (нужна_колонка or нужен_индекс or лишний_индекс):
            print(f"{путь}: миграция 017 уже применена.")
            return 0

        всего = conn.execute(f"SELECT COUNT(*) FROM {ТАБЛИЦА}").fetchone()[0]

        print(f"База: {путь}")
        print(f"  записей: {всего}")
        if нужна_колонка:
            print(f"  добавится колонка {КОЛОНКА} = '{ИСТОЧНИК_ПО_УМОЛЧАНИЮ}' у всех")
        if лишний_индекс:
            print(f"  снимется уникальность с vacancy_id ({СТАРЫЙ_ИНДЕКС})")
        if нужен_индекс:
            print(f"  добавится уникальность на (source, vacancy_id) ({НОВЫЙ_ИНДЕКС})")

        # Пара (источник, идентификатор) обязана быть уникальной, иначе
        # индекс не создастся. Проверяем заранее: упасть на середине
        # миграции хуже, чем не начать.
        дубли = conn.execute(
            f"SELECT vacancy_id, COUNT(*) FROM {ТАБЛИЦА} "
            f"GROUP BY vacancy_id HAVING COUNT(*) > 1"
        ).fetchall()
        if дубли:
            print(f"\nОстановлено: {len(дубли)} идентификаторов встречаются дважды.")
            print("Уникальный индекс на них не встанет. Разберитесь с дублями:")
            for ид, сколько in дубли[:5]:
                print(f"  {ид} × {сколько}")
            return 1

        if аргументы.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not аргументы.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        # Копия базы перед необратимым шагом: пересоздание индекса в
        # SQLite нельзя откатить, а данные дороже пяти секунд копирования.
        метка = datetime.now().strftime("%Y%m%d_%H%M%S")
        копия = путь.with_name(f"{путь.stem}_до_017_{метка}{путь.suffix}")
        shutil.copy2(путь, копия)
        print(f"\nКопия базы: {копия}")

        conn.execute("BEGIN IMMEDIATE")

        if нужна_колонка:
            conn.execute(f"ALTER TABLE {ТАБЛИЦА} ADD COLUMN {КОЛОНКА} VARCHAR(50)")
            conn.execute(
                f"UPDATE {ТАБЛИЦА} SET {КОЛОНКА} = ? WHERE {КОЛОНКА} IS NULL",
                (ИСТОЧНИК_ПО_УМОЛЧАНИЮ,),
            )

        if лишний_индекс:
            conn.execute(f"DROP INDEX {СТАРЫЙ_ИНДЕКС}")
            # Неуникальный остаётся: поиск по идентификатору идёт в
            # каждом сборе, и без индекса он станет перебором таблицы.
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS ix_vacancies_vacancy_id "
                f"ON {ТАБЛИЦА}(vacancy_id)"
            )

        if нужен_индекс:
            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {НОВЫЙ_ИНДЕКС} "
                f"ON {ТАБЛИЦА}({КОЛОНКА}, vacancy_id)"
            )

        conn.execute("COMMIT")

        print("Готово: запись узнаётся по источнику и идентификатору.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
