"""
Дозапрос карточек вакансий, у которых их нет.

Зачем. Карточка вакансии — отдельный запрос к источнику, и раньше она
бралась только для первых двух страниц каждого запроса. На живой базе
это дало детали у 43 % записей, и разница видна в данных: у вакансии с
карточкой 14,7 навыка, без карточки — 2,4. Из 1268 вакансий без единого
навыка почти все именно такие.

Сбор теперь берёт карточку у каждой новой вакансии, но в базе остались
тысячи собранных по старому правилу. Пересобирать их значит заново
проходить всю выдачу; здесь запрашиваются только сами карточки.

Порядок — от свежих к старым: если бюджет кончится, он кончится на менее
важном. Прерванный проход не теряет сделанное — карточки сохраняются по
мере получения, и следующий запуск продолжает с того же места.

Запуск:
    python scripts/maintenance/дозапрос_деталей.py --сухой-прогон
    python scripts/maintenance/дозапрос_деталей.py --предел 200 --yes
    python scripts/maintenance/дозапрос_деталей.py --все --yes
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402

from src.api_client import HHAPIClient  # noqa: E402
from src.normalize import SkillDictionaries, normalize_vacancy  # noqa: E402
from src.storage import VacancyStorage  # noqa: E402
from src.utils import get_logger  # noqa: E402

logger = get_logger(__name__)


def кого_дозапрашивать(df: pd.DataFrame, только_активные: bool) -> pd.DataFrame:
    """Вакансии без карточки, от свежих к старым."""
    если_есть = df["has_details"].fillna(0).astype(bool)
    нужны = df[~если_есть].copy()

    if только_активные and "is_active" in нужны.columns:
        нужны = нужны[нужны["is_active"].fillna(1) == 1]

    if "published_at" in нужны.columns:
        нужны["_дата"] = pd.to_datetime(
            нужны["published_at"], errors="coerce", utc=True, format="mixed"
        )
        нужны = нужны.sort_values("_дата", ascending=False, na_position="last")

    return нужны


def main() -> int:
    разбор = argparse.ArgumentParser(description="Дозапрос карточек вакансий")
    разбор.add_argument("--предел", type=int, default=200,
                        help="сколько карточек запросить за один проход")
    разбор.add_argument("--все", action="store_true", dest="все",
                        help="без предела: запросить все недостающие")
    разбор.add_argument("--включая-архив", action="store_true", dest="архив",
                        help="дозапрашивать и снятые с публикации")
    разбор.add_argument("--пауза", type=float, default=1.0,
                        help="секунд между запросами к источнику")
    разбор.add_argument("--сухой-прогон", action="store_true", dest="сухой")
    разбор.add_argument("--yes", action="store_true")
    аргументы = разбор.parse_args()

    склад = VacancyStorage()
    try:
        df = склад.get_all_vacancies(include_inactive=True)
    finally:
        склад.close()

    if df.empty:
        print("База пуста — дозапрашивать нечего.")
        return 0

    очередь = кого_дозапрашивать(df, только_активные=not аргументы.архив)
    предел = len(очередь) if аргументы.все else min(аргументы.предел, len(очередь))

    с_деталями = int(df["has_details"].fillna(0).astype(bool).sum())
    print(f"В базе: {len(df)}, с карточкой: {с_деталями} ({с_деталями / len(df) * 100:.0f} %)")
    print(f"Без карточки{'' if аргументы.архив else ' (активных)'}: {len(очередь)}")
    print(f"Будет запрошено: {предел}")
    print(f"Время при паузе {аргументы.пауза} с: примерно {предел * аргументы.пауза / 60:.0f} мин")

    if аргументы.сухой:
        print("\nСухой прогон. Запросов к источнику не сделано.")
        if предел:
            print("Первые в очереди (свежие сверху):")
            for _, строка in очередь.head(5).iterrows():
                print(f"  {строка['vacancy_id']}  {str(строка['vacancy_name'])[:52]}")
        return 0

    if not аргументы.yes:
        print("\nЗапустите с --yes, чтобы обратиться к источнику.")
        return 1

    клиент = HHAPIClient(delay=аргументы.пауза)
    словари = SkillDictionaries.from_config()
    склад = VacancyStorage()

    получено = пусто = 0
    начало = time.monotonic()

    try:
        for номер, (_, строка) in enumerate(очередь.head(предел).iterrows(), start=1):
            ид = str(строка["vacancy_id"])
            try:
                карточка = клиент.get_vacancy_details(ид)
            except Exception as ошибка:
                logger.warning(f"Вакансия {ид}: {ошибка}")
                карточка = None

            if not карточка:
                пусто += 1
                continue

            # Карточка разбирается тем же кодом, что и живой сбор: два
            # пути разбора однажды разойдутся, и данные будут зависеть от
            # того, каким из них они попали в базу.
            карточка["_has_details"] = True
            карточка.setdefault("_source_keyword", строка.get("source_keyword"))
            запись = normalize_vacancy(карточка, словари)

            склад.save_vacancies_incremental(pd.DataFrame([запись]))
            получено += 1

            if номер % 25 == 0:
                прошло = time.monotonic() - начало
                print(f"  {номер} из {предел}, получено {получено}, "
                      f"{прошло / 60:.1f} мин")

        print(f"\nГотово: карточек получено {получено}, пустых ответов {пусто}.")

        обновлённый = склад.get_all_vacancies(include_inactive=True)
        стало = int(обновлённый["has_details"].fillna(0).astype(bool).sum())
        print(f"С карточкой теперь: {стало} из {len(обновлённый)} "
              f"({стало / len(обновлённый) * 100:.0f} %)")
        return 0

    except KeyboardInterrupt:
        # Прерывание — не потеря: всё полученное уже в базе, следующий
        # запуск начнёт с того места, где остановились.
        print(f"\nОстановлено. Получено карточек: {получено}, они сохранены.")
        return 0
    finally:
        склад.close()
        клиент.close() if hasattr(клиент, "close") else None


if __name__ == "__main__":
    sys.exit(main())
