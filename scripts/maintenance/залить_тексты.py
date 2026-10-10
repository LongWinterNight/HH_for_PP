"""
Залить в базу тексты описаний из сырых файлов.

Зачем. Текст описания пишется в базу с 10.10.2026; у вакансий,
собранных раньше, его нет — только ссылки нет и самого текста. Сырые
ответы источника при этом лежат в `data/raw`, и описание в них есть у
каждой вакансии, по которой запрашивалась карточка. Без текста по
вакансии нельзя искать и её нельзя переразобрать.

Текст кладётся тем же кодом, что и при сборе (`texts.подготовить`):
один экземпляр на текст, ссылка у вакансии — по хэшу. Вакансия, у
которой ссылка уже есть, не трогается: её текст — снимок на момент
получения, и переписать его значило бы задним числом изменить то, по
чему посчитаны навыки.

Запуск:
    python scripts/maintenance/залить_тексты.py --сухой-прогон
    python scripts/maintenance/залить_тексты.py --yes
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import texts  # noqa: E402
from src.config import settings  # noqa: E402

from дозаполнить_график import вакансии_из_файла  # noqa: E402


def описания_из_сырья(папка: Path) -> Dict[str, str]:
    """Описание по идентификатору вакансии; поздний файл перекрывает ранний."""
    найденное: Dict[str, str] = {}
    for путь in sorted(папка.glob("*.json"), key=lambda p: p.stat().st_mtime):
        for вакансия in вакансии_из_файла(путь):
            if isinstance(вакансия, dict) and вакансия.get("id") and (вакансия.get("description") or "").strip():
                найденное[str(вакансия["id"])] = вакансия["description"]
    return найденное


def main() -> int:
    разбор = argparse.ArgumentParser(description="Залить в базу тексты описаний из сырых файлов")
    разбор.add_argument("--сухой-прогон", action="store_true", help="показать, что изменится, и ничего не писать")
    разбор.add_argument("--yes", action="store_true", help="записать")
    аргументы = разбор.parse_args()

    if not аргументы.сухой_прогон and not аргументы.yes:
        print("Нужен --сухой-прогон или --yes: без одного из них скрипт ничего не делает.")
        return 2

    сырьё = описания_из_сырья(settings.raw_data_dir)
    print(f"Описаний в сырье: {len(сырьё)}")

    база = sqlite3.connect(settings.db_path)
    try:
        без_текста = [str(строка[0]) for строка in база.execute(
            "SELECT vacancy_id FROM vacancies WHERE text_hash IS NULL OR text_hash = ''"
        )]
        уже = {строка[0] for строка in база.execute("SELECT text_hash FROM vacancy_texts")}
        print(f"Вакансий без текста: {len(без_текста)}")

        новые_тексты, ссылки = {}, []
        for ид in без_текста:
            описание = сырьё.get(ид)
            if not описание:
                continue
            подготовленное = texts.подготовить(описание)
            if not подготовленное:
                continue
            хэш, тело, отпечаток, размер = подготовленное
            if хэш not in уже and хэш not in новые_тексты:
                новые_тексты[хэш] = (хэш, тело, texts.в_поле(отпечаток), размер)
            ссылки.append((хэш, ид))

        объём = sum(len(запись[1]) for запись in новые_тексты.values())
        print(f"Получат текст: {len(ссылки)} вакансий; новых текстов {len(новые_тексты)} "
              f"({len(ссылки) - len(новые_тексты)} — копии уже известного), {объём / 1e6:.1f} МБ после сжатия")
        print(f"Останутся без текста: {len(без_текста) - len(ссылки)} — в сырье их описания нет")

        if аргументы.сухой_прогон or not ссылки:
            print("Сухой прогон: база не тронута." if аргументы.сухой_прогон else "Править нечего.")
            return 0

        копия = settings.db_path.parent / "backups" / f"до_текстов_{datetime.now():%Y%m%d_%H%M}.db"
        копия.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(settings.db_path, копия)
        print(f"Копия базы: {копия}")

        сейчас = datetime.now().isoformat(sep=" ")
        with база:
            база.executemany(
                "INSERT INTO vacancy_texts (text_hash, body, format, simhash, bytes_raw, fetched_at) "
                "VALUES (?, ?, 'html', ?, ?, ?)",
                [(*запись, сейчас) for запись in новые_тексты.values()],
            )
            база.executemany("UPDATE vacancies SET text_hash = ? WHERE vacancy_id = ?", ссылки)
        print(f"Записано: текстов {len(новые_тексты)}, ссылок {len(ссылки)}")
        return 0
    finally:
        база.close()


if __name__ == "__main__":
    sys.exit(main())
