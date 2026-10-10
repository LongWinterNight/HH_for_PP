"""
Отметка подзадач в плане работ.

Зачем. Разложить задачу на подзадачи получается всегда, а отмечать их по
ходу — нет: отметка это отдельное действие, которое откладывается «на
потом», и в конце статусы проставляются пачкой по памяти. Один раз так
уже потерялась подзадача (перенос прогресс-бара в 2.1): в списке она
была, в коде её не было, и заметили это только при следующей сверке.

Скрипт делает отметку дешёвой — одна команда сразу после выполнения.

Использование:
    python scripts/plan_status.py 2.3-2a                  # отметить сделанной
    python scripts/plan_status.py 2.3-2a --статус отменено --почему "..."
    python scripts/plan_status.py --что-осталось          # незакрытые подзадачи
    python scripts/plan_status.py --сверка                # найти отмеченное, но пустое
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ДОКУМЕНТЫ = [
    Path(__file__).resolve().parents[1] / "docs" / "plan-parser-dashboard.md",
    Path(__file__).resolve().parents[1] / "docs" / "backlog-breakdown.md",
    Path(__file__).resolve().parents[1] / "docs" / "backlog-full.md",
]

# В плане номера подзадач пишутся с неразрывным дефисом, а в командной
# строке его не набрать — приводим оба вида к одному.
ДЕФИСЫ = {"‑": "-", "–": "-", "—": "-"}


def нормализовать(текст: str) -> str:
    for исходный, обычный in ДЕФИСЫ.items():
        текст = текст.replace(исходный, обычный)
    return текст.strip()


def документы() -> list:
    """Файлы, где живут подзадачи: план работ и разбивка бэклога."""
    существующие = [d for d in ДОКУМЕНТЫ if d.exists()]
    if not существующие:
        print("Ни одного документа с задачами не найдено")
        sys.exit(1)
    return существующие


def строки(документ: Path) -> list[str]:
    return документ.read_text(encoding="utf-8").split("\n")


def найти(строки: list[str], ид: str) -> int | None:
    цель = нормализовать(ид).lower()
    for i, строка in enumerate(строки):
        if not строка.startswith("|"):
            continue
        первая = нормализовать(строка.split("|")[1]).lower()
        if первая == цель:
            return i
    return None


def отметить(ид: str, статус: str, почему: str) -> int:
    for документ in документы():
        текст = строки(документ)
        i = найти(текст, ид)
        if i is None:
            continue

        ячейки = текст[i].split("|")
        отметка = статус if not почему else f"{статус} — {почему}"

        if len(ячейки) >= 5:
            # Таблица со своей колонкой статуса.
            ячейки[-2] = f" {отметка} "
        else:
            # Таблица без колонки статуса: отметка дописывается к строке,
            # чтобы стоять там же, где задача, а не в отдельном списке.
            ячейки.insert(-1, f" {отметка} ")
        текст[i] = "|".join(ячейки)

        документ.write_text("\n".join(текст), encoding="utf-8")
        print(f"{ид}: {отметка}  ({документ.name})")
        return 0

    print(f"Подзадача {ид} не найдена ни в плане, ни в разбивке бэклога.")
    return 1


def что_осталось() -> int:
    открытые = []
    for документ in документы():
        открытые += [
            s for s in строки(документ)
            if s.startswith("|") and s.rstrip().endswith("| — |")
        ]
    if not открытые:
        print("Незакрытых подзадач в плане нет.")
        return 0

    print(f"Незакрытых подзадач: {len(открытые)}\n")
    for s in открытые:
        ячейки = s.split("|")
        print(f"  {нормализовать(ячейки[1]):<12} {ячейки[2].strip()[:80]}")
    return 0


def сверка() -> int:
    """
    Показать отмеченные подзадачи для ручной сверки с кодом.

    Скрипт не умеет проверять, что код действительно написан, — он лишь
    напоминает, что отметка это утверждение, которое стоит подтвердить.
    """
    сделанные = []
    for документ in документы():
        сделанные += [
            s for s in строки(документ)
            if s.startswith("|") and "сделано" in s.split("|")[-2]
        ]
    print(f"Отмечено сделанными: {len(сделанные)}")
    print("Сверь выборочно: у каждой должен быть след в коде или тестах.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Отметка подзадач плана")
    parser.add_argument("ид", nargs="?", help="номер подзадачи, например 2.3-2a")
    parser.add_argument("--статус", default="сделано", help="сделано | отменено | перенесено")
    parser.add_argument("--почему", default="", help="пояснение для отменённых и перенесённых")
    parser.add_argument("--что-осталось", action="store_true", help="список незакрытых")
    parser.add_argument("--сверка", action="store_true", help="сводка по отмеченным")
    args = parser.parse_args()

    if args.что_осталось:
        return что_осталось()
    if args.сверка:
        return сверка()
    if not args.ид:
        parser.print_help()
        return 1

    return отметить(args.ид, args.статус, args.почему)


if __name__ == "__main__":
    sys.exit(main())
