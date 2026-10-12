"""
Миграция 022: хранение слоя понимания текста.

Зачем. Модель читает вакансии и достаёт навыки, которых не знает
словарь (группа S10). Её находки нельзя класть туда же, где лежат
навыки словаря: модель не пишет числа в аналитику (решение S9‑6a), и
то, что она нашла, должно быть отличимо от найденного детерминированным
кодом — и сегодня, и через год, после смены модели.

Что делает миграция.

Таблицы:
- `ai_extractions` — что модель уже разобрала: один текст с одной
  версией модели и промпта разбирается один раз;
- `skill_candidates` — очередь на пополнение словаря;
- `skill_candidate_hits` — в каких вакансиях кандидат встречен. По ней
  считаются и число встреч, и число разных работодателей, а повторный
  прогон не увеличивает счётчики.

Колонки `vacancies`:
- `ai_skills` — навыки, найденные моделью, вместе с цитатами (JSON);
- `ai_version` — чем они извлечены: модель, квант, рантайм, промпт.

Номер 013, названный в проекте слоя, занят миграцией навыков
работодателя — отсюда 022.

Запуск:
    python scripts/migrations/022_ai_layer.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/022_ai_layer.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

КОЛОНКИ = {
    "ai_skills": "TEXT",
    "ai_version": "VARCHAR(200)",
}

ТАБЛИЦЫ = {
    "ai_extractions": """
        CREATE TABLE IF NOT EXISTS ai_extractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text_hash VARCHAR(64) NOT NULL,
            model_version VARCHAR(200) NOT NULL,
            prompt_version VARCHAR(100) NOT NULL,
            response TEXT NOT NULL,
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0,
            duration_ms INTEGER DEFAULT 0,
            skills_count INTEGER DEFAULT 0,
            rejected_count INTEGER DEFAULT 0,
            run_tag VARCHAR(40),
            created_at DATETIME NOT NULL,
            UNIQUE (text_hash, model_version, prompt_version)
        )""",
    "skill_candidates": """
        CREATE TABLE IF NOT EXISTS skill_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_key VARCHAR(200) NOT NULL UNIQUE,
            name VARCHAR(200) NOT NULL,
            kind VARCHAR(30),
            status VARCHAR(20) NOT NULL DEFAULT 'new',
            section VARCHAR(20),
            decided_at DATETIME,
            created_at DATETIME NOT NULL
        )""",
    "skill_candidate_hits": """
        CREATE TABLE IF NOT EXISTS skill_candidate_hits (
            name_key VARCHAR(200) NOT NULL,
            vacancy_id VARCHAR(50) NOT NULL,
            employer VARCHAR(500),
            quote VARCHAR(300),
            created_at DATETIME NOT NULL,
            PRIMARY KEY (name_key, vacancy_id)
        )""",
}


def есть_колонка(conn: sqlite3.Connection, таблица: str, имя: str) -> bool:
    return any(строка[1] == имя for строка in conn.execute(f"PRAGMA table_info({таблица})"))


def есть_таблица(conn: sqlite3.Connection, имя: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (имя,)).fetchone() is not None


def применить(conn: sqlite3.Connection) -> None:
    for запрос in ТАБЛИЦЫ.values():
        conn.execute(запрос)
    for имя, тип in КОЛОНКИ.items():
        if not есть_колонка(conn, "vacancies", имя):
            conn.execute(f"ALTER TABLE vacancies ADD COLUMN {имя} {тип}")


def main() -> int:
    разбор = argparse.ArgumentParser(description="Миграция 022: хранение слоя понимания текста")
    разбор.add_argument("--db", required=True, help="путь к базе")
    разбор.add_argument("--dry-run", action="store_true", help="показать, что изменится")
    разбор.add_argument("--yes", action="store_true", help="применить")
    аргументы = разбор.parse_args()

    путь = Path(аргументы.db)
    if not путь.exists():
        print(f"База не найдена: {путь}")
        return 1
    if not аргументы.dry_run and not аргументы.yes:
        print("Нужен --dry-run или --yes.")
        return 2

    conn = sqlite3.connect(путь)
    try:
        новые_таблицы = [имя for имя in ТАБЛИЦЫ if not есть_таблица(conn, имя)]
        новые_колонки = [имя for имя in КОЛОНКИ if not есть_колонка(conn, "vacancies", имя)]
        if not новые_таблицы and not новые_колонки:
            print("Таблицы и колонки уже есть — делать нечего.")
            return 0

        if новые_таблицы:
            print(f"Появятся таблицы: {', '.join(новые_таблицы)}.")
        if новые_колонки:
            print(f"Появятся колонки vacancies: {', '.join(новые_колонки)}.")
        print("Существующие данные не меняются.")
        if аргументы.dry_run:
            print("Сухой прогон: база не тронута.")
            return 0

        копия = путь.parent / "backups" / f"до_022_{datetime.now():%Y%m%d_%H%M}.db"
        копия.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(путь, копия)
        print(f"Копия базы: {копия}")

        with conn:
            применить(conn)
        print("Готово.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
