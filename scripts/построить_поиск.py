"""
Построить индексы поиска по базе вакансий.

Зачем. Поиск по словам и по смыслу живёт в собственных таблицах базы.
Сбор дописывает в них новые вакансии сам, но первую постройку, смену
модели векторов и восстановление после полной перезаписи базы делает
эта команда.

Запуск:
    python scripts/построить_поиск.py                # слова и векторы
    python scripts/построить_поиск.py --без-векторов # только слова
    python scripts/построить_поиск.py --модель intfloat/multilingual-e5-base
    python scripts/построить_поиск.py --скачать      # скачать модель и выйти
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.search import lexical, vectors  # noqa: E402
from src.search.индексация import документы  # noqa: E402

ФАЙЛЫ_МОДЕЛИ = ["config.json", "tokenizer*", "sentencepiece*", "special_tokens_map.json",
                "model.safetensors", "pytorch_model.bin"]


def скачать(модель: str) -> int:
    from huggingface_hub import snapshot_download

    путь = snapshot_download(модель, allow_patterns=ФАЙЛЫ_МОДЕЛИ)
    print(f"Модель на диске: {путь}")
    return 0


def main() -> int:
    разбор = argparse.ArgumentParser(description="Построить индексы поиска")
    разбор.add_argument("--без-векторов", action="store_true", help="только поиск по словам")
    разбор.add_argument("--модель", default=None, help="модель векторов (по умолчанию SEARCH_MODEL)")
    разбор.add_argument("--скачать", action="store_true", help="скачать модель векторов и выйти")
    аргументы = разбор.parse_args()

    модель = аргументы.модель or vectors.имя_модели()
    if аргументы.скачать:
        return скачать(модель)

    conn = sqlite3.connect(settings.db_path)
    try:
        начало = time.time()
        набор = документы(conn)
        print(f"Вакансий в базе: {len(набор)}, с описанием: {sum(1 for д in набор if д.описание)}")

        записано = lexical.записать(conn, набор)
        conn.commit()
        print(f"Поиск по словам: {записано} документов, {len(lexical.словарь(conn).частоты)} слов "
              f"за {time.time() - начало:.0f} с")

        if аргументы.без_векторов:
            return 0

        начало = time.time()
        try:
            исход = vectors.досчитать(conn, набор, vectors.ЛокальнаяМодель(модель), модель)
        except vectors.МодельНедоступна as ошибка:
            print(f"Векторы не посчитаны: {ошибка}")
            print(f"Скачать модель: python scripts/построить_поиск.py --скачать --модель {модель}")
            return 1
        print(f"Поиск по смыслу ({модель}): посчитано {исход['посчитано']}, "
              f"без изменений {исход['без_изменений']} за {time.time() - начало:.0f} с")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
