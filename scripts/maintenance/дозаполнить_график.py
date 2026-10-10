"""
Дозаполнить занятость и график у вакансий, собранных с пустыми полями.

Зачем. Источник убрал поля `employment` и `schedule` и отдаёт вместо
них `employment_form`, `work_format` и `work_schedule_by_days`. Сбор
этого не заметил: поля были необязательными, и у тысяч вакансий
занятость и график молча опустели. Сбор теперь читает новые поля, но
собранное раньше осталось пустым.

Сырые ответы источника лежат в `data/raw` и новые поля несут — значит,
спрашивать источник заново не нужно. Здесь значения читаются из сырья
тем же кодом, что и при сборе, и пишутся только туда, где пусто:
заполненное не переписывается.

Вакансии, которых в сырье нет, остаются пустыми, и их число печатается:
«не указан» у них — правда, а не недоработка.

Запуск:
    python scripts/maintenance/дозаполнить_график.py --сухой-прогон
    python scripts/maintenance/дозаполнить_график.py --yes
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import settings  # noqa: E402
from src.sources.hh import в_общую_запись  # noqa: E402


def вакансии_из_файла(путь: Path) -> Iterable[dict]:
    """Вакансии сырого файла: список либо словарь со списком внутри."""
    try:
        данные = json.loads(путь.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(данные, list):
        return данные
    if isinstance(данные, dict):
        for значение in данные.values():
            if isinstance(значение, list):
                return значение
    return []


def прочитать_сырьё(папка: Path) -> Dict[str, Tuple[str, str]]:
    """
    Занятость и график по идентификатору вакансии.

    Файлы читаются от старых к новым: поздний ответ источника
    перекрывает ранний, но только непустым значением.
    """
    найденное: Dict[str, Tuple[str, str]] = {}
    for путь in sorted(папка.glob("*.json"), key=lambda p: p.stat().st_mtime):
        for вакансия in вакансии_из_файла(путь):
            if not isinstance(вакансия, dict) or not вакансия.get("id"):
                continue
            запись = в_общую_запись(вакансия)
            ид = str(вакансия["id"])
            прежняя = найденное.get(ид, ("", ""))
            найденное[ид] = (
                запись["занятость"] or прежняя[0],
                запись["график"] or прежняя[1],
            )
    return найденное


def main() -> int:
    разбор = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    разбор.add_argument("--сухой-прогон", action="store_true", help="показать, что изменится, и ничего не писать")
    разбор.add_argument("--yes", action="store_true", help="записать изменения")
    аргументы = разбор.parse_args()

    if not аргументы.сухой_прогон and not аргументы.yes:
        print("Нужен --сухой-прогон или --yes: без одного из них скрипт ничего не делает.")
        return 2

    сырьё = прочитать_сырьё(settings.raw_data_dir)
    print(f"В сырье: {len(сырьё)} вакансий")

    база = sqlite3.connect(settings.db_path)
    try:
        пустые = база.execute(
            "SELECT vacancy_id, COALESCE(employment, ''), COALESCE(schedule, '') FROM vacancies "
            "WHERE COALESCE(employment, '') = '' OR COALESCE(schedule, '') = ''"
        ).fetchall()
        print(f"В базе с пустой занятостью или графиком: {len(пустые)}")

        правки = []
        нет_в_сырье = 0
        for ид, занятость, график in пустые:
            найдено = сырьё.get(str(ид))
            if not найдено:
                нет_в_сырье += 1
                continue
            # Заполненное не переписывается: пишем только туда, где пусто.
            новая_занятость = занятость or найдено[0]
            новый_график = график or найдено[1]
            if (новая_занятость, новый_график) != (занятость, график):
                правки.append((новая_занятость, новый_график, ид))

        print(f"Будет дозаполнено: {len(правки)}")
        print(f"Нет в сырье, останутся пустыми: {нет_в_сырье}")
        print(f"Есть в сырье, но источник и там ничего не сказал: {len(пустые) - нет_в_сырье - len(правки)}")
        for занятость, график, ид in правки[:5]:
            print(f"  {ид}: занятость «{занятость}», график «{график}»")

        if аргументы.сухой_прогон or not правки:
            print("Сухой прогон: база не тронута." if аргументы.сухой_прогон else "Править нечего.")
            return 0

        копия = settings.db_path.parent / "backups" / f"до_графика_{datetime.now():%Y%m%d_%H%M}.db"
        копия.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(settings.db_path, копия)
        print(f"Копия базы: {копия}")

        with база:
            база.executemany("UPDATE vacancies SET employment = ?, schedule = ? WHERE vacancy_id = ?", правки)
        print(f"Записано: {len(правки)}")
        return 0
    finally:
        база.close()


if __name__ == "__main__":
    sys.exit(main())
