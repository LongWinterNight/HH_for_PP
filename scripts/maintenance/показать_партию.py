"""
Показать следующие вакансии очереди для разметки.

Зачем. Разметчик читает вакансию целиком, и половина текста — условия,
соцпакет и рассказ о компании, из которых навыки по правилам не берутся
(S9‑1: раздел «Условия» в поиск не входит). Читать их — тратить внимание
на то, что заведомо не попадёт в разметку, а внимание здесь и есть
главный расходуемый ресурс: набор из двухсот вакансий размечается
руками.

Скрипт печатает то, что нужно решать: название, работодателя,
`key_skills` и текст без хвоста условий, с сохранёнными подзаголовками —
по ним видно, где требования, а где предложение работодателя.

Запуск:
    python scripts/maintenance/показать_партию.py Дизайн
    python scripts/maintenance/показать_партию.py Продажи --сколько 6
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

КОРЕНЬ = Path(__file__).resolve().parents[2]
ОЧЕРЕДЬ = КОРЕНЬ / "data" / "очередь_эталона.json"
ЭТАЛОН = КОРЕНЬ / "tests" / "fixtures" / "эталон_навыков.json"

# Заголовки, после которых в описании начинается предложение
# работодателя. Всё, что за ними, для разметки бесполезно.
ХВОСТ = re.compile(
    r"【\s*(условия|мы предлагаем|что мы предлагаем|мы гарантируем|"
    r"почему стоит|наши преимущества|мы это|что предлагаем|"
    r"условия работы|оформление|бонусы)",
    re.I,
)


def читаемый(html: str) -> str:
    т = re.sub(r"</(p|li|ul|ol|div|h[1-6])>", "\n", html or "")
    т = re.sub(r"<li>", " • ", т)
    т = re.sub(r"<(strong|b)>", "【", т)
    т = re.sub(r"</(strong|b)>", "】", т)
    т = re.sub(r"<[^>]+>", "", т)
    т = re.sub(r"&nbsp;?", " ", т)
    т = re.sub(r"[ \t]+", " ", т)
    return re.sub(r"\n{2,}", "\n", т).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Показать вакансии для разметки")
    parser.add_argument("рынок", help="название рынка из очереди")
    parser.add_argument("--сколько", type=int, default=4)
    parser.add_argument("--знаков", type=int, default=2600)
    args = parser.parse_args()

    очередь = json.loads(ОЧЕРЕДЬ.read_text(encoding="utf-8"))["вакансии"]
    размечено = {str(в["id"]) for в in json.loads(ЭТАЛОН.read_text(encoding="utf-8"))["вакансии"]}
    ждут = [в for в in очередь if в["рынок"] == args.рынок and в["id"] not in размечено]

    print(f"{args.рынок}: размечено {len([в for в in очередь if в['рынок'] == args.рынок]) - len(ждут)}, "
          f"ждёт {len(ждут)}\n")
    for в in ждут[: args.сколько]:
        текст = читаемый(в["описание"])
        обрыв = ХВОСТ.search(текст)
        if обрыв and обрыв.start() > 400:
            текст = текст[: обрыв.start()].rstrip() + "\n[…условия опущены]"
        print("=" * 95)
        print(f"id {в['id']} | {в['name']} | {в['employer']}")
        print(f"key_skills: {в['key_skills']}")
        print("-" * 95)
        print(текст[: args.знаков])
    return 0


if __name__ == "__main__":
    sys.exit(main())
