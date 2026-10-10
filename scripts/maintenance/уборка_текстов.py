"""
Уборка описаний, которые больше не нужны.

Зачем. Текст хранится ради переразбора: сменились правила извлечения —
прошли по базе заново, не обращаясь к источнику. Но переразбирать имеет
смысл то, что участвует в аналитическом окне. Вакансия, снятая с
публикации год назад, в срезах не появляется, а её описание продолжает
занимать место — и на пятнадцати источниках это уже гигабайты.

Правило удержания: тело живёт, пока вакансия активна, плюс окно. Дальше
остаются хэш текста, извлечённые навыки и версия правил, которой они
получены. Тогда объём хранилища — функция окна, а не всей истории
продукта: через три года база весит столько же, сколько через полгода.

Обмен осознанный и записан в решении 2.8a: переразобрать вакансию
2027 года новыми правилами в 2029‑м будет нельзя. Чем старше вакансия,
тем меньше смысла в её переразборе.

Текст, на который ссылается хоть одна живая вакансия, не трогается: он
один на всю группу копий, и удалить его — значит осиротить их все.

Запуск:
    python scripts/maintenance/уборка_текстов.py --сухой-прогон
    python scripts/maintenance/уборка_текстов.py --окно 365 --сухой-прогон
    python scripts/maintenance/уборка_текстов.py --окно 365 --yes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Сколько дней текст живёт после того, как вакансия перестала быть
# активной. Год — компромисс: годовые срезы остаются переразбираемыми, а
# хранилище не растёт бесконечно.
ОКНО_ПО_УМОЛЧАНИЮ = 365


def кандидаты(conn: sqlite3.Connection, окно: int) -> list:
    """
    Тексты, которые можно удалить.

    Три условия сразу: на текст не ссылается ни одна активная вакансия,
    все ссылающиеся вакансии старше окна, и сам текст получен раньше
    границы. Последнее спасает от удаления свежего текста, случайно
    привязанного к старой записи.
    """
    граница = (datetime.now() - timedelta(days=окно)).isoformat(" ", "seconds")
    return list(conn.execute(
        """
        SELECT t.text_hash, t.bytes_raw
        FROM vacancy_texts t
        WHERE t.fetched_at < ?
          AND NOT EXISTS (
              SELECT 1 FROM vacancies v
              WHERE v.text_hash = t.text_hash
                AND (v.is_active = 1 OR COALESCE(v.last_seen_at, v.created_at) >= ?)
          )
        """,
        (граница, граница),
    ))


def main() -> int:
    разбор = argparse.ArgumentParser(description="Уборка старых описаний")
    разбор.add_argument("--db", default="data/hh_vacancies.db")
    разбор.add_argument("--окно", type=int, default=ОКНО_ПО_УМОЛЧАНИЮ,
                        help="сколько дней текст живёт после того, как вакансия ушла")
    разбор.add_argument("--сухой-прогон", action="store_true", dest="сухой")
    разбор.add_argument("--yes", action="store_true")
    аргументы = разбор.parse_args()

    путь = Path(аргументы.db)
    if not путь.exists():
        print(f"База не найдена: {путь}")
        return 1

    conn = sqlite3.connect(путь)
    try:
        таблицы = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "vacancy_texts" not in таблицы:
            print("Таблицы vacancy_texts нет. Сначала: "
                  "python scripts/migrations/018_vacancy_texts.py --yes")
            return 1

        всего, объём = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(bytes_raw), 0) FROM vacancy_texts"
        ).fetchone()
        удалить = кандидаты(conn, аргументы.окно)
        освободится = sum(размер or 0 for _, размер in удалить)

        print(f"База: {путь}")
        print(f"  текстов всего:    {всего}, {объём / 1024 / 1024:.1f} МБ до сжатия")
        print(f"  окно удержания:   {аргументы.окно} дней после ухода вакансии")
        print(f"  под удаление:     {len(удалить)}, освободится "
              f"{освободится / 1024 / 1024:.1f} МБ")

        if not удалить:
            print("\nУдалять нечего.")
            return 0

        # Скрипт всегда печатает, что именно удалит, до удаления: цена
        # ошибки здесь — потерянный навсегда текст, восстановить его
        # можно только повторным обращением к источнику, а снятую
        # вакансию он уже не отдаст.
        for хэш, размер in удалить[:5]:
            print(f"    {хэш[:16]}…  {(размер or 0) / 1024:.1f} КБ")
        if len(удалить) > 5:
            print(f"    …и ещё {len(удалить) - 5}")

        if аргументы.сухой:
            print("\nСухой прогон. Ничего не удалено.")
            return 0

        if not аргументы.yes:
            print("\nЗапустите с --yes, чтобы удалить.")
            return 1

        conn.executemany(
            "DELETE FROM vacancy_texts WHERE text_hash = ?",
            [(хэш,) for хэш, _ in удалить],
        )
        conn.commit()
        print(f"\nУдалено текстов: {len(удалить)}. "
              "Хэши, навыки и версии правил у вакансий остались.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
