"""
Рублёвый вид аналитики: одна гистограмма вместо семи.

Гистограмма строилась внутри одной валюты, и чтобы увидеть рынок
целиком, человеку приходилось листать семь графиков, держа в голове,
что 6 000 000 сум и 300 000 рублей — соседние величины. Рублёвый
эквивалент сводит их в один график.

Проверяется то, что легко сломать незаметно: что эквивалент считается по
всей выборке, что границы корзин берутся из данных (а не задаются
словами «50k–100k», бессмысленными для сумов), что дата курса едет
вместе с числами и что записи без курса не теряются молча.

Запуск: pytest tests/test_аналитика_в_рублях.py -v
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
from web.app.main import get_distribution

КУРСЫ = Курсы(
    на_дату=date(2026, 9, 9),
    значения={"RUB": 1.0, "USD": 86.473, "UZS": 0.00733485},
)


def вакансия(vacancy_id: str, currency: str, salary_from: float) -> dict:
    return {
        "vacancy_id": vacancy_id,
        # Название и работодатель у каждой свои: вакансии с одинаковой
        # парой считаются копиями одной вакансии по городам и в
        # зарплатных числах схлопываются в одну (S5).
        "vacancy_name": f"Аналитик данных {vacancy_id}",
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


ВЫБОРКА = (
    [вакансия(f"rub{i}", "RUB", 80000 + i * 10000) for i in range(6)]
    + [вакансия(f"uzs{i}", "UZS", 5_000_000 + i * 1_000_000) for i in range(6)]
    + [вакансия(f"usd{i}", "USD", 2000 + i * 500) for i in range(6)]
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
class TestРублёвыйВид:
    """Эквивалент считается по всей выборке, а не по выбранной валюте."""

    def test_в_рублёвую_гистограмму_входят_все_валюты(self):
        ответ = get_distribution(currency="RUB")

        assert ответ["salary_sample"] == 6, "валютный вид — только рубли"
        assert ответ["salary_sample_rub"] == 18, "рублёвый вид — вся выборка"
        assert len(ответ["salary_histogram_rub"]) > 0

    def test_выбор_валюты_не_меняет_рублёвый_вид(self):
        """Вид не зависит от селекта валюты — поэтому тот и выключается."""
        по_рублям = get_distribution(currency="RUB")
        по_сумам = get_distribution(currency="UZS")

        assert по_рублям["salary_histogram_rub"] == по_сумам["salary_histogram_rub"]
        assert по_рублям["salary_stats_rub"] == по_сумам["salary_stats_rub"]
        # А валютный вид, наоборот, меняется вместе с выбором.
        assert по_рублям["salary_histogram"] != по_сумам["salary_histogram"]

    def test_границы_корзин_из_данных_а_не_из_словаря(self):
        корзины = get_distribution(currency="RUB")["salary_histogram_rub"]

        нижняя = корзины[0]["from"]
        верхняя = корзины[-1]["to"]
        # Сумы в эквиваленте дают ~37 000 ₽, доллары — до ~380 000 ₽:
        # шкала должна накрыть обе группы, а не встать на круглых числах.
        assert нижняя < 50000 < верхняя
        assert all(к["count"] >= 0 for к in корзины)
        assert sum(к["count"] for к in корзины) == 18, "ни одна запись не потерялась"

    def test_дата_курса_едет_вместе_с_числами(self):
        ответ = get_distribution(currency="RUB")

        assert ответ["rate_date"] == "2026-09-09"
        assert ответ["salary_stats_rub"]["basis"] == "equivalent"

    def test_записи_без_курса_посчитаны(self, tmp_path, monkeypatch):
        """Валюта, которой нет в курсах ЦБ, не исчезает молча."""
        путь = tmp_path / "сбезкурса.db"
        склад = VacancyStorage(db_path=путь)
        склад.save_currency_rates(КУРСЫ)
        склад.save_vacancies_incremental(pd.DataFrame(
            ВЫБОРКА + [вакансия("kzt1", "KZT", 400_000), вакансия("kzt2", "KZT", 500_000)]
        ))
        склад.close()
        monkeypatch.setattr(
            storage_module, "VacancyStorage", lambda *a, **k: VacancyStorage(db_path=путь)
        )

        ответ = get_distribution(currency="RUB")

        assert ответ["without_rate"] == 2
        assert ответ["salary_sample_rub"] == 18, "тенге без курса в эквивалент не вошли"
