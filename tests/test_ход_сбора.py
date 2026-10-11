"""
Процент готовности сбора.

Полоса показывала 99 % на втором запросе из пяти: собранное за весь
сбор делилось на найденное по текущему запросу. Здесь проверяется, что
единица работы — запрос, и что полоса не обещает конец раньше срока.
"""

from __future__ import annotations

from src.progress import возьмём, осталось_секунд, процент, страниц_ожидается
from tests.test_collector_modes import ЖурналКлиента, база, вакансия  # noqa: F401


class TestПроцент:

    def test_случай_со_снимка_экрана(self):
        """Второй запрос из пяти, 175 найдено, почти все просмотрены."""
        assert процент(2, 5, просмотрено=170, к_просмотру=175) == 39

    def test_второй_запрос_из_пяти_не_выше_сорока(self):
        for просмотрено in (0, 50, 175, 10_000):
            assert процент(2, 5, просмотрено, 175) <= 40

    def test_начало_запроса_равно_доле_пройденных(self):
        assert процент(1, 5) == 0
        assert процент(3, 5) == 40

    def test_пройденный_запрос_даёт_долю_целиком(self):
        assert процент(3, 5, запрос_пройден=True) == 60

    def test_сто_ставит_только_завершение(self):
        assert процент(5, 5, запрос_пройден=True) == 99
        assert процент(1, 1, просмотрено=100, к_просмотру=100) == 99

    def test_растёт_вместе_с_просмотренным(self):
        ход = [процент(1, 2, n, 1000) for n in range(0, 1001, 100)]
        assert ход == sorted(ход) and ход[0] == 0 and ход[-1] == 50

    def test_без_числа_запросов_процента_нет(self):
        assert процент(1, 0, 50, 100) == 0
        assert процент(0, 5, 50, 100) == 0

    def test_объём_запроса_неизвестен_до_первой_страницы(self):
        assert процент(2, 4, просмотрено=30, к_просмотру=0) == 25


class TestЗнаменатель:

    def test_найдено_больше_глубины_обхода(self):
        """5 000 найдено при десяти страницах — тысяча к просмотру."""
        assert возьмём(5000, 10) == 1000
        assert процент(1, 1, просмотрено=500, к_просмотру=возьмём(5000, 10)) == 50

    def test_найдено_меньше_глубины(self):
        assert возьмём(175, 10) == 175

    def test_ничего_не_найдено(self):
        assert возьмём(0, 10) == 0 and возьмём(None, 10) == 0

    def test_страниц_столько_сколько_будет_прочитано(self):
        """«Страница 1 из 10» при 175 вакансиях обещала бы восемь лишних."""
        assert страниц_ожидается(175, 10) == 2
        assert страниц_ожидается(5000, 10) == 10
        assert страниц_ожидается(100, 10) == 1
        assert страниц_ожидается(0, 10) == 0


class TestОсталось:

    def test_оценки_нет_пока_мало_сделано(self):
        assert осталось_секунд(10, 2) is None
        assert осталось_секунд(0, 50) is None

    def test_половина_пути_столько_же_впереди(self):
        assert осталось_секунд(300, 50) == 300

    def test_четверть_пути(self):
        assert осталось_секунд(100, 25) == 300


class TestСостояниеЭкрана:
    """Событие сбора превращается в то, что показывает экран."""

    @staticmethod
    def _состояние(запросы):
        from datetime import datetime, timedelta

        return {
            "progress": 0,
            "started_at": (datetime.now() - timedelta(minutes=5)).isoformat(),
            "keywords_total": len(запросы),
            "queries": [
                {"keyword": з, "status": "waiting", "found": None, "new": None, "updated": None}
                for з in запросы
            ],
            "recent": [],
        }

    @staticmethod
    def _событие(stage, **поля):
        from src.collector import ProgressEvent

        return ProgressEvent(stage=stage, **поля)

    def test_сбор_со_снимка_экрана(self):
        """
        Пять запросов; первый принёс 702, идёт второй на 175. Прежде
        здесь было 99 %: 712 собранных делились на 175 найденных.
        """
        from src.collection_run import учесть_ход as _учесть_ход

        запросы = ["3dsmax", "рендер", "Арт-директор", "артдиректор", "визуализатор"]
        с = self._состояние(запросы)

        _учесть_ход(с, self._событие("keyword_started", keyword="3dsmax", keyword_index=1, keywords_total=5), 10)
        _учесть_ход(с, self._событие("keyword_saved", keyword="3dsmax", collected=702, found=702,
                                     keyword_index=1, keywords_total=5, new=633, updated=69), 10)
        assert с["progress"] == 20

        _учесть_ход(с, self._событие("keyword_started", keyword="рендер", collected=702,
                                     keyword_index=2, keywords_total=5), 10)
        _учесть_ход(с, self._событие("vacancy_processed", keyword="рендер", collected=712, found=175,
                                     keyword_index=2, keywords_total=5, keyword_done=10, keyword_total=175,
                                     vacancy={"name": "3D-визуализатор", "employer": "Студия", "area": "Москва"}), 10)

        assert 20 <= с["progress"] < 40
        assert с["pages_expected"] == 2
        assert [q["status"] for q in с["queries"]] == ["done", "running", "waiting", "waiting", "waiting"]
        assert с["queries"][0]["new"] == 633
        assert с["recent"][0]["name"] == "3D-визуализатор"
        assert с["eta_seconds"] > 0

    def test_полоса_не_ходит_назад(self):
        """При резке на срезы доля внутри запроса считается по срезу."""
        from src.collection_run import учесть_ход as _учесть_ход

        с = self._состояние(["Python"])
        _учесть_ход(с, self._событие("page_fetched", keyword="Python", found=2000, keyword_index=1,
                                     keywords_total=1, keyword_done=800, keyword_total=1000), 10)
        было = с["progress"]
        _учесть_ход(с, self._событие("page_fetched", keyword="Python", found=300, keyword_index=1,
                                     keywords_total=1, keyword_done=10, keyword_total=300), 10)
        assert с["progress"] == было == 80

    def test_лента_держит_последние_и_не_повторяет(self):
        from src.collection_run import ЛЕНТА_ВАКАНСИЙ, учесть_ход as _учесть_ход

        с = self._состояние(["Python"])
        for n in list(range(10)) + [9]:
            _учесть_ход(с, self._событие("vacancy_processed", keyword="Python", keyword_index=1, keywords_total=1,
                                         vacancy={"name": f"Вакансия {n}", "employer": "", "area": ""}), 10)
        assert len(с["recent"]) == ЛЕНТА_ВАКАНСИЙ
        assert [в["name"] for в in с["recent"][:2]] == ["Вакансия 9", "Вакансия 8"]


class TestСобытияСборщика:

    def test_каждое_событие_несёт_номер_запроса(self, база, tmp_path):
        """Обработчик не должен помнить, какой запрос шёл в прошлом событии."""
        from src.collector import VacancyCollector

        class ПоЗапросу(ЖурналКлиента):
            """У каждого запроса свои десять вакансий: иначе второй — одни дубликаты."""

            def search_vacancies(self, keyword, page=0, per_page=100, **_):
                items = [вакансия(f"{keyword}-{n}") for n in range(10)] if page == 0 else []
                return {"items": items, "found": 10, "pages": 1}

        события = []
        VacancyCollector(
            client=ПоЗапросу([]), output_dir=tmp_path / "raw", max_pages=1, days_back=30,
            on_progress=события.append,
        ).collect_all(keywords=["первый", "второй"], save_raw=False)

        в_запросе = [с for с in события if с.stage in ("page_fetched", "vacancy_processed", "keyword_saved")]
        assert в_запросе and all(с.keywords_total == 2 and с.keyword_index in (1, 2) for с in в_запросе)

        обработанные = [с for с in события if с.stage == "vacancy_processed"]
        assert обработанные[-1].keyword_total == 10
        assert 0 < обработанные[-1].keyword_done <= 10
        assert обработанные[-1].vacancy["employer"] == "Компания"

        записанные = [с for с in события if с.stage == "keyword_saved"]
        assert [с.keyword_index for с in записанные] == [1, 2]
        assert записанные[0].new == 10
