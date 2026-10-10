"""
Навыки, названные работодателем.

hh.ru отдаёт `key_skills` — список, который работодатель заполнил руками.
Продукт его не читал: навыки искались словарём по тексту описания, и всё,
чего в словаре нет, исчезало. Замер на файлах сборов: терялось 77 %
упоминаний, 402 из 477 уникальных названий.

Главное свойство, которое здесь закрепляется: навык от работодателя
доезжает до базы, даже если наш словарь о нём никогда не слышал. Через
словарь эти навыки не проходят намеренно — фильтрация выбрасывала бы
ровно то, ради чего поле и читается.

Запуск: pytest tests/test_навыки_работодателя.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.normalize import normalize_vacancy, навыки_работодателя
from src.storage import VacancyStorage


def вакансия(**поля) -> dict:
    основа = {
        "id": "1",
        "name": "Backend Developer",
        "published_at": "2026-09-01T10:00:00+0300",
        "snippet": {"requirement": "Опыт с PostgreSQL и Docker"},
    }
    основа.update(поля)
    return основа


def навыки(запись: dict) -> list:
    return [н.strip() for н in запись["all_skills"].split(",") if н.strip()]


class TestНавыкиДоезжают:
    def test_навык_вне_словаря_попадает_в_запись(self):
        """Ради этого поле и читается: 77 % названного нет в словаре."""
        запись = normalize_vacancy(вакансия(
            key_skills=[{"name": "FastStream"}, {"name": "NATS"}, {"name": "Dishka"}]
        ))

        для_проверки = {н.lower() for н in навыки(запись)}
        assert "faststream" in для_проверки
        assert "nats" in для_проверки
        assert "dishka" in для_проверки

    def test_названное_работодателем_хранится_отдельно(self):
        """По полю видно, что сказал источник, а что нашли мы."""
        запись = normalize_vacancy(вакансия(
            key_skills=[{"name": "FastStream"}, {"name": "PostgreSQL"}]
        ))

        assert запись["employer_skills"] == "FastStream, PostgreSQL"
        # Словарные категории остались только со словарными навыками:
        # категорию чужого навыка мы не знаем и придумывать не должны.
        assert "FastStream" not in запись["hard_skills"]

    def test_один_навык_из_двух_источников_не_задваивается(self):
        """«PostgreSQL» от источника и «postgresql» из словаря — одно."""
        запись = normalize_vacancy(вакансия(
            key_skills=[{"name": "PostgreSQL"}],
            snippet={"requirement": "Опыт с PostgreSQL"},
        ))

        сколько = sum(1 for н in навыки(запись) if н.lower() == "postgresql")
        assert сколько == 1
        assert запись["skill_count"] == len(навыки(запись))

    def test_порядок_работодателя_сохраняется(self):
        """Первым он обычно называет главное."""
        assert навыки_работодателя(вакансия(
            key_skills=[{"name": "Go"}, {"name": "Kafka"}, {"name": "Redis"}]
        )) == ["Go", "Kafka", "Redis"]

    def test_повторы_и_пустые_отсеиваются(self):
        assert навыки_работодателя(вакансия(
            key_skills=[{"name": "Go"}, {"name": "go"}, {"name": "  "}, {"name": "Go "}]
        )) == ["Go"]

    def test_вакансия_без_поля_разбирается_как_прежде(self):
        запись = normalize_vacancy(вакансия())

        assert запись["employer_skills"] == ""
        assert "Docker" in запись["hard_skills"]


class TestДоЗаписиВБазу:
    def test_навык_вне_словаря_доезжает_до_базы(self, tmp_path):
        """Сквозная проверка: от ответа источника до строки в таблице."""
        склад = VacancyStorage(db_path=tmp_path / "проба.db")
        try:
            запись = normalize_vacancy(вакансия(
                key_skills=[{"name": "Boolean search"}, {"name": "FastStream"}]
            ))
            склад.save_vacancies_incremental(pd.DataFrame([запись]))

            из_базы = склад.get_all_vacancies()
            assert len(из_базы) == 1
            строка = из_базы.iloc[0]

            assert "Boolean search" in строка["employer_skills"]
            assert "Boolean search" in строка["all_skills"]
            assert строка["skill_count"] >= 2
        finally:
            склад.close()
