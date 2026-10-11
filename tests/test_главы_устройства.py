"""
Данные глав экрана «Как устроено».

Экран показывает работу системы на одной настоящей вакансии. Здесь
проверяется главное обещание этих данных: подсветка навыка стоит там,
где навык действительно написан; числа очистки и зарплат посчитаны по
базе; отказ одной главы не гасит остальные.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from src import system_story
from src.config import settings
from src.texts import хэш as хэш_текста

ОПИСАНИЕ = (
    "<p>Мы — проектное бюро. Работаем с жилыми и общественными зданиями по всей стране, "
    "ведём объекты от эскиза до сдачи.</p><p><strong>Требования</strong></p>"
    "<ul><li>Уверенное владение AutoCAD</li><li>Разработка чертежей и спецификаций</li></ul>"
)


@pytest.fixture
def база():
    """Вакансия-пример с текстом, копии по городам, найденная не по запросу и зарплаты."""
    from src.storage import VacancyStorage

    строки = [
        {"vacancy_id": "1", "vacancy_name": "Чертёжник", "employer_name": "Бюро", "area": "Актобе",
         "all_skills": "Autocad, Чертежи, Работа в команде, Ответственность", "skill_count": 4,
         "tools": "Autocad", "hard_skills": "Чертежи", "employer_skills": "Работа в команде, Ответственность",
         "source_keyword": "чертежник", "salary_from": 140000, "salary_currency": "KZT",
         "_описание": ОПИСАНИЕ, "text_hash": хэш_текста(ОПИСАНИЕ)},
        # Одна вакансия в трёх городах.
        *[{"vacancy_id": f"к{i}", "vacancy_name": "Курьер", "employer_name": "Доставка", "area": город}
          for i, город in enumerate(["Казань", "Пермь", "Тула"])],
        {"vacancy_id": "чужая", "vacancy_name": "Сварщик", "employer_name": "Кадры Найм", "source_keyword": "найм"},
        {"vacancy_id": "снята", "vacancy_name": "Архивариус", "employer_name": "Архив"},
        # Зарплаты для распределения: тридцать ровных и одна в десять раз выше.
        *[{"vacancy_id": f"з{i}", "vacancy_name": f"Инженер {i}", "employer_name": f"Завод {i}"} for i in range(31)],
    ]
    хранилище = VacancyStorage(db_path=settings.db_path)
    хранилище.save_vacancies_incremental(pd.DataFrame(строки))
    хранилище.close()

    conn = sqlite3.connect(settings.db_path)
    conn.execute("UPDATE vacancies SET off_query = 1 WHERE vacancy_id = 'чужая'")
    conn.execute("UPDATE vacancies SET is_active = 0 WHERE vacancy_id = 'снята'")
    conn.execute("UPDATE vacancies SET salary_from_rub = 26647, salary_mode = 'MONTH' WHERE vacancy_id = '1'")
    for i in range(31):
        сумма = 1_000_000 if i == 30 else 80_000 + i * 1_000
        conn.execute("UPDATE vacancies SET salary_from_rub = ? WHERE vacancy_id = ?", (сумма, f"з{i}"))
    conn.commit()
    conn.close()

    # Ответ запоминается по состоянию файла базы; между тестами оно может совпасть.
    system_story._память.update(ключ=None, ответ=None)
    return settings.db_path


class TestГерой:

    def test_подсветка_стоит_там_где_навык_написан(self, база):
        отрывок = system_story.собрать()["герой"]["отрывок"]
        места = {отрывок["текст"][м["от"]:м["до"]].lower(): м for м in отрывок["навыки"]}
        assert "autocad" in места and места["autocad"]["как"] == "как написано"

    def test_навык_в_другой_форме_находится_и_это_сказано(self, база):
        отрывок = system_story.собрать()["герой"]["отрывок"]
        по_форме = [м for м in отрывок["навыки"] if м["как"] == "форма слова"]
        assert [отрывок["текст"][м["от"]:м["до"]] for м in по_форме] == ["чертежей"]
        assert по_форме[0]["навык"] == "Чертежи"

    def test_разметка_в_отрывок_не_попадает(self, база):
        текст = system_story.собрать()["герой"]["отрывок"]["текст"]
        assert "<" not in текст and "Требования" in текст

    def test_навык_работодателя_помечен_а_не_приписан_тексту(self, база):
        навыки = {н["название"]: н["откуда"] for н in system_story.собрать()["герой"]["навыки"]}
        assert навыки["Autocad"] == "отрывок"
        assert навыки["Ответственность"] == "работодатель"

    def test_хранение_считает_эту_вакансию(self, база):
        герой = system_story.собрать()["герой"]
        хранение = герой["хранение"]
        assert хранение["байт_текста"] == len(ОПИСАНИЕ.encode("utf-8"))
        assert 0 < хранение["байт_сжато"] < хранение["байт_текста"]
        assert "проектный" in хранение["слова"], "слова лежат в начальной форме: в тексте «проектное»"
        assert хранение["вектор"] == [] and хранение["размерность"] == 0, "векторы в тесте не считались"
        assert герой["зарплата"]["в_распределении"] is True

    def test_без_подходящей_вакансии_героя_нет(self):
        from src.storage import VacancyStorage

        хранилище = VacancyStorage(db_path=settings.db_path)
        хранилище.save_vacancies_incremental(pd.DataFrame([{"vacancy_id": "1", "vacancy_name": "Без текста"}]))
        хранилище.close()
        system_story._память.update(ключ=None, ответ=None)
        assert system_story.собрать()["герой"] is None


class TestОтрывок:

    def test_берётся_кусок_с_навыками_а_не_начало(self):
        текст = "О компании. " * 80 + "Требования: AutoCAD и Revit. " + "Условия. " * 80
        где = текст.index("AutoCAD")
        начало, конец = system_story._отрывок(текст, {"Autocad": [(где, где + 7)]})
        assert начало > 0 and начало <= где < конец
        assert конец - начало <= system_story.ЗНАКОВ_ОТРЫВКА

    def test_короткий_текст_идёт_целиком(self):
        assert system_story._отрывок("Короткий текст.", {}) == (0, 15)


class TestОчистка:

    def test_копии_сведены_к_вакансиям(self, база):
        копии = system_story.собрать()["очистка"]["копии"]
        assert (копии["строк"], копии["вакансий"]) == (3, 1)
        assert копии["пример"]["города"] == ["Казань", "Пермь", "Тула"]

    def test_пример_не_по_запросу_показывает_слово_в_названии_компании(self, база):
        чужие = system_story.собрать()["очистка"]["не_по_запросу"]
        assert чужие["скрыто"] == 1
        assert чужие["пример"] == {"название": "Сварщик", "компания": "Кадры Найм", "запрос": "найм"}

    def test_снятые_в_архиве(self, база):
        снятые = system_story.собрать()["очистка"]["снятые"]
        assert снятые["в_архиве"] == 1 and снятые["активных"] > 30


class TestЗарплаты:

    def test_выброс_сдвигает_среднюю_сильнее_медианы(self, база):
        з = system_story.собрать()["зарплаты"]
        assert з["вакансий"] == 32 and з["верхних"] == 1 and з["наибольшая"] == 1_000_000
        сдвиг_средней = з["средняя"] - з["средняя_без_верха"]
        сдвиг_медианы = з["медиана"] - з["медиана_без_верха"]
        assert сдвиг_средней > 10 * сдвиг_медианы > 0

    def test_все_зарплаты_либо_в_корзинах_либо_за_пределом(self, база):
        з = system_story.собрать()["зарплаты"]
        assert sum(з["корзины"]) + з["за_пределом"] == з["вакансий"]
        assert len(з["корзины"]) == system_story.КОРЗИН

    def test_на_горстке_зарплат_распределения_нет(self):
        from src.storage import VacancyStorage

        хранилище = VacancyStorage(db_path=settings.db_path)
        хранилище.save_vacancies_incremental(pd.DataFrame([{"vacancy_id": "1", "vacancy_name": "Одна"}]))
        хранилище.close()
        system_story._память.update(ключ=None, ответ=None)
        assert system_story.собрать()["зарплаты"] is None


class TestОтвет:

    def test_без_базы_главы_пусты_а_не_падают(self):
        assert system_story.собрать() == {"герой": None, "сбор": None, "очистка": None, "зарплаты": None}

    def test_отказ_одной_главы_не_гасит_остальные(self, база, monkeypatch):
        def сломано(conn):
            raise RuntimeError("нет героя")

        monkeypatch.setattr(system_story, "_герой", сломано)
        ответ = system_story.собрать()
        assert ответ["герой"] is None
        assert ответ["очистка"]["копии"]["вакансий"] == 1 and ответ["зарплаты"] is not None

    def test_сбора_не_было_глава_пуста(self, база):
        assert system_story.собрать()["сбор"] is None

    def test_запросы_последнего_сбора(self, база):
        conn = sqlite3.connect(база)
        conn.execute("INSERT INTO parser_runs (id, status, started_at) VALUES (7, 'completed', '2026-10-10 20:00:00')")
        conn.execute(
            "INSERT INTO run_queries (run_id, keyword, status, found, taken, pages, vacancies_new, vacancies_updated, duration_ms) "
            "VALUES (7, 'чертежник', 'complete', 120, 118, 2, 100, 10, 4000)"
        )
        conn.commit()
        conn.close()
        system_story._память.update(ключ=None, ответ=None)

        сбор = system_story.собрать()["сбор"]
        assert сбор["номер"] == 7 and сбор["взято"] == 118 and сбор["страниц"] == 2
        assert сбор["запросы"][0]["запрос"] == "чертежник"

    def test_повторный_запрос_берётся_из_памяти(self, база):
        assert system_story.собрать() is system_story.собрать()
