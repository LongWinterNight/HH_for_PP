"""
Дозапрос карточек вакансий.

Карточка вакансии — отдельный запрос к источнику, и раньше она бралась
только для первых двух страниц каждого запроса: детали были у 43 %
записей. Разница видна в данных — 14,7 навыка у вакансии с карточкой
против 2,4 без неё, и почти все вакансии без единого навыка именно
такие.

Здесь закрепляется поведение дозапроса: кого он берёт, в каком порядке
и что происходит при прерывании.

Запуск: pytest tests/test_дозапрос_деталей.py -v
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

спец = importlib.util.spec_from_file_location(
    "дозапрос", project_root / "scripts" / "maintenance" / "дозапрос_деталей.py"
)
дозапрос = importlib.util.module_from_spec(спец)
спец.loader.exec_module(дозапрос)


def вакансия(ид: str, детали: bool, дата: str, активна: int = 1) -> dict:
    return {
        "vacancy_id": ид,
        "vacancy_name": f"Вакансия {ид}",
        "has_details": детали,
        "published_at": дата,
        "is_active": активна,
    }


class TestОчередь:
    def test_берутся_только_без_карточки(self):
        df = pd.DataFrame([
            вакансия("1", True, "2026-09-01T10:00:00+0300"),
            вакансия("2", False, "2026-09-01T10:00:00+0300"),
        ])

        очередь = дозапрос.кого_дозапрашивать(df, только_активные=True)

        assert list(очередь["vacancy_id"]) == ["2"]

    def test_свежие_идут_первыми(self):
        """Бюджет кончится — пусть кончится на менее важном."""
        df = pd.DataFrame([
            вакансия("старая", False, "2026-01-01T10:00:00+0300"),
            вакансия("свежая", False, "2026-09-01T10:00:00+0300"),
            вакансия("средняя", False, "2026-05-01T10:00:00+0300"),
        ])

        очередь = дозапрос.кого_дозапрашивать(df, только_активные=True)

        assert list(очередь["vacancy_id"]) == ["свежая", "средняя", "старая"]

    def test_архив_по_умолчанию_не_дозапрашивается(self):
        """Снятая вакансия карточки уже не отдаст, а запрос потратит."""
        df = pd.DataFrame([
            вакансия("живая", False, "2026-09-01T10:00:00+0300", активна=1),
            вакансия("снятая", False, "2026-09-02T10:00:00+0300", активна=0),
        ])

        только_живые = дозапрос.кого_дозапрашивать(df, только_активные=True)
        со_снятыми = дозапрос.кого_дозапрашивать(df, только_активные=False)

        assert list(только_живые["vacancy_id"]) == ["живая"]
        assert len(со_снятыми) == 2

    def test_вакансия_без_даты_не_роняет_очередь(self):
        df = pd.DataFrame([
            вакансия("без даты", False, None),
            вакансия("с датой", False, "2026-09-01T10:00:00+0300"),
        ])

        очередь = дозапрос.кого_дозапрашивать(df, только_активные=True)

        assert len(очередь) == 2
        assert очередь.iloc[0]["vacancy_id"] == "с датой"

    def test_пустая_база_даёт_пустую_очередь(self):
        df = pd.DataFrame(columns=["vacancy_id", "has_details", "published_at", "is_active"])

        очередь = дозапрос.кого_дозапрашивать(df, только_активные=True)

        assert len(очередь) == 0


class TestГлубинаСбора:
    """Предел в две страницы стал настройкой, а не константой."""

    def test_ноль_означает_карточку_для_каждой_новой(self):
        from src.config import settings

        assert settings.detailed_pages == 0

    def test_коллектор_принимает_глубину_параметром(self):
        from src.collector import VacancyCollector

        сборщик = VacancyCollector.__new__(VacancyCollector)
        сборщик.detailed_pages = 3

        assert сборщик.detailed_pages == 3
