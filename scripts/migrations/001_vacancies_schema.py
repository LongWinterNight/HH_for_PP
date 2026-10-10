"""
Миграция 001: привести таблицу vacancies к схеме ORM.

Зачем. Таблицу создавал pandas через to_sql: колонка id хранит копию
vacancy_id строкой, первичного ключа нет, уникальности по vacancy_id нет,
индексов нет ни одного, а объявленных в VacancyModel колонок applied_at,
salary_gross, created_at и updated_at в базе не существует. Из-за этого
save_vacancies_incremental() — единственный путь записи, который не стирает
базу, — падает на первом же обращении к отсутствующей колонке, а upsert без
уникального индекса невозможен в принципе.

SQLite не умеет ни добавлять первичный ключ, ни менять тип колонки через
ALTER TABLE. Поэтому таблица пересоздаётся: новая схема, перенос данных,
подмена имени. Это стандартный для SQLite приём, и он же единственный.

Миграция идемпотентна: повторный запуск на уже переведённой базе ничего не
делает и сообщает об этом.

Запуск:
    python scripts/migrations/001_vacancies_schema.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/001_vacancies_schema.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Схема повторяет VacancyModel из src/storage.py. Порядок колонок — как в
# модели: файл читают рядом с ней, и расхождение в порядке заставляет
# сверять глазами то, что должно совпадать построчно.
TARGET_DDL = """
CREATE TABLE vacancies_migrated (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vacancy_id VARCHAR(50) NOT NULL,
    vacancy_name VARCHAR(500) NOT NULL,
    published_at DATETIME,
    applied_at DATETIME,
    all_skills TEXT,
    hard_skills TEXT,
    soft_skills TEXT,
    tools TEXT,
    skill_count INTEGER DEFAULT 0,
    hard_skill_count INTEGER DEFAULT 0,
    soft_skill_count INTEGER DEFAULT 0,
    tools_count INTEGER DEFAULT 0,
    salary_from FLOAT,
    salary_to FLOAT,
    salary_currency VARCHAR(10) DEFAULT 'RUB',
    salary_gross BOOLEAN DEFAULT 0,
    employer_name VARCHAR(300),
    employer_id VARCHAR(50),
    employer_url VARCHAR(500),
    vacancy_url VARCHAR(500),
    experience VARCHAR(100),
    employment VARCHAR(100),
    schedule VARCHAR(100),
    area VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME
)
"""

# Имя уникального индекса выбрано не произвольно: SQLAlchemy для
# Column(unique=True, index=True) создаёт ровно ix_<таблица>_<колонка>.
# Назови его иначе — и первый же create_all() добавит рядом второй индекс
# по тому же полю.
INDEXES = [
    ("ix_vacancies_vacancy_id", "vacancies(vacancy_id)", True),
    ("idx_employer", "vacancies(employer_name)", False),
    ("idx_area", "vacancies(area)", False),
    ("idx_published_at", "vacancies(published_at)", False),
    ("idx_experience", "vacancies(experience)", False),
    ("idx_salary_from", "vacancies(salary_from)", False),
    ("idx_created_at", "vacancies(created_at)", False),
    ("idx_salary_currency", "vacancies(salary_currency)", False),
]

# Колонки, которые переносятся один в один из старой таблицы.
CARRIED_COLUMNS = [
    "vacancy_id",
    "vacancy_name",
    "published_at",
    "all_skills",
    "hard_skills",
    "soft_skills",
    "tools",
    "skill_count",
    "hard_skill_count",
    "soft_skill_count",
    "tools_count",
    "salary_from",
    "salary_to",
    "salary_currency",
    "employer_name",
    "employer_id",
    "employer_url",
    "vacancy_url",
    "experience",
    "employment",
    "schedule",
    "area",
]


def columns_of(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def indexes_of(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA index_list({table})")]


def already_migrated(conn: sqlite3.Connection) -> bool:
    cols = columns_of(conn, "vacancies")
    return "created_at" in cols and "ix_vacancies_vacancy_id" in indexes_of(conn, "vacancies")


def inspect(conn: sqlite3.Connection) -> dict:
    """Что есть в базе до миграции — это же печатается при --dry-run."""
    total = conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]
    duplicates = conn.execute(
        "SELECT COUNT(*) FROM (SELECT vacancy_id FROM vacancies "
        "GROUP BY vacancy_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    empty_id = conn.execute(
        "SELECT COUNT(*) FROM vacancies WHERE vacancy_id IS NULL OR vacancy_id = ''"
    ).fetchone()[0]
    empty_name = conn.execute(
        "SELECT COUNT(*) FROM vacancies WHERE vacancy_name IS NULL OR vacancy_name = ''"
    ).fetchone()[0]
    return {
        "total": total,
        "duplicates": duplicates,
        "empty_id": empty_id,
        "empty_name": empty_name,
        "columns": columns_of(conn, "vacancies"),
        "indexes": indexes_of(conn, "vacancies"),
    }


def migrate(conn: sqlite3.Connection) -> dict:
    """
    Перенос данных в новую схему.

    created_at существующим записям ставится временем миграции: когда они
    на самом деле попали в базу, неизвестно — прежняя схема этого не
    хранила. Придумывать дату по published_at было бы хуже: это разные
    величины, и одна начала бы выдавать себя за другую. Точное «когда
    впервые увидели» восстанавливается отдельной задачей из data/raw.
    """
    carried = ", ".join(CARRIED_COLUMNS)

    conn.execute("BEGIN IMMEDIATE")
    conn.execute(TARGET_DDL)

    # MAX(rowid) на случай дублей: при равных vacancy_id остаётся строка,
    # записанная последней. Сейчас дублей нет, но миграция не должна
    # зависеть от состояния конкретной базы.
    conn.execute(
        f"""
        INSERT INTO vacancies_migrated ({carried}, created_at, updated_at)
        SELECT {carried}, datetime('now'), datetime('now')
        FROM vacancies
        WHERE rowid IN (SELECT MAX(rowid) FROM vacancies GROUP BY vacancy_id)
          AND vacancy_id IS NOT NULL AND vacancy_id != ''
        """
    )
    moved = conn.execute("SELECT COUNT(*) FROM vacancies_migrated").fetchone()[0]

    conn.execute("DROP TABLE vacancies")
    conn.execute("ALTER TABLE vacancies_migrated RENAME TO vacancies")

    for name, target, unique in INDEXES:
        conn.execute(f"CREATE {'UNIQUE ' if unique else ''}INDEX {name} ON {target}")

    conn.execute("COMMIT")
    return {"moved": moved}


def verify(conn: sqlite3.Connection, expected: int) -> list[str]:
    """Проверки после миграции. Пустой список — всё сошлось."""
    problems: list[str] = []

    total = conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]
    if total != expected:
        problems.append(f"строк {total}, ожидалось {expected}")

    cols = columns_of(conn, "vacancies")
    for required in ("applied_at", "salary_gross", "created_at", "updated_at"):
        if required not in cols:
            problems.append(f"нет колонки {required}")

    idx = indexes_of(conn, "vacancies")
    for name, _, _ in INDEXES:
        if name not in idx:
            problems.append(f"нет индекса {name}")

    # Уникальность проверяется не наличием индекса, а поведением: вставка
    # существующего vacancy_id обязана быть отвергнута.
    sample = conn.execute("SELECT vacancy_id FROM vacancies LIMIT 1").fetchone()
    if sample:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT INTO vacancies (vacancy_id, vacancy_name) VALUES (?, ?)",
                (sample[0], "проверка уникальности"),
            )
            problems.append("дубль vacancy_id вставился — уникальности нет")
        except sqlite3.IntegrityError:
            pass
        finally:
            # Проверочная вставка не должна оставить следа независимо от
            # исхода: откат нужен и когда она прошла, и когда была отвергнута.
            conn.execute("ROLLBACK")

    if conn.execute("SELECT COUNT(*) FROM vacancies WHERE created_at IS NULL").fetchone()[0]:
        problems.append("есть записи с пустым created_at")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 001: схема таблицы vacancies")
    parser.add_argument("--db", default="data/hh_vacancies.db", help="путь к базе")
    parser.add_argument("--dry-run", action="store_true", help="только показать, что будет сделано")
    parser.add_argument("--yes", action="store_true", help="выполнить без вопроса")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"База не найдена: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.isolation_level = None  # транзакциями управляем сами

    try:
        if already_migrated(conn):
            print(f"{db_path}: миграция 001 уже применена, делать нечего.")
            return 0

        state = inspect(conn)
        print(f"База: {db_path}")
        print(f"  строк: {state['total']}")
        print(f"  дублей vacancy_id: {state['duplicates']}")
        print(f"  записей без vacancy_id: {state['empty_id']}")
        print(f"  записей без названия: {state['empty_name']}")
        print(f"  колонок сейчас: {len(state['columns'])}, индексов: {len(state['indexes'])}")
        print(f"  станет колонок: 27, индексов: {len(INDEXES)}")

        if state["empty_name"]:
            print("\nОстановка: vacancy_name объявлен NOT NULL, а пустые названия есть.")
            print("Разберитесь с этими записями до миграции.")
            return 1

        expected = state["total"] - state["duplicates"] - state["empty_id"]

        if args.dry_run:
            print(f"\nСухой прогон. Перенеслось бы записей: {expected}")
            return 0

        if not args.yes:
            print("\nЗапустите с --yes, чтобы применить. Копию базы сделайте заранее.")
            return 1

        result = migrate(conn)
        print(f"\nПеренесено записей: {result['moved']}")

        problems = verify(conn, expected)
        if problems:
            print("Проверки не прошли:")
            for p in problems:
                print(f"  - {p}")
            return 1

        print("Проверки пройдены: колонки, индексы, уникальность, заполненность created_at.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
