"""
Порядок списка вакансий по зарплате.

Пока курса не было, сортировка требовала сначала выбрать валюту: без
общего знаменателя 19 000 000 сум всегда оказывались выше 300 000
рублей. Курс ЦБ появился (К1, К2), и костыль снят — но снят он верно
только если выполняются три вещи: между валютами сравнивается
эквивалент, внутри выбранной валюты — исходная сумма, а запись без
суммы не выдаёт себя за самую дешёвую.

Запуск: pytest tests/test_сортировка_зарплат.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import src.storage as storage_module
from src.cbr_rates import Курсы
from src.storage import VacancyStorage
from web.app.main import get_vacancies

from datetime import date

# Курс из настоящего ответа ЦБ, приведённый к единице.
КУРСЫ = Курсы(
    на_дату=date(2026, 9, 9),
    значения={"RUB": 1.0, "USD": 86.473, "UZS": 0.00733485},
)

# Три вакансии, ради которых задача и затевалась: по номиналу сум выше
# всех, по эквиваленту — ниже доллара и рубля.
ВЫБОРКА = [
    ("сум", "UZS", 19_000_000),   # ≈ 139 000 ₽
    ("доллар", "USD", 5_000),     # ≈ 432 000 ₽
    ("рубль", "RUB", 300_000),    # 300 000 ₽
]


def вакансия(vacancy_id: str, currency: str, salary_from, день: str = "01") -> dict:
    """Строка в том виде, в каком её отдаёт нормализация сбора."""
    return {
        "vacancy_id": vacancy_id,
        "vacancy_name": "Аналитик данных",
        "published_at": f"2026-09-{день}T10:00:00+0300",
        "salary_from": salary_from,
        "salary_to": None,
        "salary_currency": currency,
        "employer_name": "Компания",
        "employer_id": vacancy_id,
        "employer_url": "",
        "vacancy_url": "",
        "experience": "От 1 года до 3 лет",
        "employment": "Полная занятость",
        "schedule": "Удалённо",
        "area": "Москва",
        "all_skills": "python",
        "hard_skills": "python",
        "soft_skills": "",
        "tools": "",
        "skill_count": 1,
        "hard_skill_count": 1,
        "soft_skill_count": 0,
        "tools_count": 0,
    }


def порядок(sort_order: str = "desc", currency: str = "", **ещё) -> list[str]:
    """Идентификаторы вакансий в том порядке, в каком их отдаёт список."""
    ответ = get_vacancies(
        page=1, per_page=20, search="", area="", experience="", skill="",
        salary_only=False, currency=currency, sort_by="salary",
        sort_order=sort_order, include_inactive=False, **ещё
    )
    return [i["vacancy_id"] for i in ответ["items"]]


@pytest.fixture
def база(tmp_path, monkeypatch):
    """Своя база с курсами: тест не зависит от боевых данных и от дня."""
    путь = tmp_path / "проба.db"
    склад = VacancyStorage(db_path=путь)
    склад.save_currency_rates(КУРСЫ)
    склад.save_vacancies_incremental(
        pd.DataFrame([вакансия(ид, вал, сумма) for ид, вал, сумма in ВЫБОРКА])
    )
    склад.close()

    monkeypatch.setattr(
        storage_module, "VacancyStorage", lambda *args, **kwargs: VacancyStorage(db_path=путь)
    )
    yield путь


@pytest.mark.usefixtures("база")
class TestПорядокМеждуВалютами:
    """Валюта не выбрана — сравнивается рублёвый эквивалент."""

    def test_сум_рубль_и_доллар_в_одном_списке(self):
        """Номинал сума больше всех, эквивалент — меньше всех."""
        assert порядок("desc") == ["доллар", "рубль", "сум"]

    def test_обратный_порядок_зеркальный(self):
        assert порядок("asc") == ["сум", "рубль", "доллар"]


@pytest.mark.usefixtures("база")
class TestПорядокВнутриВалюты:
    """Валюта выбрана — сравниваются исходные суммы."""

    def test_внутри_валюты_эквивалент_не_участвует(self, tmp_path, monkeypatch):
        путь = tmp_path / "сумы.db"
        склад = VacancyStorage(db_path=путь)
        склад.save_currency_rates(КУРСЫ)
        склад.save_vacancies_incremental(pd.DataFrame([
            вакансия("больше", "UZS", 24_000_000),
            вакансия("меньше", "UZS", 18_000_000),
            вакансия("рубль", "RUB", 300_000),
        ]))
        склад.close()
        monkeypatch.setattr(
            storage_module, "VacancyStorage", lambda *a, **k: VacancyStorage(db_path=путь)
        )

        assert порядок("desc", currency="UZS") == ["больше", "меньше"]


@pytest.mark.usefixtures("база")
class TestЗаписиБезСуммы:
    """Пустое не выдаёт себя за дешёвое."""

    def test_без_зарплаты_уходит_в_конец_при_возрастании(self, tmp_path, monkeypatch):
        путь = tmp_path / "спустыми.db"
        склад = VacancyStorage(db_path=путь)
        склад.save_currency_rates(КУРСЫ)
        склад.save_vacancies_incremental(pd.DataFrame([
            вакансия("без_зарплаты", "RUB", None),
            вакансия("дешёвая", "RUB", 50_000),
            вакансия("дорогая", "RUB", 300_000),
        ]))
        склад.close()
        monkeypatch.setattr(
            storage_module, "VacancyStorage", lambda *a, **k: VacancyStorage(db_path=путь)
        )

        # При возрастании пустая встала бы первой и читалась бы как самая
        # дешёвая, хотя про неё просто ничего не известно.
        assert порядок("asc") == ["дешёвая", "дорогая", "без_зарплаты"]
        assert порядок("desc") == ["дорогая", "дешёвая", "без_зарплаты"]
