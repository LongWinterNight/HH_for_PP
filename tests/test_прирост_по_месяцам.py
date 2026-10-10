"""
Ряд «Новых вакансий в месяц».

Считается по `first_seen_at` — дате, когда вакансия впервые попала в
базу. По дате публикации так считать нельзя: источник отдаёт только
открытые вакансии, и в старых месяцах остались бы одни долгожители —
график показывал бы вымирающий рынок там, где остальные вакансии просто
успели закрыться.

Проверяется то, что легко сломать незаметно: непрерывность оси, пометка
незакрытого месяца и то, что архив из ряда не выпадает.

Запуск: pytest tests/test_прирост_по_месяцам.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import src.storage as storage_module
from src.storage import VacancyStorage
from web.app.main import new_vacancies_by_month


def вакансия(vacancy_id: str, first_seen: str, is_active: int = 1) -> dict:
    return {
        "vacancy_id": vacancy_id,
        "vacancy_name": "Аналитик данных",
        "published_at": "2026-09-01T10:00:00+0300",
        "first_seen_at": first_seen,
        "last_seen_at": first_seen,
        "is_active": is_active,
        "salary_from": 100000,
        "salary_to": None,
        "salary_currency": "RUB",
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


def месяцы_назад(n: int) -> str:
    """Дата в прошлом, привязанная к сегодняшнему дню, а не к календарю.

    Тест не должен ломаться оттого, что наступил новый месяц.
    """
    момент = (pd.Timestamp.now().normalize().replace(day=1) - pd.DateOffset(months=n))
    return момент.strftime("%Y-%m-%d 12:00:00")


@pytest.fixture
def база(tmp_path, monkeypatch):
    путь = tmp_path / "проба.db"
    склад = VacancyStorage(db_path=путь)
    склад.save_vacancies_incremental(pd.DataFrame([
        вакансия("сейчас1", месяцы_назад(0)),
        вакансия("сейчас2", месяцы_назад(0)),
        # Между этим месяцем и позапрошлым — дыра: сбора не было.
        вакансия("давно", месяцы_назад(3)),
        # Снятая с публикации: в месяце, когда её нашли, она была новой.
        вакансия("снятая", месяцы_назад(3), is_active=0),
    ]))
    склад.close()
    monkeypatch.setattr(
        storage_module, "VacancyStorage", lambda *a, **k: VacancyStorage(db_path=путь)
    )
    yield путь


@pytest.mark.usefixtures("база")
class TestРяд:
    def test_ось_непрерывна(self):
        """Месяц без сбора отдаётся нулём, а не пропускается: пропуск
        сжимает ось, и два столбца оказываются рядом, хотя между ними
        полгода."""
        ряд = new_vacancies_by_month(months=12)["series"]

        assert len(ряд) == 12
        месяцы = [т["month"] for т in ряд]
        assert месяцы == sorted(месяцы), "месяцы идут подряд и по порядку"
        assert any(т["count"] == 0 for т in ряд), "дыра между сборами показана нулём"

    def test_текущий_месяц_помечен(self):
        """Он ещё не кончился, и без пометки читается как обвал."""
        ряд = new_vacancies_by_month(months=12)["series"]

        assert ряд[-1]["partial"] is True
        assert all(т["partial"] is False for т in ряд[:-1])

    def test_архив_из_ряда_не_выпадает(self):
        """Снятая вакансия в месяц своей находки всё равно была новой."""
        ответ = new_vacancies_by_month(months=12)

        assert ответ["total"] == 4, "снятая посчитана вместе с активными"

    def test_ряд_знает_с_какого_месяца_шли_сборы(self):
        """Ноль до первого сбора — отсутствие сбора, а не пустой рынок."""
        ответ = new_vacancies_by_month(months=12)

        assert ответ["collected_since"] == месяцы_назад(3)[:7]
        assert ответ["basis"] == "first_seen_at"

    def test_длина_ряда_ограничена(self):
        """Запрос на тысячу месяцев не должен строить тысячу столбцов."""
        assert len(new_vacancies_by_month(months=1000)["series"]) == 60
        assert len(new_vacancies_by_month(months=0)["series"]) == 1
