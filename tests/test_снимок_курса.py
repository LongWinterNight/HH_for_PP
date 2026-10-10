"""
Снимок метрик хранит курс своего дня.

Снимок лежит в основе трендов и живёт годами. Без курса своего дня
рублёвый тренд посчитать нечем: пересчёт старого снимка сегодняшними
котировками смешал бы два движения — рынок и валюту. Падение рубля на
десять процентов подняло бы эквивалент сумовых зарплат на те же десять,
и график показал бы рост зарплат там, где выросла только цена валюты.

Запуск: pytest tests/test_снимок_курса.py -v
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.cbr_rates import Курсы
from src.storage import VacancyStorage

КУРСЫ = Курсы(
    на_дату=date(2026, 9, 9),
    значения={"RUB": 1.0, "USD": 86.473, "UZS": 0.00733485},
)


def вакансия(vacancy_id: str, currency: str = "RUB", salary_from: float = 100000) -> dict:
    return {
        "vacancy_id": vacancy_id,
        "vacancy_name": "Аналитик данных",
        "published_at": "2026-09-01T10:00:00+0300",
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


@pytest.fixture
def склад(tmp_path):
    store = VacancyStorage(db_path=tmp_path / "проба.db")
    yield store
    store.close()


class TestКурсВСнимке:
    def test_снимок_запоминает_котировки_и_их_день(self, склад):
        склад.save_currency_rates(КУРСЫ)
        склад.save_vacancies_incremental(pd.DataFrame([
            вакансия("1"), вакансия("2", "UZS", 6_000_000)
        ]))

        склад.save_metrics_snapshot()
        точка = склад.get_metrics_snapshots(limit=1)[0]

        assert точка["rate_date"] == "2026-09-09"
        assert точка["rates"]["USD"] == pytest.approx(86.473)
        assert точка["rates"]["UZS"] == pytest.approx(0.00733485)

    def test_медианы_по_валютам_лежат_рядом_с_курсом(self, склад):
        """Вместе они дают рублёвую медиану того дня задним числом."""
        склад.save_currency_rates(КУРСЫ)
        склад.save_vacancies_incremental(pd.DataFrame([
            вакансия(f"uzs{i}", "UZS", 6_000_000) for i in range(3)
        ]))

        склад.save_metrics_snapshot()
        точка = склад.get_metrics_snapshots(limit=1)[0]

        медиана_сум = точка["medians_by_currency"]["UZS"]["median"]
        курс = точка["rates"]["UZS"]
        assert медиана_сум * курс == pytest.approx(6_000_000 * 0.00733485)

    def test_без_курсов_снимок_всё_равно_снимается(self, склад):
        """Курса может не быть — это не повод терять точку истории."""
        склад.save_vacancies_incremental(pd.DataFrame([вакансия("1")]))

        склад.save_metrics_snapshot()
        точка = склад.get_metrics_snapshots(limit=1)[0]

        assert точка["rate_date"] is None
        assert точка["rates"] == {}
        assert точка["active_vacancies"] == 1
