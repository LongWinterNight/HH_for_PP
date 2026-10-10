"""
Две медианы дашборда: по рублёвым вакансиям и по эквиваленту.

Плитка называлась «Медиана зарплаты · RUB», а считалась по всем валютам
разом: 6 000 000 сум входили в неё числом 6 000 000. Подпись называла
валюту, которой число не соответствовало, — на живой базе это давало
90 000 там, где по рублёвым вакансиям было 82 000.

Теперь метрики две, и каждая описывает то, что обещает: `median_salary`
— рублёвые вакансии, `median_salary_rub` — всю выборку, приведённую к
рублям по курсу ЦБ.

Запуск: pytest tests/test_медиана_дашборда.py -v
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import src.storage as storage_module
from src.cbr_rates import Курсы
from src.storage import VacancyStorage
from web.app.main import collect_kpi_values, get_kpi_metrics

КУРСЫ = Курсы(
    на_дату=date(2026, 9, 9),
    значения={"RUB": 1.0, "USD": 86.473, "UZS": 0.00733485},
)


def вакансия(vacancy_id: str, currency: str, salary_from: float) -> dict:
    return {
        "vacancy_id": vacancy_id,
        "vacancy_name": "Аналитик данных",
        "published_at": "2026-09-01T10:00:00+0300",
        "salary_from": salary_from,
        "salary_to": None,
        "salary_currency": currency,
        "employer_name": f"Компания {vacancy_id}",
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


# Пять рублёвых вакансий (медиана 100 000) и пять в сумах, номинал
# которых на два порядка больше, а эквивалент — заметно меньше.
ВЫБОРКА = (
    [вакансия(f"rub{i}", "RUB", 80000 + i * 10000) for i in range(5)]
    + [вакансия(f"uzs{i}", "UZS", 5_000_000 + i * 1_000_000) for i in range(5)]
)


@pytest.fixture
def база(tmp_path, monkeypatch):
    путь = tmp_path / "проба.db"
    склад = VacancyStorage(db_path=путь)
    склад.save_currency_rates(КУРСЫ)
    склад.save_vacancies_incremental(pd.DataFrame(ВЫБОРКА))
    склад.close()
    monkeypatch.setattr(
        storage_module, "VacancyStorage", lambda *a, **k: VacancyStorage(db_path=путь)
    )
    yield путь


@pytest.mark.usefixtures("база")
class TestМедианыНеСмешиваются:
    """Номиналы разных валют не складываются в одно число."""

    def test_рублёвая_медиана_считает_только_рубли(self):
        метрики = get_kpi_metrics(
            period="all_time", domain=None, regions=None, experience=None, salary_only=False
        )["metrics"]

        assert метрики["median_salary"]["value"] == 100000
        assert метрики["median_salary"]["sample"] == 5, "в неё входят только рублёвые"
        assert метрики["median_salary"]["currency"] == "RUB"

    def test_медиана_по_эквиваленту_описывает_всю_выборку(self):
        метрики = get_kpi_metrics(
            period="all_time", domain=None, regions=None, experience=None, salary_only=False
        )["metrics"]
        по_эквиваленту = метрики["median_salary_rub"]

        assert по_эквиваленту["sample"] == 10, "входят и рубли, и сумы"
        # Сумы в эквиваленте дешевле рублёвых вакансий, поэтому медиана
        # всей выборки ниже рублёвой — а по номиналам была бы выше.
        assert по_эквиваленту["value"] < метрики["median_salary"]["value"]
        assert по_эквиваленту["basis"] == "equivalent"

    def test_дата_курса_едет_вместе_с_числом(self):
        метрики = get_kpi_metrics(
            period="all_time", domain=None, regions=None, experience=None, salary_only=False
        )["metrics"]

        assert метрики["median_salary_rub"]["rate_date"] == "2026-09-09"

    def test_тренд_по_эквиваленту_не_показывается(self):
        """Снимки не хранят курс своего дня — тренд был бы курсовым."""
        метрики = get_kpi_metrics(
            period="all_time", domain=None, regions=None, experience=None, salary_only=False
        )["metrics"]
        по_эквиваленту = метрики["median_salary_rub"]

        assert "trend_percent" not in по_эквиваленту
        assert по_эквиваленту["trend_unavailable"]


def test_обе_метрики_считаются_вместе():
    """Расчёт отдаёт оба числа и оба объёма выборки."""
    df = pd.DataFrame(ВЫБОРКА)
    df["salary_from_rub"] = [s["salary_from"] if s["salary_currency"] == "RUB"
                             else s["salary_from"] * 0.00733485 for s in ВЫБОРКА]

    значения = collect_kpi_values(df)

    assert значения["median_salary"] == 100000
    assert значения["salary_sample"] == 5
    assert значения["salary_sample_rub"] == 10
    assert значения["median_salary_rub"] is not None
