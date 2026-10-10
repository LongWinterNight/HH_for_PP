"""
Механика поиска навыков в тексте.

Замер на 600 вакансиях показал, что словарь находит лишь часть того, что
заведомо есть в тексте. Причины были три, и каждая закрепляется здесь:

- границы слова через \b не работают со спецсимволами: «C#» и «Node.js»
  не находились вовсе;
- порог длины в три символа выбрасывал Go, C#, QA, UX, ML, JS — они
  лежали в словаре, но до поиска не доходили;
- совпадение внутри чужого слова засчитывалось: «Git» находился в
  «github.com», «Access» — в «access/refresh tokens».

Запуск: pytest tests/test_поиск_навыков.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.normalize import PreparedSkill, SkillDictionaries, find_skills


def находит(навык: str, текст: str) -> bool:
    return bool(PreparedSkill(навык).word.search(текст.lower()))


class TestГраницыСоСпецсимволами:
    def test_решётка_и_точка_не_мешают(self):
        assert находит("c#", "разработка на c# и .net")
        assert находит("node.js", "стек: node.js, react")
        assert находит("c++", "опыт c++ обязателен")
        assert находит("ci/cd", "настройка ci/cd пайплайна")

    def test_навык_не_находится_внутри_чужого_слова(self):
        """«Git» в «github.com» — не Git, а часть адреса."""
        assert not находит("git", "ссылка на github.com/itcase")
        assert not находит("git", "используем gitlab для сборки")
        assert not находит("c#", "непонятное c## обозначение")

    def test_перечисление_стека_через_слэш_читается(self):
        """«React/JS/Express» — три навыка, а не один непонятный.

        Косая черта справа не запрещена намеренно. Запрет спасал бы от
        «access/refresh tokens» (2 случая на девять тысяч описаний), но
        ломал перечисления стека (206 случаев) — цена в сто раз выше
        пользы, полнота падала с 81,3 % до 79,4 %.
        """
        assert находит("react", "стек: react/js/express/postgresql")
        assert находит("python", "python/django разработчик")


class TestКороткиеНавыки:
    """Порог длины выбрасывал целый класс настоящих навыков."""

    def test_двухсимвольный_навык_ищется(self, словари):
        assert "go" in найденные("опыт разработки на go от года", словари)
        assert "c#" in найденные("требования: знание c# и sql", словари)

    def test_короткий_навык_требует_окружения(self, словари):
        """«go» посреди английской фразы — не язык программирования."""
        assert "go" not in найденные("we go home after work", словари)

    def test_односимвольные_не_ищутся_вовсе(self, словари):
        """Язык R не отличить от предлога — это осознанная потеря."""
        assert "r" not in найденные("требования: знание r и python", словари)

    def test_длинный_навык_окружения_не_требует(self, словари):
        """«PostgreSQL» ни с чем не спутать."""
        assert "postgresql" in найденные("postgresql, redis, kafka", словари)


class TestСловарьБезОбщихСлов:
    """Слово, которое само по себе ничего не значит, — не навык."""

    def test_обрезков_составных_навыков_нет(self, словари):
        имена = {s.name for s in словари.hard + словари.soft + словари.tools}

        for обрезок in ("контроль", "взаимодействие", "развитие", "организация"):
            assert обрезок not in имена, f"«{обрезок}» приходит из «{обрезок} версий» и подобного"

    def test_составные_формы_остались(self, словари):
        имена = {s.name for s in словари.hard + словари.soft + словари.tools}

        assert "контроль качества" in имена
        assert "развитие сотрудников" in имена

    def test_требование_к_кандидату_не_навык(self, словари):
        имена = {s.name for s in словари.hard + словари.soft + словари.tools}

        assert "высшее образование" not in имена


class TestБазовыеТермины:
    """Дыры словаря: их отсутствие давало больше всего пропусков."""

    def test_веб_основы_находятся(self, словари):
        текст = "требования: html, css, api, http, json"
        нашли = найденные(текст, словари)

        for навык in ("html", "css", "api", "http", "json"):
            assert навык in нашли, f"«{навык}» не найден"

    def test_нотации_находятся(self, словари):
        нашли = найденные("знание нотаций uml и bpmn обязательно", словари)

        assert "uml" in нашли and "bpmn" in нашли

    def test_отраслевые_системы_находятся(self, словари):
        """Без них не-ИТ рынок в продукте не виден."""
        нашли = найденные("опыт внедрения wms, tms и erp систем", словари)

        assert "wms" in нашли and "tms" in нашли and "erp" in нашли


import pytest  # noqa: E402


@pytest.fixture(scope="module")
def словари():
    return SkillDictionaries.from_config()


def найденные(текст: str, словари) -> set:
    все = словари.hard + словари.soft + словари.tools
    return {н.lower() for н in find_skills(текст.lower(), все)}
