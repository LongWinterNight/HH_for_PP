"""
Пересчёт навыков по файлам сборов.

Зачем. Навыки в базе посчитаны прежним правилом: поиск шёл по всему
описанию, включая разделы «Условия» и «Мы предлагаем». Оттуда в
статистику попали «Подарки» (70 вакансий), «Развитие» (260),
«Мотивация» (129), «Больничные» (26) — корпоративный соцпакет,
засчитанный как профессиональные навыки.

Правило изменилось (`src/sections.py`), но записи в базе остались
прежними: пересобирать их значит заново ходить в источник за тем, что
уже сохранено в `data/raw`.

Скрипт заново разбирает сохранённые ответы источника текущими правилами
и переписывает навыки. Навыки, названные работодателем
(`employer_skills`), при этом не теряются: они приходят из тех же
файлов и считаются по тем же правилам, что в живом сборе.

Вакансия, которой нет в файлах, остаётся как была: пересчитать её не по
чему, а стереть навыки значило бы обменять неточность на пустоту.

Запуск:
    python scripts/maintenance/пересчёт_навыков.py --сухой-прогон
    python scripts/maintenance/пересчёт_навыков.py --yes
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.normalize import SkillDictionaries, normalize_vacancy  # noqa: E402

# С какой убыли навыков пересчёт останавливается и требует согласия.
# Десятая часть — это уже не уточнение правил, а потеря данных: столько
# даёт стирание навыков работодателя, которых нет в старых файлах сборов.
ПОРОГ_УБЫЛИ = 0.10


def вакансии_из_файла(путь: Path):
    try:
        данные = json.loads(путь.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(данные, dict):
        данные = данные.get("vacancies") or данные.get("items") or []
    return данные if isinstance(данные, list) else []


def свежие_разборы(папка: Path, словари) -> dict:
    """{ид: разобранная запись} по всем файлам сборов.

    Из нескольких версий одной вакансии берётся та, где больше текста:
    описание могло появиться только в поздних сборах, когда до вакансии
    дошла очередь за карточкой.
    """
    лучшее: dict[str, tuple] = {}

    for файл in sorted(папка.glob("*.json")):
        for вакансия in вакансии_из_файла(файл):
            if not isinstance(вакансия, dict):
                continue
            ид = str(вакансия.get("id") or "")
            if not ид:
                continue
            объём = len(вакансия.get("description") or "") + len(
                json.dumps(вакансия.get("key_skills") or [], ensure_ascii=False)
            )
            если_было = лучшее.get(ид)
            if если_было is None or объём > если_было[0]:
                лучшее[ид] = (объём, вакансия)

    return {ид: normalize_vacancy(в, словари) for ид, (_, в) in лучшее.items()}


def разборы_из_базы(словари) -> dict:
    """
    {ид: разобранная запись} по текстам, лежащим в самой базе.

    Зачем отдельно от файлов. Пересчёт по сырью работает, пока сырьё
    есть: 261 МБ файлов, которые волна 6 предлагает убирать через
    девяносто дней. Текст в базе (S13) делает пересчёт независимым и от
    файлов, и от сети — прогон без интернета даёт те же навыки.

    Вакансии без текста пропускаются молча: их подберёт разбор по
    файлам, если файлы ещё целы.
    """
    from src.storage import VacancyStorage

    хранилище = VacancyStorage()
    try:
        строки = хранилище.engine.raw_connection().cursor().execute(
            "SELECT v.vacancy_id, v.vacancy_name, v.employer_name, v.published_at, "
            "       v.area, v.employer_skills, t.body "
            "FROM vacancies v JOIN vacancy_texts t ON t.text_hash = v.text_hash"
        ).fetchall()
    finally:
        хранилище.close()

    from src import texts as тексты_модуль

    итог = {}
    for ид, название, работодатель, опубликовано, регион, навыки_работодателя, тело in строки:
        вакансия = {
            "id": ид,
            "name": название or "",
            "description": тексты_модуль.разжать(тело),
            "employer": {"name": работодатель or ""},
            "published_at": опубликовано,
            "area": {"name": регион or ""},
            "key_skills": [
                {"name": н} for н in (навыки_работодателя or "").split(", ") if н
            ],
        }
        итог[str(ид)] = normalize_vacancy(вакансия, словари)
    return итог


def разбить(строка) -> list:
    return [ч.strip() for ч in (строка or "").split(",") if ч.strip()]


def main() -> int:
    разбор = argparse.ArgumentParser(description="Пересчёт навыков по файлам сборов")
    разбор.add_argument("--db", default="data/hh_vacancies.db")
    разбор.add_argument("--raw", default="data/raw")
    разбор.add_argument("--из-базы", action="store_true", dest="из_базы",
                        help="брать тексты из базы, а не из сырых файлов: "
                             "работает без интернета и без сырья")
    разбор.add_argument("--сухой-прогон", action="store_true", dest="сухой")
    разбор.add_argument("--yes", action="store_true")
    разбор.add_argument("--согласен-на-убыль", action="store_true",
                        dest="согласен_на_убыль",
                        help="применить, даже если навыков станет заметно меньше")
    аргументы = разбор.parse_args()

    база, сырые = Path(аргументы.db), Path(аргументы.raw)
    if not база.exists():
        print(f"База не найдена: {база}")
        return 1
    if not аргументы.из_базы and not сырые.exists():
        print(f"Папка сборов не найдена: {сырые}")
        return 1

    словари = SkillDictionaries.from_config()
    if аргументы.из_базы:
        разборы = разборы_из_базы(словари)
        print(f"Вакансий разобрано из текстов в базе: {len(разборы)}")
    else:
        разборы = свежие_разборы(сырые, словари)
        print(f"Вакансий разобрано из файлов сборов: {len(разборы)}")

    conn = sqlite3.connect(база)
    conn.isolation_level = None

    try:
        строки = conn.execute(
            "SELECT vacancy_id, all_skills, hard_skills, soft_skills, tools FROM vacancies"
        ).fetchall()

        к_записи = []
        ушло, пришло = Counter(), Counter()
        было_всего = стало_всего = 0

        for ид, все_н, hard, soft, tools in строки:
            свежий = разборы.get(str(ид))
            if not свежий:
                continue

            прежние = {н.lower(): н for н in разбить(все_н)}
            новые = {н.lower(): н for н in разбить(свежий["all_skills"])}

            было_всего += len(прежние)
            стало_всего += len(новые)

            for ключ in прежние.keys() - новые.keys():
                ушло[прежние[ключ]] += 1
            for ключ in новые.keys() - прежние.keys():
                пришло[новые[ключ]] += 1

            if прежние.keys() == новые.keys():
                continue

            к_записи.append((
                свежий["all_skills"], свежий["hard_skills"], свежий["soft_skills"],
                свежий["tools"], свежий["employer_skills"], свежий["skill_count"],
                свежий["hard_skill_count"], свежий["soft_skill_count"],
                свежий["tools_count"], ид,
            ))

        print(f"Записей изменится: {len(к_записи)}")
        print(f"Навыков было: {было_всего}, станет: {стало_всего}")

        print("\nПерестанут считаться навыками (топ-12):")
        for н, c in ушло.most_common(12):
            print(f"  {c:>5} × {н}")
        if пришло:
            print("\nПоявятся (топ-8):")
            for н, c in пришло.most_common(8):
                print(f"  {c:>5} × {н}")

        # Потеря навыков — не всегда очистка мусора.
        #
        # Скрипт задуман, чтобы выбросить из статистики соцпакет,
        # засчитанный как навыки. Но он же переписывает навыки,
        # названные работодателем, а в файлах сборов `key_skills` есть
        # не у всех записей: часть попала в базу позже, скриптом
        # обогащения. Для таких вакансий пересчёт означает не уточнение,
        # а стирание — на живой базе это почти десять тысяч упоминаний.
        #
        # Поэтому большая убыль требует отдельного согласия: молча
        # стереть собранное скрипт не должен.
        убыль = было_всего - стало_всего
        доля_убыли = убыль / было_всего if было_всего else 0

        if убыль > 0:
            print()
            print(f"Навыков станет меньше на {убыль} ({доля_убыли:.0%})")
            if доля_убыли >= ПОРОГ_УБЫЛИ:
                print("  Проверьте, есть ли `key_skills` в файлах сборов у тех")
                print("  вакансий, чьи навыки исчезнут: навыки работодателя,")
                print("  восстановленные обогащением, пересчёт по файлам стирает.")

        if аргументы.сухой:
            print("\nСухой прогон. Данные не изменены.")
            return 0

        if not аргументы.yes:
            print("\nЗапустите с --yes, чтобы применить.")
            return 1

        if доля_убыли >= ПОРОГ_УБЫЛИ and not аргументы.согласен_на_убыль:
            print()
            print(f"Остановлено: убыль {доля_убыли:.0%} больше порога {ПОРОГ_УБЫЛИ:.0%}.")
            print("Если это ожидаемо, добавьте --согласен-на-убыль.")
            return 1

        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(
            "UPDATE vacancies SET all_skills = ?, hard_skills = ?, soft_skills = ?, "
            "tools = ?, employer_skills = ?, skill_count = ?, hard_skill_count = ?, "
            "soft_skill_count = ?, tools_count = ? WHERE vacancy_id = ?",
            к_записи,
        )
        conn.execute("COMMIT")

        print(f"\nГотово: пересчитано {len(к_записи)} записей.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
