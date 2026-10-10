"""
Восстановление точек истории по прошлым сборам.

Снимки метрик начали сохраняться только сейчас, а история сборов есть с
марта. По датам первой встречи вакансий видно, сколько их было известно
базе на каждую из этих дат, — из этого получаются точки, которых иначе
пришлось бы ждать неделями.

Что считается и что нет:

    вакансии, компании, регионы   считаются: даты первой встречи известны
    медианы зарплат               не считаются: в базе лежит последнее
                                  известное значение зарплаты, истории
                                  значений нет. Приписать мартовскому
                                  снимку сентябрьские зарплаты значило бы
                                  повторить ровно ту подмену, из-за
                                  которой тренды и оказались
                                  недостоверными

Восстановленные снимки помечаются `reconstructed` — по этой пометке
расчёт трендов знает, что зарплатных метрик у них нет.

Запуск:
    python scripts/maintenance/reconstruct_snapshots.py --dry-run
    python scripts/maintenance/reconstruct_snapshots.py --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


def даты_сборов(conn: sqlite3.Connection) -> list:
    """
    По одной точке на день со сборами — последний сбор дня.

    В день бывало по пять сборов подряд, и все они дают одно и то же
    число известных вакансий: точки-близнецы засоряют историю, ничего к
    ней не добавляя. Для динамики важен день, а не каждый запуск.
    """
    строки = conn.execute(
        "SELECT id, момент FROM ("
        "  SELECT id, COALESCE(completed_at, started_at) AS момент,"
        "         ROW_NUMBER() OVER ("
        "           PARTITION BY DATE(COALESCE(completed_at, started_at))"
        "           ORDER BY COALESCE(completed_at, started_at) DESC"
        "         ) AS номер"
        "  FROM parser_runs"
        "  WHERE status = 'completed' AND COALESCE(completed_at, started_at) IS NOT NULL"
        ") WHERE номер = 1 ORDER BY момент"
    ).fetchall()
    return [(run_id, момент) for run_id, момент in строки if момент]


def уже_есть(conn: sqlite3.Connection, момент: str) -> bool:
    """Снимок за этот момент уже сохранён."""
    строка = conn.execute(
        "SELECT 1 FROM metrics_snapshots WHERE taken_at = ? LIMIT 1", (момент,)
    ).fetchone()
    return строка is not None


def посчитать(conn: sqlite3.Connection, момент: str) -> dict:
    """
    Что база знала на этот момент.

    Считаются вакансии, впервые увиденные не позже указанной даты.
    Активность на тот момент неизвестна — признак появился позже, — но
    для счётной метрики это и не нужно: вопрос «сколько вакансий знала
    база» имеет однозначный ответ.
    """
    строка = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT employer_name), COUNT(DISTINCT area) "
        "FROM vacancies WHERE first_seen_at IS NOT NULL AND first_seen_at <= ?",
        (момент,),
    ).fetchone()

    return {
        "total_vacancies": строка[0] or 0,
        "unique_companies": строка[1] or 0,
        "unique_regions": строка[2] or 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Восстановление точек истории")
    parser.add_argument("--db", default="data/hh_vacancies.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"База не найдена: {db_path}")
        return 1

    if not args.dry_run and not args.yes:
        print("Запустите с --dry-run для проверки или с --yes, чтобы применить.")
        return 1

    conn = sqlite3.connect(db_path)
    conn.isolation_level = None

    try:
        сборы = даты_сборов(conn)
        if not сборы:
            print("Успешных сборов в истории нет — восстанавливать нечего.")
            return 0

        новые = []
        for run_id, момент in сборы:
            if уже_есть(conn, момент):
                continue
            значения = посчитать(conn, момент)
            новые.append((run_id, момент, значения))

        print(f"Успешных сборов: {len(сборы)}, точек к восстановлению: {len(новые)}")
        if новые:
            первая, последняя = новые[0][1][:10], новые[-1][1][:10]
            print(f"  период: {первая} — {последняя}")
            print(f"  вакансий в первой точке: {новые[0][2]['total_vacancies']}")
            print(f"  вакансий в последней: {новые[-1][2]['total_vacancies']}")

        if args.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not новые:
            print("Все точки уже на месте.")
            return 0

        conn.execute("BEGIN IMMEDIATE")
        for run_id, момент, значения in новые:
            conn.execute(
                # active_vacancies не заполняется: активность на ту дату
                # неизвестна — признак появился позже, и подставить сюда
                # число всех известных вакансий значило бы выдать догадку
                # за факт.
                # active_vacancies указывается явным NULL: у колонки
                # умолчание 0, а ноль читается как «активных вакансий не
                # было» — это утверждение, которого мы делать не можем.
                "INSERT INTO metrics_snapshots "
                "(taken_at, run_id, source, active_vacancies, total_vacancies, "
                " unique_companies, unique_regions, created_at) "
                "VALUES (?, ?, 'reconstructed', NULL, ?, ?, ?, ?)",
                (
                    момент,
                    run_id,
                    значения["total_vacancies"],
                    значения["unique_companies"],
                    значения["unique_regions"],
                    datetime.now(),
                ),
            )
        conn.execute("COMMIT")

        всего = conn.execute("SELECT COUNT(*) FROM metrics_snapshots").fetchone()[0]
        замеров = conn.execute(
            "SELECT COUNT(*) FROM metrics_snapshots WHERE source = 'measured'"
        ).fetchone()[0]
        print(f"\nВосстановлено точек: {len(новые)}")
        print(f"Всего в таблице: {всего}, из них настоящих замеров: {замеров}")
        print("У восстановленных точек зарплатных метрик нет — это осознанно.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
