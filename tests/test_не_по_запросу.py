"""
Вакансии, найденные не по запросу.

По «Арт-директор» источник отдавал рестораны работодателя «АРТ РЕСТ»:
он искал слова запроса во всех полях, включая название компании. Здесь
проверяется вся цепочка: поиск идёт только по названию и описанию,
собранное раньше помечается по доказанной причине, а помеченное не
попадает в аналитику и не теряется из базы.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.relevance import встречается, запросы, не_по_запросу


class TestСопоставление:

    def test_другая_форма_слова_совпадает(self):
        assert встречается("рендер", "Опыт рендеринга в Corona")
        assert встречается("дизайнер", "Ищем дизайнера интерьеров")

    def test_слитное_и_раздельное_написание_совпадают(self):
        """Буквальное сравнение объявило бы мусором почти всю выдачу по «3dsmax»."""
        assert встречается("3dsmax", "Уверенное владение 3ds Max")
        assert встречается("Арт-директор", "Требуется артдиректор")

    def test_все_слова_запроса_обязательны(self):
        assert встречается("Арт-директор", "арт-директор в агентство")
        assert not встречается("Арт-директор", "директор ресторана")

    def test_разметка_не_мешает(self):
        assert встречается("figma", "<p>Работа в <strong>Figma</strong></p>")

    def test_короткий_запрос_не_ищется_внутри_слов(self):
        """«ai» нашлось бы в любом «email» и «training»."""
        assert not встречается("ai", "Пишите на email, пройдите training")

    def test_пустое_не_совпадает(self):
        assert not встречается("", "текст") and not встречается("запрос", "")


class TestНеПоЗапросу:

    def test_найдена_по_названию_компании(self):
        """Тот самый случай: «арт» в названии компании, в вакансии — ресторан."""
        assert не_по_запросу(
            "Арт-директор", "Сотрудник ресторана ROSTIC`S", навыки="Касса, Работа с гостями",
            описание="Приём заказов, работа на кассе, уборка зала.", компания="АРТ РЕСТ",
        ) is True

    def test_запрос_в_названии_вакансии(self):
        assert не_по_запросу("Арт-директор", "Арт-директор в агентство", компания="АРТ РЕСТ") is False

    def test_запрос_в_описании(self):
        assert не_по_запросу(
            "рендер", "Дизайнер интерьеров", описание="Нужен опыт рендеринга", компания="Студия",
        ) is False

    def test_запрос_среди_навыков(self):
        assert не_по_запросу("3dsmax", "Дизайнер", навыки="3ds Max, AutoCAD", компания="Бюро") is False

    def test_синоним_источника_не_помечается(self):
        """
        Слов запроса нет нигде, и в названии компании тоже. Источник
        подставил синоним — доказать обратное нечем, и пометки нет.
        Первая версия правила помечала такие, и 642 вакансии из 1 419
        оказались законными.
        """
        assert не_по_запросу(
            "Разработчик", "Java Backend Developer", описание="Spring, Kafka, PostgreSQL",
            компания="IMOT.IO",
        ) is None

    def test_несколько_запросов_достаточно_одного(self):
        assert не_по_запросу("Арт-директор, дизайнер", "Графический дизайнер", компания="АРТ РЕСТ") is False

    def test_без_запроса_судить_не_о_чем(self):
        assert не_по_запросу("", "Что угодно", компания="АРТ РЕСТ") is None

    def test_запросы_разбираются_из_строки(self):
        assert запросы("Арт-директор,  дизайнер ,") == ["Арт-директор", "дизайнер"]


class TestПоискИКэш:

    def test_поиск_уходит_с_полями_названия_и_описания(self, monkeypatch):
        from src.api_client import HHAPIClient, ПОЛЯ_ПОИСКА

        отправлено = {}
        клиент = HHAPIClient(email="test@example.com")
        monkeypatch.setattr(клиент, "_make_request", lambda url, params: отправлено.update(params) or {"items": []})

        клиент.search_vacancies("Арт-директор")

        assert отправлено["search_field"] == ["name", "description"]
        assert "company_name" not in ПОЛЯ_ПОИСКА

    def test_ключ_кэша_зависит_от_полей_поиска(self, tmp_path, monkeypatch):
        """Иначе кэш суток давности вернул бы прежнюю выдачу с ресторанами."""
        import src.api_client as клиент
        from src.api_cache import APICache

        кэш = APICache(cache_db=tmp_path / "cache.db")
        прежний = кэш._generate_key("Арт-директор", 0, 100)
        monkeypatch.setattr(клиент, "ПОЛЯ_ПОИСКА", ("name",))
        assert кэш._generate_key("Арт-директор", 0, 100) != прежний


class TestХранилище:

    @pytest.fixture
    def storage(self, tmp_path):
        from src.storage import VacancyStorage

        store = VacancyStorage(db_path=tmp_path / "test.db")
        store.save_vacancies_incremental(pd.DataFrame([
            {"vacancy_id": "1", "vacancy_name": "Арт-директор", "source_keyword": "Арт-директор"},
            {"vacancy_id": "2", "vacancy_name": "Сотрудник ресторана", "source_keyword": "Арт-директор"},
        ]))
        with store.engine.begin() as conn:
            conn.exec_driver_sql("UPDATE vacancies SET off_query = 1 WHERE vacancy_id = '2'")
        yield store
        store.close()

    def test_помеченная_не_попадает_в_аналитику(self, storage):
        assert list(storage.get_all_vacancies()["vacancy_id"]) == ["1"]

    def test_помеченная_не_теряется_из_базы(self, storage):
        assert len(storage.get_all_vacancies(include_off_query=True)) == 2

    def test_счётчики_сходятся(self, storage):
        assert storage.get_vacancy_count() == 1
        assert storage.get_off_query_count() == 1

    def test_пометку_снимает_только_явная_запись(self, storage):
        """Повторная запись без признака пометку не трогает."""
        storage.save_vacancies_incremental(pd.DataFrame([
            {"vacancy_id": "2", "vacancy_name": "Сотрудник ресторана", "source_keyword": "Арт-директор"},
        ]))
        assert storage.get_off_query_count() == 1

        # Сбор с узким поиском нашёл её законно — пометка снимается.
        storage.save_vacancies_incremental(pd.DataFrame([
            {"vacancy_id": "2", "vacancy_name": "Сотрудник ресторана", "source_keyword": "ресторан", "off_query": 0},
        ]))
        assert storage.get_off_query_count() == 0
