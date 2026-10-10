"""
Миграция 018: тексты описаний живут в базе.

Зачем. Текст вакансии приходит в карточке, используется на лету для
поиска навыков и выбрасывается: в таблице `vacancies` его нет ни в каком
виде. Единственная копия — сырые файлы сборов, 92 файла на 261 МБ, то
есть 30 КБ на вакансию при среднем описании в 5,8 КБ. Сырьё впятеро
тяжелее того, ради чего его держат.

Без текста в базе невозможны: переразбор при смене правил без обращения
к сети, кэш разбора по хэшу текста (S10‑5a), цитата «как в тексте» под
навыком (S10‑2b) и сравнение объявлений между площадками (S12).

Что добавляется:

- таблица `vacancy_texts` — тело описания, сжатое, по одному экземпляру
  на уникальный текст. Ключ — `text_hash`, а не идентификатор вакансии:
  тридцать одна копия объявления по городам хранит один текст, а не
  тридцать один. Тот же хэш нужен слою понимания как ключ кэша разбора —
  одна сущность вместо двух;
- `simhash` рядом с телом: вход для сравнения объявлений между
  площадками (S12). Считается один раз при записи, а не по всей базе
  потом;
- колонка `text_hash` у вакансии — ссылка на её текст.

Почему HTML, а не очищенный текст: секции описания разбираются по тегам
`<strong|b|h2|h3>`, и подзаголовки есть у 95 % вакансий. Без разметки
переразобрать секции нельзя, а после сжатия она стоит 5 % объёма.

Старые вакансии остаются без текста. Восстанавливать его из сырых файлов
эта миграция не берётся: то отдельная работа со своим бюджетом времени.

Запуск:
    python scripts/migrations/018_vacancy_texts.py --db data/hh_vacancies.db --dry-run
    python scripts/migrations/018_vacancy_texts.py --db data/hh_vacancies.db --yes
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ТАБЛИЦА = """
CREATE TABLE IF NOT EXISTS vacancy_texts (
    -- sha256 от текста: он же ключ дедупликации и ключ кэша разбора
    text_hash   TEXT PRIMARY KEY,
    -- тело, сжатое zlib. Замер: сжатие вчетверо, 5,8 КБ → 1,45 КБ
    body        BLOB NOT NULL,
    -- что именно лежит в теле: html как пришло от источника
    format      TEXT NOT NULL DEFAULT 'html',
    -- отпечаток для сравнения похожих текстов между площадками (S12)
    simhash     INTEGER,
    -- размер до сжатия: по нему видно, растёт ли хранилище
    bytes_raw   INTEGER,
    -- когда получен: текст объявления — снимок на момент сбора,
    -- работодатель правит вакансию, и наш экземпляр стареет
    fetched_at  DATETIME NOT NULL
)
"""

ИНДЕКС = "CREATE INDEX IF NOT EXISTS idx_texts_fetched ON vacancy_texts(fetched_at)"
КОЛОНКА_ВАКАНСИИ = ("text_hash", "TEXT")
ИНДЕКС_ВАКАНСИИ = "CREATE INDEX IF NOT EXISTS idx_vacancies_text ON vacancies(text_hash)"


def таблицы(conn: sqlite3.Connection) -> set:
    return {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}


def есть_колонка(conn: sqlite3.Connection, таблица: str, имя: str) -> bool:
    return имя in {row[1] for row in conn.execute(f"PRAGMA table_info({таблица})")}


def бэкап(db_path: Path) -> Path:
    """
    Копия базы перед изменением схемы.

    Не осторожность ради осторожности: однажды сбор уже стёр базу
    целиком, и с тех пор в проекте правило — перед миграцией копия.
    """
    метка = datetime.now().strftime("%Y%m%d_%H%M%S")
    куда = db_path.parent / "backups" / f"{db_path.stem}_до_018_{метка}.db"
    куда.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, куда)
    return куда


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция 018: тексты описаний в базе")
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
        если_есть = таблицы(conn)
        if "vacancies" not in если_есть:
            print("Таблицы vacancies нет — не та база.")
            return 1

        нужна_таблица = "vacancy_texts" not in если_есть
        нужна_колонка = not есть_колонка(conn, "vacancies", КОЛОНКА_ВАКАНСИИ[0])

        if not нужна_таблица and not нужна_колонка:
            print(f"{db_path}: миграция 018 уже применена.")
            return 0

        всего = conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]
        print(f"База: {db_path}")
        if нужна_таблица:
            print("  появится таблица vacancy_texts: тело, формат, отпечаток, размер, дата")
        if нужна_колонка:
            print("  у вакансии появится ссылка text_hash")
        print(f"  вакансий в базе: {всего} — останутся без текста, "
              "он появится у собранных заново")

        if args.dry_run:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not args.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        куда = бэкап(db_path)
        print(f"\nКопия базы: {куда}")

        conn.execute("BEGIN IMMEDIATE")
        if нужна_таблица:
            conn.execute(ТАБЛИЦА)
            conn.execute(ИНДЕКС)
        if нужна_колонка:
            conn.execute(
                f"ALTER TABLE vacancies ADD COLUMN {КОЛОНКА_ВАКАНСИИ[0]} {КОЛОНКА_ВАКАНСИИ[1]}"
            )
        conn.execute(ИНДЕКС_ВАКАНСИИ)
        conn.execute("COMMIT")

        print("Готово: текст описания теперь есть где хранить.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
