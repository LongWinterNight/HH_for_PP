"""
Память между запросами: таблица вакансий и готовые ответы.

Память имеет право существовать только при одном условии — она не
отдаёт устаревшее. Поэтому главное, что здесь проверяется: любая запись
в базу, из этого процесса или из чужого, делает следующий ответ свежим.

Запуск: pytest tests/test_память_запросов.py -v
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from src import data_cache
from src.storage import VacancyStorage


def _вакансии(сколько: int, с: int = 0) -> pd.DataFrame:
    return pd.DataFrame([
        {"vacancy_id": str(i), "vacancy_name": f"Вакансия {i}", "employer_name": f"Компания {i}",
         "salary_from": 100000 + i, "salary_currency": "RUB", "area": "Москва",
         "experience": "Нет опыта", "published_at": "2026-09-01T10:00:00+0300"}
        for i in range(с, с + сколько)
    ])


@pytest.fixture
def база(tmp_path):
    """Своя база с включённой памятью: под тестами она по умолчанию выключена."""
    путь = tmp_path / "память.db"
    склад = VacancyStorage(db_path=путь)
    склад.save_vacancies_incremental(_вакансии(10))
    склад.close()
    data_cache.сбросить()
    data_cache.включить(True)
    yield путь
    data_cache.включить(None)
    data_cache.сбросить()


def _прочитать(путь) -> pd.DataFrame:
    склад = VacancyStorage(db_path=путь)
    try:
        return склад.get_all_vacancies()
    finally:
        склад.close()


class TestТаблица:

    def test_второе_чтение_берётся_из_памяти(self, база):
        первая = _прочитать(база)
        вторая = _прочитать(база)
        assert len(первая) == len(вторая) == 10
        assert data_cache.счётчики["таблица_прочитана"] == 1
        assert data_cache.счётчики["таблица_из_памяти"] == 1

    def test_запись_из_этого_процесса_делает_ответ_свежим(self, база):
        _прочитать(база)
        склад = VacancyStorage(db_path=база)
        склад.save_vacancies_incremental(_вакансии(5, с=100))
        склад.close()

        assert len(_прочитать(база)) == 15, "после записи в базу таблица обязана быть новой"

    def test_запись_чужим_соединением_делает_ответ_свежим(self, база):
        # Так пишут сбор по расписанию и фоновый разбор моделью: другой
        # процесс, о котором сервер ничего не знает.
        _прочитать(база)
        чужое = sqlite3.connect(база)
        чужое.execute("UPDATE vacancies SET is_active = 0 WHERE vacancy_id IN ('0', '1', '2')")
        чужое.commit()
        чужое.close()

        assert len(_прочитать(база)) == 7, "снятые с публикации вакансии из памяти не отдаются"

    def test_правка_полученной_таблицы_соседям_не_достаётся(self, база):
        первая = _прочитать(база)
        первая["salary_from"] = 0
        первая["лишняя"] = 1

        вторая = _прочитать(база)
        assert (вторая["salary_from"] > 0).all() and "лишняя" not in вторая.columns

    def test_разные_условия_чтения_хранятся_отдельно(self, база):
        чужое = sqlite3.connect(база)
        чужое.execute("UPDATE vacancies SET is_active = 0 WHERE vacancy_id = '0'")
        чужое.commit()
        чужое.close()
        склад = VacancyStorage(db_path=база)
        try:
            assert len(склад.get_all_vacancies()) == 9
            assert len(склад.get_all_vacancies(include_inactive=True)) == 10
            assert len(склад.get_all_vacancies()) == 9, "архивная выборка активную не подменила"
        finally:
            склад.close()

    def test_одновременные_запросы_читают_таблицу_один_раз(self, база):
        # Экран шлёт пять запросов разом. Без очереди на чтение каждый
        # читал бы таблицу сам: память помогала бы только со второго захода.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(5) as пул:
            длины = list(пул.map(lambda _: len(_прочитать(база)), range(5)))

        assert длины == [10] * 5
        assert data_cache.счётчики["таблица_прочитана"] == 1
        assert data_cache.счётчики["таблица_из_памяти"] == 4

    def test_выключенная_память_читает_каждый_раз(self, база):
        data_cache.включить(False)
        _прочитать(база)
        _прочитать(база)
        assert data_cache.счётчики["таблица_прочитана"] == 0 and data_cache.счётчики["таблица_из_памяти"] == 0

    def test_под_тестами_память_по_умолчанию_выключена(self):
        data_cache.включить(None)
        assert data_cache.включена() is False, "тесты подменяют базу на лету — чужой ответ им достаться не должен"


class TestОтветы:

    @pytest.fixture
    def расчёт(self, база, monkeypatch):
        from src.config import settings

        monkeypatch.setattr(settings, "db_path", база)
        вызовы = []

        @data_cache.запомнить
        def посчитать(что: str = "а"):
            вызовы.append(что)
            return {"что": что, "список": [1, 2, 3]}

        return посчитать, вызовы

    def test_повторный_запрос_не_считает_заново(self, расчёт):
        посчитать, вызовы = расчёт
        assert посчитать(что="а") == посчитать(что="а")
        assert вызовы == ["а"]

    def test_другие_параметры_считаются_отдельно(self, расчёт):
        посчитать, вызовы = расчёт
        посчитать(что="а")
        посчитать(что="б")
        assert вызовы == ["а", "б"]

    def test_запись_в_базу_сбрасывает_готовые_ответы(self, расчёт, база):
        посчитать, вызовы = расчёт
        посчитать(что="а")
        чужое = sqlite3.connect(база)
        чужое.execute("UPDATE vacancies SET area = 'Казань' WHERE vacancy_id = '0'")
        чужое.commit()
        чужое.close()

        посчитать(что="а")
        assert вызовы == ["а", "а"], "после изменения базы ответ считается заново"

    def test_правка_полученного_ответа_в_память_не_попадает(self, расчёт):
        посчитать, _ = расчёт
        первый = посчитать(что="а")
        первый["список"].append(99)
        первый["что"] = "испорчено"
        assert посчитать(что="а") == {"что": "а", "список": [1, 2, 3]}

    def test_минута_на_часах_тоже_сбрасывает(self, расчёт, monkeypatch):
        # Ответ зависит не только от базы: «за неделю» завтра — другая
        # неделя, даже если в базу никто не писал.
        посчитать, вызовы = расчёт
        посчитать(что="а")
        сейчас = data_cache.time.time()
        monkeypatch.setattr(data_cache.time, "time", lambda: сейчас + data_cache.ОКНО_СЕКУНД + 1)
        посчитать(что="а")
        assert вызовы == ["а", "а"]

    def test_память_ответов_не_растёт_без_предела(self, расчёт, monkeypatch):
        monkeypatch.setattr(data_cache, "ОТВЕТОВ", 5)
        посчитать, _ = расчёт
        for i in range(20):
            посчитать(что=str(i))
        assert len(data_cache._ответы) <= 5


class TestСводкаШапки:
    """Счётчики, которые экраны берут вместо расчёта дашборда."""

    def test_число_активных_сходится_с_таблицей_по_которой_считают_графики(self, база):
        чужое = sqlite3.connect(база)
        чужое.execute("UPDATE vacancies SET is_active = 0 WHERE vacancy_id IN ('0', '1')")
        чужое.execute("UPDATE vacancies SET off_query = 1 WHERE vacancy_id = '2'")
        чужое.commit()
        чужое.close()

        склад = VacancyStorage(db_path=база)
        try:
            сводка = склад.get_active_summary()
            assert сводка["active"] == len(склад.get_all_vacancies()) == 7
        finally:
            склад.close()

    def test_счёт_по_валютам_считает_только_вакансии_в_работе(self, база):
        чужое = sqlite3.connect(база)
        чужое.execute("UPDATE vacancies SET salary_currency = 'KZT' WHERE vacancy_id IN ('3', '4', '5')")
        чужое.execute("UPDATE vacancies SET salary_currency = NULL WHERE vacancy_id = '6'")
        чужое.execute("UPDATE vacancies SET is_active = 0 WHERE vacancy_id = '3'")
        чужое.commit()
        чужое.close()

        склад = VacancyStorage(db_path=база)
        try:
            assert склад.get_active_summary()["currencies"] == {"RUB": 6, "KZT": 2}
        finally:
            склад.close()
