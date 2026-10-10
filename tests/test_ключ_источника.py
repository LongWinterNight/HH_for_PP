"""
Ключ записи: источник плюс идентификатор (S8‑2a, S8‑2b).

Пока источник один, уникальность по `vacancy_id` работает. Второй
источник ломает её молча: идентификаторы у сайтов свои, и «137176862»
на одном не имеет отношения к «137176862» на другом. Прежний
уникальный индекс объявил бы их одной вакансией, и одна затёрла бы
другую — без ошибки, без следа в логах.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.storage import ИСТОЧНИК_ПО_УМОЛЧАНИЮ, VacancyStorage  # noqa: E402


@pytest.fixture
def склад(tmp_path, monkeypatch):
    from src import storage as модуль

    monkeypatch.setattr(модуль.settings, "db_path", tmp_path / "проверка.db")
    склад = VacancyStorage()
    yield склад
    склад.close()


def запись(vacancy_id, source=None, name="Инженер", employer="Компания"):
    строка = {
        "vacancy_id": vacancy_id,
        "vacancy_name": name,
        "employer_name": employer,
        "area": "Москва",
        "salary_currency": "RUB",
        "skill_count": 0,
    }
    if source is not None:
        строка["source"] = source
    return строка


class TestСоставнойКлюч:

    def test_одинаковый_идентификатор_разных_источников(self, склад):
        склад.save_vacancies_incremental(pd.DataFrame([
            запись("100", source="hh.ru", name="С первого сайта"),
            запись("100", source="пример.рф", name="Со второго сайта"),
        ]))

        df = склад.get_all_vacancies(include_inactive=True)

        assert len(df) == 2
        assert set(df["source"]) == {"hh.ru", "пример.рф"}
        assert set(df["vacancy_name"]) == {"С первого сайта", "Со второго сайта"}

    def test_обе_записи_считаются_новыми(self, склад):
        итог = склад.save_vacancies_incremental(pd.DataFrame([
            запись("100", source="hh.ru"),
            запись("100", source="пример.рф"),
        ]))

        # Счёт по одним идентификаторам показывал здесь одну вставку
        # вместо двух: множество схлопывало пару в один элемент.
        assert итог["inserted"] == 2

    def test_повтор_того_же_ключа_обновляет(self, склад):
        склад.save_vacancies_incremental(pd.DataFrame([
            запись("100", source="hh.ru", name="Было"),
        ]))
        итог = склад.save_vacancies_incremental(pd.DataFrame([
            запись("100", source="hh.ru", name="Стало"),
        ]))

        df = склад.get_all_vacancies(include_inactive=True)

        assert len(df) == 1
        assert df.iloc[0]["vacancy_name"] == "Стало"
        assert итог["updated"] == 1
        assert итог["inserted"] == 0

    def test_записи_без_источника_считаются_нашими(self, склад):
        # Файлы прошлых сборов источника не несут. Все они собраны с
        # hh.ru — другого источника у продукта не было.
        склад.save_vacancies_incremental(pd.DataFrame([запись("100")]))

        df = склад.get_all_vacancies(include_inactive=True)

        assert df.iloc[0]["source"] == ИСТОЧНИК_ПО_УМОЛЧАНИЮ

    def test_старая_запись_обновляется_новой_с_явным_источником(self, склад):
        # Запись, сохранённая без источника, и та же вакансия из живого
        # сбора — одно и то же: подстановка по умолчанию обязана давать
        # тот же ключ.
        склад.save_vacancies_incremental(pd.DataFrame([запись("100", name="Было")]))
        склад.save_vacancies_incremental(pd.DataFrame([
            запись("100", source="hh.ru", name="Стало"),
        ]))

        df = склад.get_all_vacancies(include_inactive=True)

        assert len(df) == 1
        assert df.iloc[0]["vacancy_name"] == "Стало"

    def test_повтор_ключа_внутри_одной_пачки(self, склад):
        # SQLite не даёт ON CONFLICT сработать дважды в одном запросе:
        # повтор внутри пачки надо схлопнуть до записи.
        склад.save_vacancies_incremental(pd.DataFrame([
            запись("100", source="hh.ru", name="Первое"),
            запись("100", source="hh.ru", name="Второе"),
        ]))

        df = склад.get_all_vacancies(include_inactive=True)

        assert len(df) == 1
        assert df.iloc[0]["vacancy_name"] == "Второе"
