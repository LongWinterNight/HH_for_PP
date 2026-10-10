"""
Даты жизненного цикла читаются без молчаливых потерь.

В базе они записаны в двух видах: с микросекундами и без — datetime.now()
их даёт, разобранная дата из файла сбора нет. `pd.to_datetime` выводит
единый формат по первым строкам и на остальных возвращает NaT, а с
errors="coerce" делает это молча. На живой базе так терялось 352 записи
из 1891: девятнадцать процентов не доезжали до расчётов, и график
прироста базы показал бы провал там, где ничего не происходило.

Запуск: pytest tests/test_разбор_дат.py -v
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.storage import VacancyStorage


def вакансия(vacancy_id: str) -> dict:
    return {
        "vacancy_id": vacancy_id,
        "vacancy_name": "Аналитик данных",
        "published_at": "2026-09-01T10:00:00+0300",
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


@pytest.fixture
def склад_с_двумя_форматами(tmp_path):
    """База, где половина дат с микросекундами, половина без.

    Именно так выглядит живая база: формат зависит от того, кто писал
    запись — сбор или разбор старого файла.
    """
    путь = tmp_path / "проба.db"
    склад = VacancyStorage(db_path=путь)
    склад.save_vacancies_incremental(pd.DataFrame([вакансия(str(i)) for i in range(6)]))
    склад.close()

    conn = sqlite3.connect(путь)
    conn.execute(
        "UPDATE vacancies SET first_seen_at = '2026-09-07 22:57:19.791881', "
        "last_seen_at = '2026-09-07 22:57:19.791881', "
        "created_at = '2026-09-07 22:57:19.791881' "
        "WHERE CAST(vacancy_id AS INTEGER) < 3"
    )
    conn.execute(
        "UPDATE vacancies SET first_seen_at = '2026-09-07 17:23:42', "
        "last_seen_at = '2026-09-07 17:23:42', "
        "created_at = '2026-09-07 17:23:42' "
        "WHERE CAST(vacancy_id AS INTEGER) >= 3"
    )
    conn.commit()
    conn.close()

    склад = VacancyStorage(db_path=путь)
    yield склад
    склад.close()


class TestДатыНеТеряются:
    def test_оба_формата_читаются(self, склад_с_двумя_форматами):
        df = склад_с_двумя_форматами.get_all_vacancies()

        assert len(df) == 6
        for колонка in ("first_seen_at", "last_seen_at", "created_at"):
            assert df[колонка].notna().all(), f"{колонка}: часть записей потерялась при разборе"

    def test_даты_приходят_датами_а_не_строками(self, склад_с_двумя_форматами):
        """Иначе каждый расчёт разбирает их заново — и снова теряет."""
        df = склад_с_двумя_форматами.get_all_vacancies()

        assert pd.api.types.is_datetime64_any_dtype(df["first_seen_at"])

    def test_группировка_по_месяцам_видит_всю_выборку(self, склад_с_двумя_форматами):
        """Тот самый расчёт, ради которого дефект и нашёлся."""
        df = склад_с_двумя_форматами.get_all_vacancies()

        по_месяцам = df["first_seen_at"].dt.to_period("M").value_counts()

        assert по_месяцам.sum() == 6
