"""
Ответы сервера для экрана «Как устроено».

Экран рисует схему по живым числам и разбирает поиск по шагам. Здесь
проверяется, что числа берутся из базы, что отказ одной части не гасит
остальные и что объяснение поиска считает тот же код, что сам поиск.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from src import system_state
from src.config import settings
from src.search import lexical, собрать_документ, служба
from src.texts import хэш as хэш_текста


@pytest.fixture
def база():
    """База с тремя вакансиями: одна снята, одна найдена не по запросу."""
    from src.storage import VacancyStorage

    хранилище = VacancyStorage(db_path=settings.db_path)
    хранилище.save_vacancies_incremental(pd.DataFrame([
        {"vacancy_id": "1", "vacancy_name": "Дизайнер интерьеров", "employer_name": "Студия",
         "all_skills": "3ds Max", "skill_count": 1, "salary_from": 100000,
         # Ссылку на текст вакансии ставит разбор; здесь — тем же хэшем.
         "_описание": "Дизайн квартир.", "text_hash": хэш_текста("Дизайн квартир.")},
        {"vacancy_id": "2", "vacancy_name": "Python разработчик", "employer_name": "Код",
         "all_skills": "Python", "skill_count": 1},
        {"vacancy_id": "3", "vacancy_name": "Сотрудник ресторана", "employer_name": "АРТ РЕСТ"},
    ]))
    with хранилище.engine.begin() as conn:
        conn.exec_driver_sql("UPDATE vacancies SET off_query = 1 WHERE vacancy_id = '3'")
        conn.exec_driver_sql("UPDATE vacancies SET is_active = 0 WHERE vacancy_id = '2'")
    хранилище.close()

    conn = sqlite3.connect(settings.db_path)
    lexical.записать(conn, [
        собрать_документ("1", "Дизайнер интерьеров", "3ds Max", None, "Дизайн квартир.", "Студия"),
        собрать_документ("2", "Python разработчик", "Python", None, "", "Код"),
        собрать_документ("3", "Сотрудник ресторана", "", None, "", "АРТ РЕСТ"),
    ])
    conn.commit()
    conn.close()
    return settings.db_path


class TestСостояние:

    def test_без_базы_экран_получает_пустые_части_а_не_сбой(self):
        состояние = system_state.собрать()
        assert состояние["база"] is None and состояние["поиск"] is None
        assert состояние["надзор"]["хранить_дней"] == 30

    def test_числа_базы_живые(self, база):
        данные = system_state.собрать()["база"]
        assert данные["вакансий"] == 2, "найденная не по запросу в счёт не идёт"
        assert данные["активных"] == 1
        assert данные["не_по_запросу"] == 1
        assert данные["с_описанием"] == 1 and данные["текстов"] == 1

    def test_индексы_поиска_посчитаны(self, база):
        поиск = system_state.собрать()["поиск"]
        assert поиск["документов"] == 3 and поиск["слов_в_словаре"] > 0
        assert поиск["векторов"] == 0 and поиск["модель_поднята"] is False

    def test_разбор_знает_словарь_и_долю_с_навыками(self, база):
        разбор = system_state.собрать()["разбор"]
        assert разбор["навыков_в_словаре"] > 100, "словарь навыков лежит в репозитории"
        assert разбор["с_навыками"] == 2 and разбор["с_зарплатой"] == 1

    def test_сбора_ещё_не_было(self, база):
        сбор = system_state.собрать()["сбор"]
        assert сбор == {**сбор, "идёт": False, "запусков": 0, "последний": None}
        assert сбор["поля_поиска"] == ["name", "description"]

    def test_отказ_одной_части_не_гасит_остальные(self, база, monkeypatch):
        def упасть(conn):
            raise RuntimeError("словарь повреждён")

        monkeypatch.setattr(system_state, "_разбор", упасть)
        состояние = system_state.собрать()
        assert состояние["разбор"] is None
        assert состояние["база"]["вакансий"] == 2

    def test_подробности_оповещений_на_экран_не_идут(self, tmp_path, monkeypatch):
        """Экран открыт каждому, кто вошёл; текст исключения — для администратора."""
        from src import alerts

        журнал = tmp_path / "оповещения.jsonl"
        monkeypatch.setattr(alerts, "КАНАЛЫ", {})
        alerts.сообщить(alerts.Отказ(причина="network", подробности="ConnectionError: 10.0.0.1:8080"), журнал=журнал)
        monkeypatch.setattr(alerts, "файл_оповещений", lambda: журнал)

        оповещения = system_state.собрать()["надзор"]["оповещения"]
        assert оповещения == [{
            "заголовок": "Источник недоступен", "когда": оповещения[0]["когда"], "доставлено": False, "проба": False,
        }]

    def test_замер_читается_из_файла_а_не_из_разметки(self, tmp_path, monkeypatch):
        файл = tmp_path / "замер.json"
        monkeypatch.setattr(system_state, "файл_замера", lambda: файл)
        assert system_state.собрать()["замер"] is None

        файл.write_text('{"запросов": 18, "способы": {"слова": {"ndcg": 0.7}}}', encoding="utf-8")
        assert system_state.собрать()["замер"]["способы"]["слова"]["ndcg"] == 0.7


class TestОбъяснениеПоиска:

    def test_без_индекса_объяснять_нечего(self):
        assert служба.объяснить("дизайнер") is None

    def test_шаги_поиска_с_настоящими_вакансиями(self, база):
        шаги = служба.объяснить("дизайнера интерьеров")
        assert шаги["разбор"]["группы"] == [["дизайнер"], ["интерьер"]]
        assert шаги["слова"]["первые"][0]["название"] == "Дизайнер интерьеров"
        assert шаги["слова"]["первые"][0]["почему"] == "в названии"
        assert шаги["итог"]["первые"][0]["место_по_словам"] == 1

    def test_объяснение_видит_те_же_вакансии_что_экран(self, база):
        """Снятая с публикации и найденная не по запросу в объяснение не попадают."""
        assert служба.объяснить("python")["итог"]["найдено"] == 0
        assert служба.объяснить("ресторана")["итог"]["найдено"] == 0

    def test_без_модели_смысл_не_участвует_и_это_сказано(self, база):
        смысл = служба.объяснить("дизайнер")["смысл"]
        assert смысл["участвовал"] is False and смысл["доступен"] is False and смысл["первые"] == []

    def test_замена_в_запросе_названа(self, база):
        conn = sqlite3.connect(settings.db_path)
        lexical.записать(conn, [собрать_документ(f"д{n}", "Дизайнер", "Figma") for n in range(4)])
        conn.commit()
        conn.close()
        assert служба.объяснить("дизайнр")["разбор"]["замены"] == {"дизайнр": "дизайнер"}
