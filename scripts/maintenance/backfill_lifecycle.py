"""
Уточнение жизненного цикла существующих вакансий по файлам сборов.

Миграция 002 проставила `first_seen_at` по дате публикации — это нижняя
оценка, а не факт. Настоящую дату первой встречи знают файлы в data/raw:
каждый сбор сохранял туда результат, а имя файла несёт запрос и время.

    vacancies_<запрос>_<ГГГГММДД_ЧЧММСС>.json   сбор по одному запросу
    all_vacancies_<ГГГГММДД_ЧЧММСС>.json        сводный файл сбора

Что уточняется:
    first_seen_at   время самого раннего файла, где встречается вакансия
    source_keyword  запросы из имён файлов, где она встречалась
    has_details     было ли у неё описание хотя бы в одном файле

Скрипт только уточняет и не портит: заполненные значения не затираются
худшими, `first_seen_at` двигается лишь назад — вакансия не может
появиться в базе позже, чем её уже видели.

Запуск:
    python scripts/maintenance/backfill_lifecycle.py --dry-run
    python scripts/maintenance/backfill_lifecycle.py --yes
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

FILENAME = re.compile(r"^(?:vacancies_(?P<keyword>.+)|all_vacancies)_(?P<stamp>\d{8}_\d{6})\.json$")


def parse_name(path: Path) -> tuple:
    """(время сбора, запрос) из имени файла; (None, None) — если имя чужое."""
    match = FILENAME.match(path.name)
    if not match:
        return None, None

    try:
        stamp = datetime.strptime(match.group("stamp"), "%Y%m%d_%H%M%S")
    except ValueError:
        return None, None

    keyword = match.group("keyword")
    if keyword:
        # В именах пробелы заменены подчёркиваниями — возвращаем обратно.
        keyword = keyword.replace("_", " ").strip()
    return stamp, keyword


def scan(raw_dir: Path) -> dict:
    """
    Пройти файлы сборов от старых к новым и собрать по каждой вакансии:
    когда её увидели впервые, какими запросами и было ли описание.
    """
    facts: dict = {}
    files = sorted(raw_dir.glob("*.json"), key=lambda p: (parse_name(p)[0] or datetime.max, p.name))
    unreadable = []

    for path in files:
        stamp, keyword = parse_name(path)
        if stamp is None:
            unreadable.append(path.name)
            continue

        try:
            with open(path, encoding="utf-8") as f:
                items = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            unreadable.append(f"{path.name} ({type(e).__name__})")
            continue

        if not isinstance(items, list):
            unreadable.append(f"{path.name} (не список)")
            continue

        for item in items:
            vacancy_id = item.get("id")
            if not vacancy_id:
                continue
            vacancy_id = str(vacancy_id)

            fact = facts.setdefault(
                vacancy_id,
                {"first_seen_at": stamp, "keywords": [], "has_details": False}
            )
            # Файлы отсортированы по времени, но порядок не гарантирован
            # для файлов с одинаковой отметкой — сравниваем явно.
            if stamp < fact["first_seen_at"]:
                fact["first_seen_at"] = stamp
            if keyword and keyword not in fact["keywords"]:
                fact["keywords"].append(keyword)
            if item.get("description"):
                fact["has_details"] = True

    return {"facts": facts, "files": len(files), "unreadable": unreadable}


def apply(conn: sqlite3.Connection, facts: dict, dry_run: bool) -> dict:
    rows = conn.execute(
        "SELECT vacancy_id, first_seen_at, source_keyword, has_details FROM vacancies"
    ).fetchall()

    stats = {"matched": 0, "first_seen_moved": 0, "keywords_set": 0, "details_set": 0}
    updates = []

    for vacancy_id, first_seen_at, source_keyword, has_details in rows:
        fact = facts.get(str(vacancy_id))
        if not fact:
            continue
        stats["matched"] += 1

        new_first_seen = fact["first_seen_at"].strftime("%Y-%m-%d %H:%M:%S")
        # Двигаем только назад: если в базе стоит более ранняя дата, она
        # ближе к истине, чем наша.
        move_first_seen = not first_seen_at or new_first_seen < str(first_seen_at)

        # Порядок запросов задаётся сортировкой, а не тем, какой файл
        # попался раньше: иначе «HR, найм» и «найм, HR» станут разными
        # значениями и рассыплются при группировке.
        keywords = ", ".join(sorted(fact["keywords"]))[:500]
        set_keywords = bool(keywords) and not source_keyword

        set_details = fact["has_details"] and not has_details

        if not (move_first_seen or set_keywords or set_details):
            continue

        if move_first_seen:
            stats["first_seen_moved"] += 1
        if set_keywords:
            stats["keywords_set"] += 1
        if set_details:
            stats["details_set"] += 1

        updates.append({
            "id": vacancy_id,
            "first_seen_at": new_first_seen if move_first_seen else first_seen_at,
            "source_keyword": keywords if set_keywords else source_keyword,
            "has_details": 1 if (set_details or has_details) else 0,
        })

    if not dry_run and updates:
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(
            "UPDATE vacancies SET first_seen_at = :first_seen_at, "
            "source_keyword = :source_keyword, has_details = :has_details "
            "WHERE vacancy_id = :id",
            updates
        )
        conn.execute("COMMIT")

    stats["updated"] = len(updates)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Уточнение жизненного цикла по файлам сборов")
    parser.add_argument("--db", default="data/hh_vacancies.db", help="путь к базе")
    parser.add_argument("--raw", default="data/raw", help="папка с файлами сборов")
    parser.add_argument("--dry-run", action="store_true", help="только показать, что изменится")
    parser.add_argument("--yes", action="store_true", help="применить")
    args = parser.parse_args()

    db_path, raw_dir = Path(args.db), Path(args.raw)
    if not db_path.exists():
        print(f"База не найдена: {db_path}")
        return 1
    if not raw_dir.exists():
        print(f"Папка сборов не найдена: {raw_dir}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.isolation_level = None

    try:
        if "first_seen_at" not in [r[1] for r in conn.execute("PRAGMA table_info(vacancies)")]:
            print("Сначала нужна миграция 002: в таблице нет first_seen_at.")
            return 1

        scanned = scan(raw_dir)
        facts = scanned["facts"]
        print(f"Файлов просмотрено: {scanned['files']}, вакансий в них: {len(facts)}")
        if scanned["unreadable"]:
            print(f"Не разобрано файлов: {len(scanned['unreadable'])}")
            for name in scanned["unreadable"][:5]:
                print(f"  - {name}")

        if not args.dry_run and not args.yes:
            print("\nЗапустите с --yes, чтобы применить, или с --dry-run для проверки.")
            return 1

        stats = apply(conn, facts, dry_run=args.dry_run)

        print(f"\nСовпало с базой: {stats['matched']} вакансий")
        print(f"  дата первой встречи уточнена: {stats['first_seen_moved']}")
        print(f"  запрос проставлен: {stats['keywords_set']}")
        print(f"  признак описания проставлен: {stats['details_set']}")
        print(f"  строк {'изменилось бы' if args.dry_run else 'изменено'}: {stats['updated']}")

        if not args.dry_run:
            earliest = conn.execute("SELECT MIN(first_seen_at) FROM vacancies").fetchone()[0]
            without_keyword = conn.execute(
                "SELECT COUNT(*) FROM vacancies WHERE source_keyword IS NULL OR source_keyword = ''"
            ).fetchone()[0]
            print(f"\nСамая ранняя встреча в базе: {earliest}")
            print(f"Без запроса осталось: {without_keyword}")

        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
