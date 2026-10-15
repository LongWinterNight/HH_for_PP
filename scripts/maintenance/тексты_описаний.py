"""
Докачка текстов описаний для вакансий, у которых их нет (S10‑13).

Сначала берёт тексты из сырых файлов прошлых сборов — бесплатно и без
сети. С ключом `--сеть` докачивает остаток с hh.ru: сначала из кэша
карточек, потом запросом с той же паузой, что у сбора.

Перед первой записью делается копия базы в `data/backups`. Остановить
докачку с сетью — создать пустой файл `data/стоп_текстов`: она допишет
текущую порцию и выйдет; продолжить — той же командой, с места.

Запуск:
    python scripts/maintenance/тексты_описаний.py --сухой-прогон
    python scripts/maintenance/тексты_описаний.py --yes
    python scripts/maintenance/тексты_описаний.py --yes --сеть
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import text_backfill as докачка  # noqa: E402
from src.config import settings  # noqa: E402
from src.normalize import SkillDictionaries, normalize_vacancy  # noqa: E402

ПОРЦИЯ = 200
СТОП = Path("data") / "стоп_текстов"


def копия_базы(база: Path) -> Path:
    """Копия средствами SQLite: верна и при работающем сервере, который читает базу."""
    папка = база.parent / "backups"
    папка.mkdir(exist_ok=True)
    цель = папка / f"{база.stem}_до_текстов_{datetime.now():%Y%m%d_%H%M}.db"
    with sqlite3.connect(база) as откуда, sqlite3.connect(цель) as куда:
        откуда.backup(куда)
    return цель


def main() -> int:
    разбор = argparse.ArgumentParser(description="Докачка текстов описаний")
    разбор.add_argument("--raw", default="data/raw")
    разбор.add_argument("--сухой-прогон", action="store_true", dest="сухой")
    разбор.add_argument("--yes", action="store_true")
    разбор.add_argument("--сеть", action="store_true", help="докачать остаток с hh.ru")
    разбор.add_argument("--предел", type=int, default=None, help="сколько вакансий скачать с hh.ru за запуск")
    разбор.add_argument("--все", action="store_true", help="и снятые с публикации, а не только активные")
    аргументы = разбор.parse_args()

    база = Path(settings.db_path)
    conn = sqlite3.connect(f"file:{база}?mode=ro", uri=True)
    очередь = докачка.без_текста(conn, только_активные=not аргументы.все)
    conn.close()
    print(f"Вакансий без текста: {len(очередь)}")
    if not очередь:
        print("Докачивать нечего.")
        return 0

    по_иду = {str(с["vacancy_id"]): с for с in очередь}
    из_файлов = докачка.из_сырых(Path(аргументы.raw), по_иду)
    остаток = [с for ид, с in по_иду.items() if ид not in из_файлов]
    print(f"Текст найден в сырых файлах: {len(из_файлов)}; придётся скачать с hh.ru: {len(остаток)}")

    if аргументы.сухой:
        словари = SkillDictionaries.from_config()
        было = sum(по_иду[ид].get("skill_count") or 0 for ид in из_файлов)
        стало = sum(normalize_vacancy(докачка.слить(по_иду[ид], к), словари)["skill_count"] for ид, к in из_файлов.items())
        print(f"Навыков у этих вакансий сейчас: {было}; станет после пересчёта по тексту: {стало}")
        print("Сухой прогон: база не тронута.")
        return 0

    if not аргументы.yes:
        print("Запустите с --yes, чтобы записать.")
        return 1

    from src.storage import VacancyStorage

    print(f"Копия базы: {копия_базы(база)}")
    хранилище = VacancyStorage(db_path=база)
    словари = SkillDictionaries.from_config()
    итог = {"вакансий": 0, "текстов_новых": 0, "навыков_было": 0, "навыков_стало": 0}

    def учесть(часть):
        for ключ in итог:
            итог[ключ] += часть[ключ]

    def записать(пачка):
        """
        Запись порции с повтором, пока база занята.

        Базу пишут и сбор по расписанию, и сервер; 15.10.2026 докачка
        упала на трёхсотой карточке с «database is locked». Повтор через
        паузу дешевле перезапуска: запись порции повторяема — вакансия с
        текстом второй раз не пишется.
        """
        from sqlalchemy.exc import OperationalError

        for попытка in range(1, 6):
            try:
                return докачка.записать(хранилище, пачка, словари)
            except OperationalError as ошибка:
                if "locked" not in str(ошибка) or попытка == 5:
                    raise
                print(f"  база занята, повтор через {попытка * 5} с")
                time.sleep(попытка * 5)

    try:
        пары = [(по_иду[ид], к) for ид, к in из_файлов.items()]
        for начало in range(0, len(пары), ПОРЦИЯ):
            учесть(записать(пары[начало:начало + ПОРЦИЯ]))
        print(f"Из файлов записано: {итог['вакансий']} вакансий, новых текстов {итог['текстов_новых']}")

        if аргументы.сеть and остаток:
            from src.api_cache import APICache
            from src.api_client import HHAPIClient

            клиент, кэш = HHAPIClient(), APICache()
            нужно = остаток[:аргументы.предел] if аргументы.предел else остаток
            пачка, отказов, скачано, начато = [], 0, 0, time.time()
            print(f"Скачиваю с hh.ru: {len(нужно)} карточек, пауза {клиент.delay} с")
            for номер, строка in enumerate(нужно, 1):
                if СТОП.exists():
                    print("Остановлено по просьбе (файл data/стоп_текстов).")
                    СТОП.unlink()
                    break
                try:
                    карточка, был_запрос = докачка.карточка_источника(str(строка["vacancy_id"]), клиент, кэш)
                except Exception as ошибка:
                    карточка, был_запрос = None, True
                    print(f"  отказ на {строка['vacancy_id']}: {ошибка}")
                if карточка and (карточка.get("description") or "").strip():
                    пачка.append((строка, карточка))
                    скачано += 1
                else:
                    отказов += 1
                if len(пачка) >= 50:
                    учесть(записать(пачка))
                    пачка = []
                if номер % 100 == 0:
                    print(f"  {номер}/{len(нужно)}: получено {скачано}, без карточки {отказов}, {time.time() - начато:.0f} с")
                if был_запрос:
                    time.sleep(клиент.delay)
            учесть(записать(пачка))
            print(f"С hh.ru: получено {скачано}, без карточки (снята или ошибка) {отказов}")
    finally:
        хранилище.close()

    print(f"Итого записано вакансий: {итог['вакансий']}; новых текстов: {итог['текстов_новых']}")
    print(f"Навыков у этих вакансий было {итог['навыков_было']}, стало {итог['навыков_стало']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
