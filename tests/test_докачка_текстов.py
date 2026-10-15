"""
Докачка текстов описаний (S10‑13).

Проверяется то, на чём докачка могла бы навредить: навыки работодателя
не стираются, зарплата и даты не переписываются полугодовой карточкой,
повторный запуск ничего не меняет, а вакансия не по запросу текстов не
получает.
"""

from __future__ import annotations

import json
import sqlite3

import pandas as pd
import pytest

from src import text_backfill as докачка
from src.config import settings

ОПИСАНИЕ = (
    "<p><strong>Требования:</strong> уверенное владение Figma и SQL, "
    "внимательность к деталям.</p>"
)


@pytest.fixture
def словарь(tmp_path, monkeypatch):
    from src import skills_store

    файл = tmp_path / "skills.yaml"
    файл.write_text("hard:\n- sql\nsoft:\n- внимательность\ntools:\n- figma\n", encoding="utf-8")
    monkeypatch.setattr(skills_store, "ПУТЬ_СЛОВАРЯ", файл)
    return файл


@pytest.fixture
def база(словарь):
    from src.storage import VacancyStorage

    хранилище = VacancyStorage(db_path=settings.db_path)
    хранилище.save_vacancies_incremental(pd.DataFrame([
        {"vacancy_id": "1", "vacancy_name": "Дизайнер", "employer_name": "Альфа", "area": "Москва",
         "salary_from": 150000, "salary_currency": "RUR", "employer_skills": "Adobe XD",
         "all_skills": "Adobe XD", "skill_count": 1},
        {"vacancy_id": "2", "vacancy_name": "Аналитик", "employer_name": "Бета", "skill_count": 0},
        {"vacancy_id": "3", "vacancy_name": "Не по запросу", "employer_name": "Гамма", "off_query": 1, "skill_count": 0},
    ]))
    yield хранилище
    хранилище.close()


def _строка(conn, ид):
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM vacancies WHERE vacancy_id = ?", (ид,)).fetchone()


class TestОчередь:

    def test_в_очереди_только_вакансии_по_запросу_без_текста(self, база):
        conn = sqlite3.connect(settings.db_path)
        иды = {с["vacancy_id"] for с in докачка.без_текста(conn)}
        conn.close()
        assert иды == {"1", "2"}, "вакансия не по запросу в аналитику не входит — текст ей не нужен"


class TestСырыеФайлы:

    def test_берётся_версия_с_самым_длинным_описанием(self, tmp_path):
        (tmp_path / "a.json").write_text(json.dumps([{"id": "1", "description": "коротко"}]), encoding="utf-8")
        (tmp_path / "b.json").write_text(json.dumps([{"id": "1", "description": ОПИСАНИЕ}, {"id": "9", "description": "чужая"}]), encoding="utf-8")
        найдено = докачка.из_сырых(tmp_path, {"1", "2"})
        assert set(найдено) == {"1"}, "без описания и не из нужных — не берутся"
        assert найдено["1"]["description"] == ОПИСАНИЕ

    def test_битый_файл_не_роняет_поиск(self, tmp_path):
        (tmp_path / "битый.json").write_text("{не json", encoding="utf-8")
        (tmp_path / "ok.json").write_text(json.dumps([{"id": "1", "description": ОПИСАНИЕ}]), encoding="utf-8")
        assert set(докачка.из_сырых(tmp_path, {"1"})) == {"1"}


class TestСлияние:

    def test_навыки_работодателя_из_базы_не_теряются(self):
        строка = {"vacancy_id": "1", "vacancy_name": "Дизайнер", "employer_skills": "Adobe XD, Figma"}
        карточка = {"description": ОПИСАНИЕ, "key_skills": [{"name": "figma"}, {"name": "Sketch"}]}
        вакансия = докачка.слить(строка, карточка)
        assert [н["name"] for н in вакансия["key_skills"]] == ["Adobe XD", "Figma", "Sketch"]

    def test_название_из_базы_а_описание_из_карточки(self):
        вакансия = докачка.слить({"vacancy_id": "1", "vacancy_name": "Новое название"},
                                 {"name": "Старое название", "description": ОПИСАНИЕ})
        assert вакансия["name"] == "Новое название"
        assert вакансия["description"] == ОПИСАНИЕ


class TestЗапись:

    def test_текст_и_навыки_записаны_прочее_как_было(self, база):
        conn = sqlite3.connect(settings.db_path)
        строки = {с["vacancy_id"]: с for с in докачка.без_текста(conn)}
        итог = докачка.записать(база, [(строки["1"], {"description": ОПИСАНИЕ, "salary": {"from": 1}})])
        запись = _строка(conn, "1")
        conn.close()

        assert итог["вакансий"] == 1
        assert запись["text_hash"], "у вакансии появилась ссылка на текст"
        assert запись["has_details"] == 1
        навыки = {н.strip().lower() for н in запись["all_skills"].split(",")}
        assert {"figma", "sql", "внимательность", "adobe xd"} <= навыки
        assert запись["salary_from"] == 150000, "зарплата из полугодовой карточки не переписывает базу"
        assert запись["vacancy_name"] == "Дизайнер"

    def test_текст_можно_прочитать(self, база):
        conn = sqlite3.connect(settings.db_path)
        строка = {с["vacancy_id"]: с for с in докачка.без_текста(conn)}["2"]
        докачка.записать(база, [(строка, {"description": ОПИСАНИЕ})])
        хэш = _строка(conn, "2")["text_hash"]
        conn.close()
        assert база.читать_текст(хэш) == ОПИСАНИЕ

    def test_повторный_запуск_ничего_не_меняет(self, база):
        conn = sqlite3.connect(settings.db_path)
        строка = {с["vacancy_id"]: с for с in докачка.без_текста(conn)}["2"]
        первый = докачка.записать(база, [(строка, {"description": ОПИСАНИЕ})])
        второй = докачка.записать(база, [(строка, {"description": ОПИСАНИЕ + "<p>правка</p>"})])
        хэш = _строка(conn, "2")["text_hash"]
        в_очереди = {с["vacancy_id"] for с in докачка.без_текста(conn)}
        conn.close()
        assert первый["вакансий"] == 1 and второй["вакансий"] == 0
        assert база.читать_текст(хэш) == ОПИСАНИЕ, "текст — снимок первого получения"
        assert "2" not in в_очереди, "вакансия с текстом из очереди уходит"

    def test_пустое_описание_не_записывается(self, база):
        conn = sqlite3.connect(settings.db_path)
        строка = {с["vacancy_id"]: с for с in докачка.без_текста(conn)}["2"]
        итог = докачка.записать(база, [(строка, {"description": "   "})])
        assert итог["вакансий"] == 0
        assert not _строка(conn, "2")["text_hash"]
        conn.close()


class TestИсточник:

    def test_карточка_из_кэша_без_запроса(self):
        class Кэш:
            def получить_карточку(self, ид):
                return {"id": ид, "description": ОПИСАНИЕ}

        class Клиент:
            def get_vacancy_details(self, ид):
                raise AssertionError("запроса быть не должно")

        карточка, запрос = докачка.карточка_источника("1", Клиент(), Кэш())
        assert карточка["description"] == ОПИСАНИЕ and запрос is False

    def test_скачанная_карточка_ложится_в_кэш(self):
        положено = {}

        class Кэш:
            def получить_карточку(self, ид):
                return None

            def сохранить_карточку(self, ид, ответ):
                положено[ид] = ответ

        class Клиент:
            def get_vacancy_details(self, ид):
                return {"id": ид, "description": ОПИСАНИЕ}

        карточка, запрос = докачка.карточка_источника("7", Клиент(), Кэш())
        assert запрос is True and "7" in положено
