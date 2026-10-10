"""
Регион в запросе к источнику и срез в ключе кэша (S4‑2a, S4‑2c).

Регион — не удобство поиска, а единственный способ уйти глубже предела
выдачи: источник отдаёт не больше 2000 вакансий на запрос, и тот же
запрос по регионам даёт в сумме больше. Поэтому проверяется не только
то, что параметр уходит, но и то, что кэш не подставляет ответ одного
среза другому: иначе резка молча вернула бы одни и те же вакансии.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api_cache import APICache  # noqa: E402
from src.api_client import HHAPIClient  # noqa: E402


class TestРегионВЗапросе:

    def клиент(self):
        клиент = HHAPIClient()
        клиент._make_request = MagicMock(return_value={"items": [], "found": 0})
        return клиент

    def параметры(self, клиент):
        return клиент._make_request.call_args[0][1]

    def test_регион_уходит_в_запрос(self):
        клиент = self.клиент()
        клиент.search_vacancies("Рекрутер", area="1")
        assert self.параметры(клиент)["area"] == "1"

    def test_без_региона_параметра_нет(self):
        # Пустой area источник понимает иначе, чем его отсутствие.
        клиент = self.клиент()
        клиент.search_vacancies("Рекрутер")
        assert "area" not in self.параметры(клиент)

    def test_пустая_строка_не_уходит(self):
        клиент = self.клиент()
        клиент.search_vacancies("Рекрутер", area="")
        assert "area" not in self.параметры(клиент)

    def test_регион_не_ломает_остальные_параметры(self):
        клиент = self.клиент()
        клиент.search_vacancies("Рекрутер", page=3, per_page=100,
                                date_from="2026-08-01", area="2")
        п = self.параметры(клиент)
        assert п["text"] == "Рекрутер"
        assert п["page"] == 3
        assert п["date_from"] == "2026-08-01"
        assert п["area"] == "2"


class TestКлючКэша:

    def test_разные_регионы_разные_ключи(self):
        кэш = APICache()
        по_москве = кэш._generate_key("Рекрутер", 0, 100, area="1")
        по_питеру = кэш._generate_key("Рекрутер", 0, 100, area="2")
        assert по_москве != по_питеру

    def test_регион_и_его_отсутствие_разные_ключи(self):
        кэш = APICache()
        assert кэш._generate_key("Рекрутер", 0, 100) != кэш._generate_key(
            "Рекрутер", 0, 100, area="1"
        )

    def test_разные_даты_разные_ключи(self):
        кэш = APICache()
        раньше = кэш._generate_key("Рекрутер", 0, 100, date_from="2026-08-01")
        позже = кэш._generate_key("Рекрутер", 0, 100, date_from="2026-09-01")
        assert раньше != позже

    def test_ключ_запроса_без_среза_несёт_поля_поиска(self):
        # Прежде тест закреплял ключ «как раньше», чтобы накопленный кэш
        # остался годным. С 10.10.2026 это стало вредным: поиск идёт по
        # названию и описанию, а не везде, и прежний кэш хранит выдачу с
        # вакансиями, найденными по названию компании. Старые записи
        # обязаны перестать находиться — поэтому поля входят в ключ.
        import hashlib

        кэш = APICache()
        прежний = hashlib.md5("search:Рекрутер:0:100".encode()).hexdigest()
        ожидаемый = hashlib.md5("search:Рекрутер:0:100:fields=name,description".encode()).hexdigest()
        assert кэш._generate_key("Рекрутер", 0, 100) == ожидаемый != прежний
