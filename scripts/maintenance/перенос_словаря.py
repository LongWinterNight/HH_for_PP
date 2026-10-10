"""
Перенос словаря навыков из конфига в данные.

Зачем. Словарь из 1158 позиций лежит в `config.yaml` рядом с
поисковыми запросами и параметрами обработки: данные, которые меняются
еженедельно, — в файле, который меняют раз в полгода. Скрипт
перекладывает их в `data/skills.yaml`, попутно убирая повторы: их
накопилось 78, в основном «Docker» и подобное сразу в двух разделах.

Синонимы переносятся из отдельного файла-заготовки, если он указан:
собирать их автоматически нельзя. Скелет «без пробелов и регистра» у
«C#» и «C++» совпадает, и машина свела бы два разных языка в один.

Что остаётся в конфиге. Ничего: разделы `hard_skills`, `soft_skills` и
`tools` из него удаляются, иначе через месяц никто не вспомнит, какой
из двух словарей главный. Загрузчик читает файл данных, а конфиг —
только пока файла нет.

Запуск:
    python scripts/maintenance/перенос_словаря.py --сухой-прогон
    python scripts/maintenance/перенос_словаря.py --yes
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml  # noqa: E402

from src.config import PROJECT_ROOT  # noqa: E402
from src.skills_store import ПУТЬ_СЛОВАРЯ, без_дублей  # noqa: E402

КОНФИГ = PROJECT_ROOT / "config.yaml"

# Как называются разделы здесь и там.
СООТВЕТСТВИЕ = {
    "hard": "hard_skills",
    "soft": "soft_skills",
    "tools": "tools",
}


def прочитать_конфиг() -> dict:
    with open(КОНФИГ, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def собрать_словарь(конфиг: dict, синонимы: dict) -> dict:
    """
    Словарь для файла данных: разделы без повторов и таблица синонимов.

    Повтор внутри раздела убирается молча. Позиция, стоящая сразу в
    двух разделах, остаётся в первом по порядку hard → soft → tools:
    категория навыка нужна для подсчётов, и одна позиция не может быть
    одновременно «жёстким навыком» и «инструментом».
    """
    итог = {}
    занято = set()

    for раздел, ключ_конфига in СООТВЕТСТВИЕ.items():
        значения = без_дублей(конфиг.get(ключ_конфига) or [])
        свои = []
        for значение in значения:
            ключ = значение.lower()
            if ключ in занято:
                continue
            занято.add(ключ)
            свои.append(значение)
        итог[раздел] = свои

    итог["synonyms"] = синонимы
    return итог


def main() -> int:
    разбор = argparse.ArgumentParser(description="Перенос словаря навыков в данные")
    разбор.add_argument("--синонимы", type=Path,
                        help="файл YAML с таблицей синонимов «канон: [варианты]»")
    разбор.add_argument("--сухой-прогон", action="store_true", dest="сухой")
    разбор.add_argument("--yes", action="store_true")
    аргументы = разбор.parse_args()

    конфиг = прочитать_конфиг()

    синонимы = {}
    if аргументы.синонимы and аргументы.синонимы.exists():
        with open(аргументы.синонимы, "r", encoding="utf-8") as f:
            синонимы = yaml.safe_load(f) or {}
    elif ПУТЬ_СЛОВАРЯ.exists():
        # Повторный перенос не должен стирать уже проверенные синонимы.
        with open(ПУТЬ_СЛОВАРЯ, "r", encoding="utf-8") as f:
            прежнее = yaml.safe_load(f) or {}
        синонимы = прежнее.get("synonyms") or {}

    словарь = собрать_словарь(конфиг, синонимы)

    было = sum(len(конфиг.get(к) or []) for к in СООТВЕТСТВИЕ.values())
    стало = sum(len(словарь[р]) for р in СООТВЕТСТВИЕ)

    print(f"Конфиг: {КОНФИГ}")
    print(f"  позиций в словаре: {было}")
    print(f"Файл данных: {ПУТЬ_СЛОВАРЯ}")
    for раздел in СООТВЕТСТВИЕ:
        print(f"  {раздел}: {len(словарь[раздел])}")
    print(f"  синонимов: {len(словарь['synonyms'])}")
    print(f"  повторов убрано: {было - стало}")
    print(f"Из конфига разделы {', '.join(СООТВЕТСТВИЕ.values())} будут удалены")

    if аргументы.сухой:
        print("\nСухой прогон. Файлы не изменены.")
        return 0

    if not аргументы.yes:
        print("\nЗапустите с --yes, чтобы применить.")
        return 1

    ПУТЬ_СЛОВАРЯ.parent.mkdir(parents=True, exist_ok=True)
    with open(ПУТЬ_СЛОВАРЯ, "w", encoding="utf-8") as f:
        yaml.safe_dump(словарь, f, allow_unicode=True, sort_keys=False, width=100)

    # Конфиг переписывается только после того, как данные легли на диск:
    # обрыв посередине не должен оставить продукт без словаря вовсе.
    shutil.copy2(КОНФИГ, КОНФИГ.with_suffix(".yaml.bak"))
    for ключ in СООТВЕТСТВИЕ.values():
        конфиг.pop(ключ, None)
    with open(КОНФИГ, "w", encoding="utf-8") as f:
        yaml.safe_dump(конфиг, f, allow_unicode=True, sort_keys=False, width=100)

    print(f"\nГотово. Словарь в {ПУТЬ_СЛОВАРЯ}, конфиг сохранён как "
          f"{КОНФИГ.with_suffix('.yaml.bak').name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
