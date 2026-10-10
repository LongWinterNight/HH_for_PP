"""
Навыки работодателя из старых файлов сборов.

Зачем. Поле `key_skills` — список навыков, который работодатель заполнил
руками, — продукт не читал вовсе: навыки искались словарём по тексту, и
всё, чего в словаре нет, исчезало. Живой сбор это уже умеет (миграция
013 и `normalize.навыки_работодателя`), но в базе лежат тысячи записей,
собранных раньше. Пересобирать их значит заново ходить в источник за
тем, что уже сохранено в `data/raw`.

Скрипт читает файлы прошлых сборов, достаёт из них `key_skills` и
дописывает их к записям в базе: в `employer_skills` — как есть, в
`all_skills` — без дублей с тем, что нашёл словарь.

Существующие навыки не стираются: скрипт только добавляет. Вакансия, по
которой в файлах ничего нет, остаётся как была.

Запуск:
    python scripts/maintenance/обогащение_навыками.py --сухой-прогон
    python scripts/maintenance/обогащение_навыками.py --yes
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def вакансии_из_файла(путь: Path):
    """Вакансии из файла сбора — формат менялся, поддерживаются оба."""
    try:
        данные = json.loads(путь.read_text(encoding="utf-8"))
    except Exception:
        return []

    if isinstance(данные, dict):
        данные = данные.get("vacancies") or данные.get("items") or []
    return данные if isinstance(данные, list) else []


def собрать_навыки(папка: Path) -> dict:
    """{ид вакансии: [навыки работодателя]} по всем файлам сборов.

    Один и тот же идентификатор встречается в разных файлах: берётся
    самый длинный список — работодатель мог дополнить вакансию, и потеря
    навыка хуже, чем лишний.
    """
    найденное: dict[str, list] = {}

    for файл in sorted(папка.glob("*.json")):
        for вакансия in вакансии_из_файла(файл):
            if not isinstance(вакансия, dict):
                continue
            ид = str(вакансия.get("id") or "")
            сырые = вакансия.get("key_skills") or []
            навыки = []
            видели = set()
            for запись in сырые:
                имя = (запись.get("name") if isinstance(запись, dict) else запись) or ""
                имя = имя.strip()
                if имя and имя.lower() not in видели:
                    видели.add(имя.lower())
                    навыки.append(имя)
            if ид and навыки and len(навыки) > len(найденное.get(ид, [])):
                найденное[ид] = навыки

    return найденное


def разбить(строка) -> list:
    return [ч.strip() for ч in (строка or "").split(",") if ч.strip()]


def main() -> int:
    разбор = argparse.ArgumentParser(description="Навыки работодателя из файлов сборов")
    разбор.add_argument("--db", default="data/hh_vacancies.db")
    разбор.add_argument("--raw", default="data/raw")
    разбор.add_argument("--сухой-прогон", action="store_true", dest="сухой")
    разбор.add_argument("--yes", action="store_true")
    аргументы = разбор.parse_args()

    база = Path(аргументы.db)
    сырые = Path(аргументы.raw)
    if not база.exists():
        print(f"База не найдена: {база}")
        return 1
    if not сырые.exists():
        print(f"Папка сборов не найдена: {сырые}")
        return 1

    conn = sqlite3.connect(база)
    conn.isolation_level = None

    try:
        колонки = {row[1] for row in conn.execute("PRAGMA table_info(vacancies)")}
        if "employer_skills" not in колонки:
            print("Нет колонки employer_skills. Сначала: "
                  "python scripts/migrations/013_employer_skills.py --yes")
            return 1

        из_файлов = собрать_навыки(сырые)
        print(f"Файлов сборов разобрано: {len(list(сырые.glob('*.json')))}")
        print(f"Вакансий с навыками от работодателя в них: {len(из_файлов)}")

        строки = conn.execute(
            "SELECT vacancy_id, all_skills, employer_skills FROM vacancies"
        ).fetchall()

        к_записи = []
        новых_навыков = 0
        затронуто = 0

        for ид, все_навыки, уже_есть in строки:
            навыки = из_файлов.get(str(ид))
            if not навыки:
                continue

            прежние = разбить(все_навыки)
            известные = {н.lower() for н in прежние}
            добавка = [н for н in навыки if н.lower() not in известные]

            # Пересчёт нужен и когда добавки нет: поле навыков
            # работодателя должно быть заполнено, даже если словарь нашёл
            # то же самое — оно отвечает на вопрос «что сказал источник».
            if not добавка and разбить(уже_есть) == навыки:
                continue

            к_записи.append((
                ", ".join(прежние + добавка),
                ", ".join(навыки),
                len(прежние) + len(добавка),
                ид,
            ))
            новых_навыков += len(добавка)
            затронуто += 1

        print(f"\nЗаписей в базе будет обновлено: {затронуто}")
        print(f"Навыков добавится: {новых_навыков}")

        if аргументы.сухой:
            print("\nСухой прогон. Данные не изменены.")
            if к_записи:
                print("Примеры:")
                for все_н, свои, _, ид in к_записи[:5]:
                    print(f"  {ид}: + {свои}")
            return 0

        if not аргументы.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(
            "UPDATE vacancies SET all_skills = ?, employer_skills = ?, "
            "skill_count = ? WHERE vacancy_id = ?",
            к_записи,
        )
        conn.execute("COMMIT")

        с_навыками = conn.execute(
            "SELECT COUNT(*) FROM vacancies WHERE employer_skills IS NOT NULL "
            "AND employer_skills != ''"
        ).fetchone()[0]
        print(f"\nГотово: навыки работодателя есть у {с_навыками} записей.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
