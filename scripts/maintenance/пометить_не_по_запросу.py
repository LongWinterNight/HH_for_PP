"""
Пометить вакансии, найденные не по запросу.

Зачем. До 10.10.2026 источник искал слова запроса во всех полях,
включая название компании: по «Арт-директор» пришла 331 вакансия
ресторанов работодателя «АРТ РЕСТ». Сбор теперь ищет только в названии
и описании, но собранное раньше осталось в базе и входит в медианы и
частоты навыков.

Вакансии помечаются, а не удаляются: аналитика и список их пропускают,
из базы они не исчезают. Правило сопоставления приближённое
(`src/relevance.py`), и пометку можно пересчитать после его правки —
повторный запуск снимает её там, где правило передумало.

Текст для суждения берётся из базы, а где его нет — из сырых файлов.
Помечается только доказанная причина: слов запроса нет в самой
вакансии, зато они есть в названии компании. Вакансии, где слов нет
нигде, остаются без пометки: чаще всего источник подставил синоним
(«Разработчик» — «Java Backend Developer»), и их число печатается.

Запуск:
    python scripts/maintenance/пометить_не_по_запросу.py --сухой-прогон
    python scripts/maintenance/пометить_не_по_запросу.py --yes
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import zlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import settings  # noqa: E402
from src.relevance import не_по_запросу  # noqa: E402

from дозаполнить_график import вакансии_из_файла  # noqa: E402


def тексты_из_сырья(папка: Path) -> Dict[str, Tuple[str, str]]:
    """Описание и отрывок выдачи по идентификатору вакансии."""
    найденное: Dict[str, Tuple[str, str]] = {}
    for путь in sorted(папка.glob("*.json"), key=lambda p: p.stat().st_mtime):
        for вакансия in вакансии_из_файла(путь):
            if not isinstance(вакансия, dict) or not вакансия.get("id"):
                continue
            отрывок = вакансия.get("snippet") or {}
            кусок = " ".join(filter(None, [отрывок.get("requirement"), отрывок.get("responsibility")]))
            прежнее = найденное.get(str(вакансия["id"]), ("", ""))
            найденное[str(вакансия["id"])] = (
                вакансия.get("description") or прежнее[0],
                кусок or прежнее[1],
            )
    return найденное


def main() -> int:
    разбор = argparse.ArgumentParser(description="Пометить вакансии, найденные не по запросу")
    разбор.add_argument("--сухой-прогон", action="store_true", help="показать, что изменится, и ничего не писать")
    разбор.add_argument("--yes", action="store_true", help="записать пометки")
    аргументы = разбор.parse_args()

    if not аргументы.сухой_прогон and not аргументы.yes:
        print("Нужен --сухой-прогон или --yes: без одного из них скрипт ничего не делает.")
        return 2

    сырьё = тексты_из_сырья(settings.raw_data_dir)
    база = sqlite3.connect(settings.db_path)
    try:
        строки = база.execute(
            """
            SELECT v.vacancy_id, v.source_keyword, v.vacancy_name, COALESCE(v.employer_name, ''),
                   COALESCE(v.all_skills, '') || ' ' || COALESCE(v.employer_skills, ''),
                   t.body, COALESCE(v.off_query, 0)
            FROM vacancies v LEFT JOIN vacancy_texts t ON t.text_hash = v.text_hash
            """
        ).fetchall()

        поставить, снять = [], []
        по_запросам: Dict[str, Counter] = defaultdict(Counter)
        итог: Counter = Counter()

        for ид, запрос, название, компания, навыки, тело, помечена in строки:
            из_сырья = сырьё.get(str(ид), ("", ""))
            описание = zlib.decompress(тело).decode("utf-8") if тело else из_сырья[0]
            решение = не_по_запросу(запрос, название, навыки, описание, из_сырья[1], компания)

            п = по_запросам[запрос or "—"]
            п["всего"] += 1
            if решение is None:
                итог["неизвестно"] += 1
                п["неизвестно"] += 1
            elif решение:
                итог["не по запросу"] += 1
                п["не по запросу"] += 1
            else:
                итог["по запросу"] += 1

            # «Неизвестно» пометку не ставит и не снимает: судить не по чему.
            if решение is True and not помечена:
                поставить.append((ид,))
            elif решение is False and помечена:
                снять.append((ид,))

        print(f"Вакансий в базе: {len(строки)}")
        print(f"  по запросу:      {итог['по запросу']}")
        print(f"  не по запросу:   {итог['не по запросу']}")
        print(f"  слов запроса нет нигде: {итог['неизвестно']} — остаются без пометки, вероятны синонимы")
        print(f"\n{'запрос':30}{'всего':>7}{'не по запросу':>15}{'доля':>7}{'нет нигде':>12}")
        заметные = sorted(
            ((з, п) for з, п in по_запросам.items() if п["не по запросу"] >= 5),
            key=lambda пара: -пара[1]["не по запросу"],
        )
        for запрос, п in заметные[:25]:
            print(f"{запрос[:29]:30}{п['всего']:>7}{п['не по запросу']:>15}"
                  f"{round(п['не по запросу'] / п['всего'] * 100):>5} %{п['неизвестно']:>12}")

        print(f"\nБудет помечено: {len(поставить)}, пометка снята: {len(снять)}")
        if аргументы.сухой_прогон or not (поставить or снять):
            print("Сухой прогон: база не тронута." if аргументы.сухой_прогон else "Править нечего.")
            return 0

        копия = settings.db_path.parent / "backups" / f"до_пометки_{datetime.now():%Y%m%d_%H%M}.db"
        копия.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(settings.db_path, копия)
        print(f"Копия базы: {копия}")

        with база:
            база.executemany("UPDATE vacancies SET off_query = 1 WHERE vacancy_id = ?", поставить)
            база.executemany("UPDATE vacancies SET off_query = 0 WHERE vacancy_id = ?", снять)
        print(f"Записано: помечено {len(поставить)}, снято {len(снять)}")
        return 0
    finally:
        база.close()


if __name__ == "__main__":
    sys.exit(main())
