"""
Средней зарплаты нет в ответах API.

Средняя по выборке, где есть одна вакансия на 800 000, перестаёт
описывать рынок: её тянет выброс. На экране её заменили медианой, но в
ответах она какое-то время оставалась «для совместимости» — и любой
новый экран мог показать её снова, не зная, что вопрос уже решён.
Тест закрепляет решение на уровне ответа, а не экрана.

Динамика зарплат из дашборда удалена (E3): недельный ряд не только
считал среднюю, но и складывал рубли, сумы и тенге в одну точку.
Проверка на её отсутствие — здесь же: вернуть ряд «как было» значит
вернуть оба дефекта сразу.

Запуск: pytest tests/test_api_bez_среднего.py -v
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
from web.app.main import (
    collect_kpi_values,
    get_analytics,
    get_dashboard,
    get_distribution,
    get_kpi_metrics,
)

# Признаки средней в имени поля. Ключ проверяется целиком по частям,
# разделённым подчёркиванием: `avg`, `avg_salary`, `salary_avg`, `mean`.
ПРИЗНАКИ_СРЕДНЕЙ = {"avg", "average", "mean"}


def вакансия(vacancy_id: str, salary_from: float = 100000, currency: str = "RUB") -> dict:
    """Строка в том виде, в каком её отдаёт нормализация сбора."""
    return {
        "vacancy_id": vacancy_id,
        "vacancy_name": "Аналитик данных",
        "published_at": "2026-09-01T10:00:00+0300",
        "salary_from": salary_from,
        "salary_to": salary_from * 1.5,
        "salary_currency": currency,
        "employer_name": f"Компания {vacancy_id}",
        "employer_id": vacancy_id,
        "employer_url": "",
        "vacancy_url": "",
        "experience": "От 1 года до 3 лет",
        "employment": "Полная занятость",
        "schedule": "Удалённо",
        "area": "Москва",
        "all_skills": "python, sql",
        "hard_skills": "python, sql",
        "soft_skills": "коммуникация",
        "tools": "",
        "skill_count": 3,
        "hard_skill_count": 2,
        "soft_skill_count": 1,
        "tools_count": 0,
    }


def ключи_со_средней(узел, путь: str = "") -> list[str]:
    """Пути ко всем ключам, которые называют среднюю."""
    найдено = []
    if isinstance(узел, dict):
        for ключ, значение in узел.items():
            полный = f"{путь}.{ключ}" if путь else str(ключ)
            if isinstance(ключ, str) and ПРИЗНАКИ_СРЕДНЕЙ & set(ключ.lower().split("_")):
                найдено.append(полный)
            найдено += ключи_со_средней(значение, полный)
    elif isinstance(узел, list):
        for i, значение in enumerate(узел):
            найдено += ключи_со_средней(значение, f"{путь}[{i}]")
    return найдено


@pytest.fixture
def база(tmp_path, monkeypatch):
    """Своя база с выборкой больше MIN_SAMPLE и с выбросом.

    Выборки меньше порога отдаются прочерками, и тогда тест прошёл бы,
    ничего не проверив: полей нет просто потому, что нет чисел.
    """
    путь = tmp_path / "проба.db"
    склад = VacancyStorage(db_path=путь)
    строки = [вакансия(str(i), salary_from=100000 + i * 5000) for i in range(10)]
    строки.append(вакансия("выброс", salary_from=800000))
    строки.append(вакансия("usd", salary_from=3000, currency="USD"))
    склад.save_vacancies_incremental(pd.DataFrame(строки))
    склад.close()

    monkeypatch.setattr(
        storage_module, "VacancyStorage", lambda *args, **kwargs: VacancyStorage(db_path=путь)
    )
    yield путь


@pytest.mark.usefixtures("база")
class TestОтветыБезСредней:
    """Ни один эндпоинт не отдаёт среднюю зарплату."""

    def test_kpi_дашборда(self):
        # Значения передаются явно: при прямом вызове параметры по
        # умолчанию остались бы объектами Query, а не значениями.
        ответ = get_kpi_metrics(
            period="all_time", domain=None, regions=None, experience=None, salary_only=False
        )
        assert ключи_со_средней(ответ["metrics"]) == []
        assert "median_salary" in ответ["metrics"], "медиана осталась на месте"

    def test_сводка_аналитики(self):
        ответ = get_analytics()
        assert ключи_со_средней(ответ["salary_stats"]) == []
        assert "median" in ответ["salary_stats"]

    def test_статистика_по_валютам(self):
        ответ = get_distribution(currency="RUB")
        по_валютам = ответ["salary_stats_by_currency"]
        assert ключи_со_средней(по_валютам) == []
        assert по_валютам, "выборка достаточна, статистика по валютам не пуста"
        for код, значения in по_валютам.items():
            assert {"min", "max", "median", "count"} <= set(значения), код

    def test_динамики_зарплат_на_дашборде_нет(self):
        """Ряд по смеси валют не отдаётся ни по неделям, ни по дням.

        Динамику зарплат строит экран аналитики внутри одной валюты
        (E4). Здесь её нет, и «вернуть, раз всё равно считается» — не
        починка, а возврат к числу, которое врало по построению.
        """
        ответ = get_dashboard()

        assert "salary_trend" not in ответ
        assert "salaries" not in ответ.get("sparklines", {})
        # Счётчики остались: они мертвы, но не врут.
        assert set(ответ["sparklines"]) == {"vacancies", "skills"}

    def test_валюты_на_дашборде(self):
        ответ = get_dashboard()
        по_валютам = ответ["vacancies_by_currency"]
        assert ключи_со_средней(по_валютам) == []
        assert "avg_salary" not in ответ, "средней нет и на верхнем уровне"
        assert по_валютам["RUB"]["median_salary"] is not None


def test_метрики_не_считают_среднюю():
    """Не считаем то, чего не отдаём: средней нет и в расчёте."""
    df = pd.DataFrame([вакансия(str(i), salary_from=100000 + i * 5000) for i in range(10)])
    значения = collect_kpi_values(df)

    assert ключи_со_средней(значения) == []
    assert значения["median_salary"] is not None
