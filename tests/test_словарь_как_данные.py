"""
Словарь навыков как данные и синонимы (S7‑1, S7‑3).

Главная проверка здесь — отрицательная: «C#» и «C++» имеют одинаковое
написание без пробелов и регистра, и любая автоматика свела бы два
разных языка в один. Синонимы должны оставаться списком, проверенным
человеком, и код обязан вести себя как список, а не как правило.
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import skills_store  # noqa: E402
from src.normalize import навыки_работодателя  # noqa: E402

СЛОВАРЬ = {
    "hard": ["python", "sql"],
    "soft": ["коммуникация"],
    "tools": ["docker"],
    "synonyms": {
        "3ds Max": ["3dmax", "3d max", "3д макс"],
        "JavaScript": ["java script"],
        "Photoshop": [],
    },
}


@pytest.fixture
def свой_словарь(tmp_path, monkeypatch):
    путь = tmp_path / "skills.yaml"
    путь.write_text(yaml.safe_dump(СЛОВАРЬ, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(skills_store, "ПУТЬ_СЛОВАРЯ", путь)
    return путь


class TestЗагрузка:

    def test_читает_файл_данных(self, свой_словарь):
        словарь = skills_store.загрузить()

        assert словарь["hard"] == ["python", "sql"]
        assert словарь["tools"] == ["docker"]
        assert "3ds Max" in словарь["synonyms"]

    def test_без_файла_берёт_конфиг(self, tmp_path, monkeypatch):
        # Совместимость: пока перенос не сделан, продукт работает как
        # раньше, а не остаётся без навыков.
        monkeypatch.setattr(skills_store, "ПУТЬ_СЛОВАРЯ", tmp_path / "нет.yaml")

        словарь = skills_store.загрузить()

        assert isinstance(словарь["hard"], list)
        assert словарь["synonyms"] == {}

    def test_битый_файл_не_оставляет_без_навыков(self, tmp_path, monkeypatch):
        путь = tmp_path / "skills.yaml"
        путь.write_text("{не yaml: [", encoding="utf-8")
        monkeypatch.setattr(skills_store, "ПУТЬ_СЛОВАРЯ", путь)

        словарь = skills_store.загрузить()

        assert isinstance(словарь["hard"], list)


class TestСинонимы:

    def test_вариант_приводится_к_канону(self, свой_словарь):
        таблица = skills_store.таблица_синонимов()

        assert skills_store.привести_к_канону("3dmax", таблица) == "3ds Max"
        assert skills_store.привести_к_канону("3D Max", таблица) == "3ds Max"
        assert skills_store.привести_к_канону("3д макс", таблица) == "3ds Max"

    def test_канон_остаётся_каноном(self, свой_словарь):
        # Код, приводящий навык к канону, не должен знать, был ли навык
        # уже каноническим.
        таблица = skills_store.таблица_синонимов()

        assert skills_store.привести_к_канону("3ds Max", таблица) == "3ds Max"

    def test_регистр_решается_сам(self, свой_словарь):
        # Достаточно, чтобы канон был в списке: варианты, отличающиеся
        # только регистром, вносить не нужно.
        таблица = skills_store.таблица_синонимов()

        assert skills_store.привести_к_канону("photoshop", таблица) == "Photoshop"
        assert skills_store.привести_к_канону("PHOTOSHOP", таблица) == "Photoshop"

    def test_незнакомое_название_не_трогается(self, свой_словарь):
        таблица = skills_store.таблица_синонимов()

        assert skills_store.привести_к_канону("Kubernetes", таблица) == "Kubernetes"

    def test_разные_языки_не_сводятся(self, свой_словарь):
        # Ради этого случая таблица и составляется руками: «C#» и «C++»
        # без пробелов и регистра выглядят одинаково.
        таблица = skills_store.таблица_синонимов()

        assert skills_store.привести_к_канону("C#", таблица) == "C#"
        assert skills_store.привести_к_канону("C++", таблица) == "C++"

    def test_пустое_название(self, свой_словарь):
        assert skills_store.привести_к_канону("", skills_store.таблица_синонимов()) == ""


class TestБезДублей:

    def test_повторы_убираются(self):
        assert skills_store.без_дублей(["Docker", "docker", " DOCKER "]) == ["Docker"]

    def test_порядок_сохраняется(self):
        assert skills_store.без_дублей(["SQL", "Python", "sql"]) == ["SQL", "Python"]

    def test_пустые_отбрасываются(self):
        assert skills_store.без_дублей(["", "  ", "Go"]) == ["Go"]


class TestНавыкиРаботодателя:

    def test_варианты_написания_схлопываются(self, свой_словарь):
        # В базе «3ds Max» и «3D Max» стояли в топе двумя строками,
        # деля между собой 221 упоминание.
        навыки = навыки_работодателя({
            "key_skills": [{"name": "3D Max"}, {"name": "3dmax"}, {"name": "Java Script"}]
        })

        assert навыки == ["3ds Max", "JavaScript"]

    def test_разные_навыки_остаются_разными(self, свой_словарь):
        навыки = навыки_работодателя({"key_skills": [{"name": "C++"}, {"name": "C#"}]})

        assert навыки == ["C++", "C#"]

    def test_порядок_работодателя_сохраняется(self, свой_словарь):
        # Первым он обычно называет главное.
        навыки = навыки_работодателя({
            "key_skills": [{"name": "SQL"}, {"name": "3dmax"}, {"name": "Docker"}]
        })

        assert навыки == ["SQL", "3ds Max", "Docker"]


class TestНаписаниеДляПоказа:
    """
    Как навык выглядит в топах (S7‑3d).

    Прежде здесь стоял `str.title()`, и он дробил статистику наравне с
    разным написанием: словарный «Оценка Персонала» и названный
    работодателем «Оценка персонала» считались разными навыками по 237
    и 154 упоминания.
    """

    def test_аббревиатура_из_таблицы(self, свой_словарь):
        таблица = skills_store.таблица_синонимов()

        # В словаре навык лежит в нижнем регистре, и title() давал «Llm».
        assert skills_store.для_показа("photoshop", таблица) == "Photoshop"

    def test_русская_фраза_не_становится_title_кейсом(self, свой_словарь):
        таблица = skills_store.таблица_синонимов()
        известные = skills_store.известные_названия()

        assert skills_store.для_показа("Оценка Персонала", таблица, известные) == "Оценка персонала"
        assert skills_store.для_показа("Грамотная Речь", таблица, известные) == "Грамотная речь"

    def test_предлог_внутри_фразы(self, свой_словарь):
        таблица = skills_store.таблица_синонимов()

        assert skills_store.для_показа("Работа С Клиентами", таблица) == "Работа с клиентами"
        assert skills_store.для_показа("Внимательность К Деталям", таблица) == "Внимательность к деталям"

    def test_латиница_не_трогается(self, свой_словарь):
        # Работодатель пишет «MS Office» и «Adobe Photoshop» сам, и знать
        # лучше него мы не можем.
        таблица = skills_store.таблица_синонимов()

        assert skills_store.для_показа("MS Office", таблица) == "MS Office"
        assert skills_store.для_показа("Adobe Photoshop", таблица) == "Adobe Photoshop"
        assert skills_store.для_показа("Power BI", таблица) == "Power BI"

    def test_1С_остаётся_собой(self, свой_словарь):
        # Заглавная «С» здесь по делу, а не от title().
        таблица = skills_store.таблица_синонимов()

        assert skills_store.для_показа("1С", таблица) == "1С"

    def test_первая_буква_поднимается(self, свой_словарь):
        таблица = skills_store.таблица_синонимов()

        assert skills_store.для_показа("подбор персонала", таблица) == "Подбор персонала"

    def test_пустое_название(self, свой_словарь):
        assert skills_store.для_показа("", skills_store.таблица_синонимов()) == ""
