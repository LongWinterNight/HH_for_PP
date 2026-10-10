"""
Восстановление истории вакансий из файлов прошлых сборов.

Пока запись в базу заменяла таблицу целиком, каждый сбор стирал
собранное раньше (см. запись 12 в docs/data-issues.md). Но сами данные
никуда не делись: каждый сбор сохранял результат в data/raw, и там лежит
в разы больше вакансий, чем осталось в базе.

Скрипт разбирает эти файлы и возвращает потерянное:

    first_seen_at   время самого раннего файла, где вакансия встречается
    last_seen_at    время самого позднего
    source_keyword  запросы из имён файлов
    is_active       0 — восстановленная вакансия считается закрытой,
                    пока её не подтвердит живой сбор

Последнее — главное правило восстановления. Вакансия из мартовского
файла почти наверняка давно снята с публикации; попав в базу активной,
она вошла бы в медианы зарплат и в «топ навыков», то есть текущий рынок
описывался бы мёртвыми вакансиями. Поэтому архив приходит погашенным, а
правила слияния в хранилище устроены так, что живые записи от этого не
пострадают: активность понижается только записью более свежей, чем та,
что уже в базе.

Проверка после прогона: числа на экранах продукта не должны измениться
ни на единицу — там показываются активные вакансии.

Запуск:
    python scripts/maintenance/restore_from_raw.py --dry-run
    python scripts/maintenance/restore_from_raw.py --yes
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.normalize import SkillDictionaries, normalize_many  # noqa: E402
from src.storage import VacancyStorage  # noqa: E402

FILENAME = re.compile(r"^(?:vacancies_(?P<keyword>.+)|all_vacancies)_(?P<stamp>\d{8}_\d{6})\.json$")

# Пачка записи. Больше — дольше держится транзакция, меньше — больше
# накладных расходов на каждую пачку.
BATCH = 1000


def parse_name(path: Path) -> tuple:
    """(время сбора, запрос) из имени файла."""
    match = FILENAME.match(path.name)
    if not match:
        return None, None
    try:
        stamp = datetime.strptime(match.group("stamp"), "%Y%m%d_%H%M%S")
    except ValueError:
        return None, None
    keyword = match.group("keyword")
    if keyword:
        keyword = keyword.replace("_", " ").strip()
    return stamp, keyword


def collect(raw_dir: Path) -> dict:
    """
    Собрать по каждой вакансии всё, что известно из файлов.

    Вакансия из тридцати файлов разбирается один раз: нормализация с
    поиском навыков — самая дорогая часть работы, и повторять её для
    каждого вхождения незачем. Данные берутся из самого позднего файла
    (там свежее зарплата и статус), даты — из крайних.
    """
    facts: dict = {}
    skipped_files = []

    files = sorted(raw_dir.glob("*.json"), key=lambda p: (parse_name(p)[0] or datetime.max, p.name))

    for path in files:
        stamp, keyword = parse_name(path)
        if stamp is None:
            skipped_files.append(path.name)
            continue

        try:
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            skipped_files.append(f"{path.name} ({type(e).__name__})")
            continue

        if not isinstance(items, list):
            skipped_files.append(f"{path.name} (не список)")
            continue

        for item in items:
            vacancy_id = item.get("id")
            if not vacancy_id:
                continue
            vacancy_id = str(vacancy_id)

            fact = facts.get(vacancy_id)
            if fact is None:
                facts[vacancy_id] = {
                    "first_seen_at": stamp,
                    "last_seen_at": stamp,
                    "keywords": [keyword] if keyword else [],
                    "raw": item,
                }
                continue

            if stamp < fact["first_seen_at"]:
                fact["first_seen_at"] = stamp
            if stamp >= fact["last_seen_at"]:
                fact["last_seen_at"] = stamp
                # Данные берём из более позднего файла, но описание не
                # теряем: карточка с описанием ценнее свежей строки без
                # него — по описанию ищутся навыки.
                if item.get("description") or not fact["raw"].get("description"):
                    fact["raw"] = item
            if keyword and keyword not in fact["keywords"]:
                fact["keywords"].append(keyword)

    return {"facts": facts, "files": len(files), "skipped": skipped_files}


def to_frame(facts: dict, dictionaries: SkillDictionaries) -> pd.DataFrame:
    """Нормализовать собранное и добавить поля жизненного цикла."""
    raws = []
    for vacancy_id, fact in facts.items():
        raw = dict(fact["raw"])
        raw["_source_keyword"] = ", ".join(sorted(fact["keywords"])) or None
        raws.append(raw)

    rows = normalize_many(raws, dictionaries)

    for row, fact in zip(rows, facts.values()):
        row["first_seen_at"] = fact["first_seen_at"]
        row["last_seen_at"] = fact["last_seen_at"]
        # Восстановленная вакансия считается закрытой, пока живой сбор не
        # подтвердит обратное.
        row["is_active"] = False

    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Восстановление истории из файлов сборов")
    parser.add_argument("--db", default="data/hh_vacancies.db", help="путь к базе")
    parser.add_argument("--raw", default="data/raw", help="папка с файлами сборов")
    parser.add_argument("--dry-run", action="store_true", help="разобрать файлы, но не писать")
    parser.add_argument("--yes", action="store_true", help="применить")
    args = parser.parse_args()

    db_path, raw_dir = Path(args.db), Path(args.raw)
    if not db_path.exists():
        print(f"База не найдена: {db_path}")
        return 1
    if not raw_dir.exists():
        print(f"Папка сборов не найдена: {raw_dir}")
        return 1

    if not args.dry_run and not args.yes:
        print("Запустите с --dry-run для проверки или с --yes, чтобы применить.")
        return 1

    started = datetime.now()
    print("Разбор файлов…")
    collected = collect(raw_dir)
    facts = collected["facts"]

    print(f"  файлов: {collected['files']}, различных вакансий: {len(facts)}")
    if collected["skipped"]:
        print(f"  пропущено файлов: {len(collected['skipped'])}")
        for name in collected["skipped"][:5]:
            print(f"    - {name}")

    if not facts:
        print("Восстанавливать нечего.")
        return 0

    dates = [f["first_seen_at"] for f in facts.values()]
    print(f"  период: {min(dates):%d.%m.%Y} — {max(dates):%d.%m.%Y}")

    storage = VacancyStorage(db_path=db_path)
    try:
        before = storage.get_all_vacancies(include_inactive=True)
        active_before = len(storage.get_all_vacancies())
        print(f"  в базе сейчас: {len(before)} записей, из них активных {active_before}")

        known = set(before["vacancy_id"].astype(str)) if not before.empty else set()
        new_ids = set(facts) - known
        print(f"  новых для базы: {len(new_ids)}")

        if args.dry_run:
            print(f"\nСухой прогон. Разбор занял {(datetime.now() - started).seconds} с.")
            return 0

        print("\nНормализация…")
        dictionaries = SkillDictionaries.from_config()
        df = to_frame(facts, dictionaries)

        print(f"Запись {len(df)} записей пачками по {BATCH}…")
        totals = {"inserted": 0, "updated": 0, "skipped": 0}
        for start in range(0, len(df), BATCH):
            chunk = df.iloc[start:start + BATCH]
            stats = storage.save_vacancies_incremental(chunk)
            for key in totals:
                totals[key] += stats[key]
            print(f"  {min(start + BATCH, len(df))}/{len(df)}")

        active_after = len(storage.get_all_vacancies())
        total_after = len(storage.get_all_vacancies(include_inactive=True))
        earliest = storage.get_all_vacancies(include_inactive=True)["first_seen_at"].min()

        print(f"\nДобавлено: {totals['inserted']}, обновлено: {totals['updated']}")
        print(f"В базе стало: {total_after} записей, активных {active_after}")
        print(f"Самая ранняя встреча: {earliest}")

        if active_after != active_before:
            print(
                f"\nВНИМАНИЕ: число активных вакансий изменилось "
                f"({active_before} → {active_after}). Восстановление истории не должно "
                f"менять текущую картину — проверьте правила слияния."
            )
            return 1

        print("\nЧисло активных вакансий не изменилось — текущие экраны показывают то же, что и до.")
        print(f"Заняло {(datetime.now() - started).seconds} с.")
        return 0

    finally:
        storage.close()


if __name__ == "__main__":
    sys.exit(main())
