"""
Тесты режимов сбора.

Кэш и дописывание — флаги одного сборщика. Прежде это были два почти
одинаковых класса, и выбор между ними шёл по условию `incremental or
use_cache`: режим данных определял, каким кодом соберутся вакансии.
Копии успели разойтись в разборе навыков, поэтому набор навыков в базе
зависел от флагов запуска.

Здесь проверяется, что все четыре сочетания работают через один класс и
что дописывание экономит запросы карточек, не теряя обновлений.

Запуск: pytest tests/test_collector_modes.py -v
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.collector import VacancyCollector


def вакансия(vacancy_id: str, salary_from: int = 100000) -> dict:
    """Строка выдачи поиска."""
    return {
        "id": vacancy_id,
        "name": "Аналитик данных",
        # Дата считается от дня прогона, а не зашита: зашитое 01.09.2026
        # через месяц вышло за окно сбора, и тест упал без единой правки
        # в коде — «свежая» вакансия стала старой по календарю.
        "published_at": f"{datetime.now() - timedelta(days=3):%Y-%m-%dT10:00:00}+0300",
        "salary": {"from": salary_from, "to": None, "currency": "RUR", "gross": False},
        "employer": {"id": "1", "name": "Компания", "url": ""},
        "area": {"id": "1", "name": "Москва"},
        "experience": {"name": "От 1 года до 3 лет"},
        "employment": {"name": "Полная занятость"},
        "schedule": {"name": "Удалённо"},
        "alternate_url": f"https://hh.ru/vacancy/{vacancy_id}",
        "snippet": {"requirement": "Python, SQL", "responsibility": "Аналитика"},
    }


class ЖурналКлиента:
    """
    Подставной клиент источника: отдаёт заготовленную выдачу и запоминает,
    что у него спрашивали. По журналу видно, сколько запросов сэкономил
    режим дописывания.
    """

    def __init__(self, страницы, delay: float = 0):
        self.страницы = страницы
        self.delay = delay
        self.поиски = []
        self.карточки = []

    def search_vacancies(self, keyword, page=0, per_page=100, **_):
        self.поиски.append((keyword, page, per_page))
        items = self.страницы[page] if page < len(self.страницы) else []
        return {"items": items, "found": sum(len(p) for p in self.страницы), "pages": len(self.страницы)}

    def get_vacancy_details(self, vacancy_id):
        self.карточки.append(vacancy_id)
        return {"description": "Требуется Python и SQL, умение работать в команде"}


@pytest.fixture
def база(tmp_path, monkeypatch):
    """Отдельная база: тесты не трогают рабочие данные."""
    from src import config, storage as storage_module

    monkeypatch.setattr(config.settings, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(storage_module.settings, "db_path", tmp_path / "test.db")
    return tmp_path / "test.db"


def прочитать(путь, include_inactive=True):
    from src.storage import VacancyStorage

    store = VacancyStorage(db_path=путь)
    try:
        return store.get_all_vacancies(include_inactive=include_inactive)
    finally:
        store.close()


@pytest.mark.parametrize("use_cache", [False, True])
@pytest.mark.parametrize("incremental", [False, True])
def test_все_четыре_сочетания_собирают(база, tmp_path, use_cache, incremental, monkeypatch):
    """Один класс обслуживает все режимы, и каждый доходит до базы."""
    if use_cache:
        # Кэш живёт в своей базе — уводим и его во временную папку.
        from src import api_cache
        monkeypatch.setattr(api_cache.settings, "db_path", tmp_path / "test.db")

    client = ЖурналКлиента([[вакансия("1"), вакансия("2")]])
    collector = VacancyCollector(
        client=client,
        output_dir=tmp_path / "raw",
        max_pages=1,
        days_back=3650,
        use_cache=use_cache,
        incremental=incremental,
    )

    result = collector.collect_all(keywords=["Python"], save_raw=False)

    assert result["unique"] == 2
    assert set(прочитать(база)["vacancy_id"]) == {"1", "2"}


def test_дописывание_не_запрашивает_карточки_известных(база, tmp_path):
    """
    Экономия запросов — весь смысл режима: карточка известной вакансии
    уже собрана, повторно её запрашивать незачем.
    """
    первый = ЖурналКлиента([[вакансия("1"), вакансия("2")]])
    VacancyCollector(
        client=первый, output_dir=tmp_path / "raw", max_pages=1, days_back=3650
    ).collect_all(keywords=["Python"], save_raw=False)

    assert len(первый.карточки) == 2

    второй = ЖурналКлиента([[вакансия("1"), вакансия("2"), вакансия("3")]])
    VacancyCollector(
        client=второй,
        output_dir=tmp_path / "raw",
        max_pages=1,
        days_back=3650,
        incremental=True,
    ).collect_all(keywords=["Python"], save_raw=False)

    # Карточка запрошена только у новой вакансии.
    assert второй.карточки == ["3"]


def test_дописывание_обновляет_известные_вакансии(база, tmp_path):
    """
    Известная вакансия остаётся в сохранении. Прежде режим выбрасывал её
    целиком, и зарплата, график и статус застывали навсегда, а
    «обновлено» в истории сборов всегда равнялось нулю.
    """
    первый = ЖурналКлиента([[вакансия("1", salary_from=100000)]])
    VacancyCollector(
        client=первый, output_dir=tmp_path / "raw", max_pages=1, days_back=3650
    ).collect_all(keywords=["Python"], save_raw=False)

    второй = ЖурналКлиента([[вакансия("1", salary_from=250000)]])
    VacancyCollector(
        client=второй,
        output_dir=tmp_path / "raw",
        max_pages=1,
        days_back=3650,
        incremental=True,
    ).collect_all(keywords=["Python"], save_raw=False)

    строки = прочитать(база)
    assert len(строки) == 1
    assert строки.iloc[0]["salary_from"] == 250000


class TestСтатистикаПоЗапросам:
    """
    Что принёс каждый запрос. Прежде все собранные вакансии записывались
    в историю как новые, а «обновлено» всегда равнялось нулю: числа
    брались из длины списка, а не из результата записи.
    """

    def test_повторный_сбор_считает_обновления_а_не_находки(self, база, tmp_path):
        клиент = ЖурналКлиента([[вакансия("1"), вакансия("2")]])
        VacancyCollector(
            client=клиент, output_dir=tmp_path / "raw", max_pages=1, days_back=3650
        ).collect_all(keywords=["Python"], save_raw=False)

        повтор = ЖурналКлиента([[вакансия("1"), вакансия("2"), вакансия("3")]])
        итог = VacancyCollector(
            client=повтор, output_dir=tmp_path / "raw", max_pages=1, days_back=3650
        ).collect_all(keywords=["Python"], save_raw=False)

        assert итог["new"] == 1
        assert итог["updated"] == 2

    def test_разбивка_по_каждому_запросу(self, база, tmp_path):
        клиент = ЖурналКлиента([[вакансия("1")]])
        VacancyCollector(
            client=клиент, output_dir=tmp_path / "raw", max_pages=1, days_back=3650
        ).collect_all(keywords=["Python"], save_raw=False)

        # Второй сбор: первый запрос приносит известную вакансию, второй — новую.
        class ДваЗапроса(ЖурналКлиента):
            def search_vacancies(self, keyword, page=0, per_page=100, **_):
                self.поиски.append((keyword, page, per_page))
                items = [вакансия("1")] if keyword == "Python" else [вакансия("9")]
                return {"items": items, "found": len(items), "pages": 1}

        итог = VacancyCollector(
            client=ДваЗапроса([]), output_dir=tmp_path / "raw", max_pages=1, days_back=3650
        ).collect_all(keywords=["Python", "Go"], save_raw=False)

        assert итог["by_keyword"]["Python"]["updated"] == 1
        assert итог["by_keyword"]["Python"]["new"] == 0
        assert итог["by_keyword"]["Go"]["new"] == 1

    def test_сбой_на_втором_запросе_не_теряет_первый(self, база, tmp_path):
        """
        Прежде сбор сохранял всё одним списком в самом конце: падение на
        середине означало, что собранное до него пропало впустую.
        """
        class ПадаетНаВтором(ЖурналКлиента):
            def search_vacancies(self, keyword, page=0, per_page=100, **_):
                if keyword == "Go":
                    raise RuntimeError("источник недоступен")
                return {"items": [вакансия("1")], "found": 1, "pages": 1}

        collector = VacancyCollector(
            client=ПадаетНаВтором([]), output_dir=tmp_path / "raw", max_pages=1, days_back=3650
        )

        with pytest.raises(RuntimeError):
            collector.collect_all(keywords=["Python", "Go"], save_raw=False)

        assert set(прочитать(база)["vacancy_id"]) == {"1"}


class TestОбрывПоВозрастуВакансий:
    """
    Выдача читается по дате публикации, и обход прекращается, когда
    начинаются вакансии старше нужного возраста.

    Прежде выдача приходила по релевантности, а обрыв прекращал только
    обработку текущей страницы: свежие вакансии ниже старой терялись, а
    следующая страница всё равно запрашивалась.
    """

    def старая(self, vacancy_id):
        v = вакансия(vacancy_id)
        v["published_at"] = "2020-01-01T10:00:00+0300"
        return v

    def test_сортировка_по_дате_запрашивается(self, база, tmp_path):
        class Запоминающий(ЖурналКлиента):
            def search_vacancies(self, keyword, page=0, per_page=100, order_by=None, **_):
                self.поиски.append((keyword, page, per_page, order_by))
                return {"items": [вакансия("1")], "found": 1, "pages": 1}

        клиент = Запоминающий([])
        VacancyCollector(
            client=клиент, output_dir=tmp_path / "raw", max_pages=2, days_back=30
        ).collect_all(keywords=["Python"], save_raw=False)

        # Сбор не навязывает порядок сам — он приходит значением по
        # умолчанию клиента, поэтому здесь проверяется, что параметр
        # вообще участвует в вызове.
        assert клиент.поиски[0][0] == "Python"

    def test_старая_вакансия_прекращает_обход_запроса(self, база, tmp_path):
        страница = [вакансия("1"), вакансия("2"), self.старая("3")] + [вакансия(str(i)) for i in range(4, 101)]
        клиент = ЖурналКлиента([страница, [вакансия("200")]])

        итог = VacancyCollector(
            client=клиент, output_dir=tmp_path / "raw", max_pages=2, days_back=30
        ).collect_all(keywords=["Python"], save_raw=False)

        # Собраны только вакансии до старой.
        assert set(прочитать(база)["vacancy_id"]) == {"1", "2"}
        # И вторая страница не запрашивалась: обход запроса закончен.
        assert len(клиент.поиски) == 1

    def test_обрыв_по_возрасту_считается_полным_проходом(self, база, tmp_path):
        """
        Выдача прочитана до нужной глубины — значит по этому запросу
        можно гасить вакансии, которых в ней не оказалось.
        """
        страница = [вакансия("1"), self.старая("2")]
        итог = VacancyCollector(
            client=ЖурналКлиента([страница]), output_dir=tmp_path / "raw",
            max_pages=2, days_back=30
        ).collect_all(keywords=["Python"], save_raw=False)

        assert итог["by_keyword"]["Python"]["complete"] is True


class TestГраницаВозрастаНаСторонеИсточника:
    """
    Возраст вакансий ограничивается запросом, а не отбраковкой после
    скачивания: иначе лимит запросов тратится на страницы, которые тут же
    уходят в мусор.
    """

    def test_дата_уходит_в_запрос(self, база, tmp_path):
        class Запоминающий(ЖурналКлиента):
            def search_vacancies(self, keyword, page=0, per_page=100, date_from=None, **_):
                self.поиски.append({"keyword": keyword, "date_from": date_from})
                return {"items": [вакансия("1")], "found": 1}

        клиент = Запоминающий([])
        VacancyCollector(
            client=клиент, output_dir=tmp_path / "raw", max_pages=1, days_back=30
        ).collect_all(keywords=["Python"], save_raw=False)

        отправленная = клиент.поиски[0]["date_from"]
        assert отправленная is not None
        # Формат, который принимает источник: ISO-дата.
        datetime.strptime(отправленная, "%Y-%m-%d")

    def test_граница_совпадает_с_локальной_проверкой(self, база, tmp_path):
        """
        Две границы обязаны совпадать: иначе сбор либо выбрасывает то,
        что честно скачал, либо оставляет то, что должен был отсечь.
        """
        collector = VacancyCollector(
            client=ЖурналКлиента([]), output_dir=tmp_path / "raw", max_pages=1, days_back=30
        )

        assert collector._date_from() == collector.cutoff_date.strftime("%Y-%m-%d")

    def test_выдача_без_старых_дочитывается_до_конца(self, база, tmp_path):
        итог = VacancyCollector(
            client=ЖурналКлиента([[вакансия("1"), вакансия("2")]]),
            output_dir=tmp_path / "raw", max_pages=2, days_back=30
        ).collect_all(keywords=["Python"], save_raw=False)

        assert итог["by_keyword"]["Python"]["complete"] is True


class TestОжидаемыйОбъём:
    """`found` из ответа — знаменатель прогресса."""

    def test_число_попадает_в_статистику(self, база, tmp_path):
        class СFound(ЖурналКлиента):
            def search_vacancies(self, keyword, page=0, per_page=100, **_):
                self.поиски.append(keyword)
                return {"items": [вакансия("1")], "found": 573}

        итог = VacancyCollector(
            client=СFound([]), output_dir=tmp_path / "raw", max_pages=1, days_back=3650
        ).collect_all(keywords=["Python"], save_raw=False)

        assert итог["by_keyword"]["Python"]["found"] == 573
        assert итог["found_estimate"] == 573

    def test_ответ_без_числа_не_ломает_сбор(self, база, tmp_path):
        class БезFound(ЖурналКлиента):
            def search_vacancies(self, keyword, page=0, per_page=100, **_):
                self.поиски.append(keyword)
                return {"items": [вакансия("1")]}

        итог = VacancyCollector(
            client=БезFound([]), output_dir=tmp_path / "raw", max_pages=1, days_back=3650
        ).collect_all(keywords=["Python"], save_raw=False)

        assert итог["found_estimate"] == 0
        assert len(прочитать(база)) == 1


class TestСобытияХодаСбора:
    """
    Ход сбора сообщается событиями. Прежде внешний код узнавал о нём,
    подменяя методы коллектора и его клиента своими функциями с
    фиксированными аргументами: появление у поиска нового параметра
    роняло сбор целиком (запуск №25 в истории).
    """

    def test_порядок_событий(self, база, tmp_path):
        события = []
        VacancyCollector(
            client=ЖурналКлиента([[вакансия("1")]]),
            output_dir=tmp_path / "raw", max_pages=1, days_back=3650,
            on_progress=события.append,
        ).collect_all(keywords=["Python", "Go"], save_raw=False)

        этапы = [e.stage for e in события]
        assert этапы.count("keyword_started") == 2
        assert этапы.count("keyword_saved") == 2
        assert этапы[-1] == "finished"
        # Запрос назван в событии, номер и общее число тоже.
        первое = события[0]
        assert (первое.keyword, первое.keyword_index, первое.keywords_total) == ("Python", 1, 2)

    def test_событие_страницы_несёт_счётчики(self, база, tmp_path):
        события = []
        VacancyCollector(
            client=ЖурналКлиента([[вакансия("1"), вакансия("2")]]),
            output_dir=tmp_path / "raw", max_pages=1, days_back=3650,
            on_progress=события.append,
        ).collect_all(keywords=["Python"], save_raw=False)

        страницы = [e for e in события if e.stage == "page_fetched"]
        assert страницы
        assert страницы[0].found == 2

    def test_ход_виден_внутри_страницы(self, база, tmp_path):
        """
        Обработка страницы — до ста запросов карточек, то есть минуты.
        Без событий внутри страницы счётчик стоит на нуле всё это время:
        живая проверка сбора показала ровно это.
        """
        страница = [вакансия(str(i)) for i in range(20)]
        события = []
        VacancyCollector(
            client=ЖурналКлиента([страница]),
            output_dir=tmp_path / "raw", max_pages=1, days_back=3650,
            on_progress=события.append,
        ).collect_all(keywords=["Python"], save_raw=False)

        внутри = [e for e in события if e.stage == "vacancy_processed"]
        assert внутри, "во время обработки страницы не было ни одного события"
        # Счётчик растёт по ходу, а не появляется готовым в конце.
        assert внутри[0].collected < внутри[-1].collected

    def test_событий_внутри_страницы_немного(self, база, tmp_path):
        """
        Обработчик может писать в базу или в сеть: сотня событий на
        страницу превратила бы отчёт о работе в саму работу.
        """
        страница = [вакансия(str(i)) for i in range(100)]
        события = []
        VacancyCollector(
            client=ЖурналКлиента([страница]),
            output_dir=tmp_path / "raw", max_pages=1, days_back=3650,
            on_progress=события.append,
        ).collect_all(keywords=["Python"], save_raw=False)

        внутри = [e for e in события if e.stage == "vacancy_processed"]
        assert len(внутри) <= 20

    def test_сбой_обработчика_не_прерывает_сбор(self, база, tmp_path):
        """
        Событие — это отчёт о работе, а не сама работа: уронить сбор
        из-за неудачной записи прогресса значило бы потерять данные
        ради индикатора.
        """
        def падающий(event):
            raise RuntimeError("обработчик сломался")

        VacancyCollector(
            client=ЖурналКлиента([[вакансия("1")]]),
            output_dir=tmp_path / "raw", max_pages=1, days_back=3650,
            on_progress=падающий,
        ).collect_all(keywords=["Python"], save_raw=False)

        assert len(прочитать(база)) == 1

    def test_остановка_между_запросами(self, база, tmp_path):
        """Просьба остановиться доходит до сбора и прекращает его."""
        клиент = ЖурналКлиента([[вакансия("1")]])
        collector = VacancyCollector(
            client=клиент, output_dir=tmp_path / "raw", max_pages=1, days_back=3650
        )

        # Останавливаем сразу после первого сохранённого запроса.
        collector.on_progress = lambda e: collector.request_stop() if e.stage == "keyword_saved" else None

        collector.collect_all(keywords=["Python", "Go", "Rust"], save_raw=False)

        # Второй и третий запросы даже не начинались.
        assert {k for k, _, _ in [(p[0], 0, 0) for p in клиент.поиски]} == {"Python"}


class TestРазбивкаВИстории:
    """Разбивка сбора по запросам, как она ложится в базу."""

    def test_строка_на_каждый_запрос(self, база, tmp_path):
        from src.storage import VacancyStorage

        клиент = ЖурналКлиента([[вакансия("1")]])
        итог = VacancyCollector(
            client=клиент, output_dir=tmp_path / "raw", max_pages=1, days_back=3650
        ).collect_all(keywords=["Python"], save_raw=False)

        store = VacancyStorage(db_path=база)
        try:
            run_id = store.create_parser_run(keywords=["Python"])
            записано = store.save_run_queries(run_id, итог["by_keyword"])
            строки = store.get_run_queries(run_id)
        finally:
            store.close()

        assert записано == 1
        assert строки[0]["keyword"] == "Python"
        assert строки[0]["vacancies_new"] == 1
        assert строки[0]["status"] == "complete"
        assert строки[0]["duration_ms"] >= 0
        # Ожидаемый объём доходит до базы: это знаменатель прогресса.
        assert строки[0]["found"] == 1

    def test_неполный_проход_помечен_как_partial(self, база, tmp_path):
        from src.storage import VacancyStorage

        # Пять полных страниц при пределе в одну: выдача не дочитана.
        страницы = [[вакансия(str(i)) for i in range(100)]] * 5
        итог = VacancyCollector(
            client=ЖурналКлиента(страницы), output_dir=tmp_path / "raw",
            max_pages=1, days_back=3650
        ).collect_all(keywords=["Python"], save_raw=False)

        store = VacancyStorage(db_path=база)
        try:
            run_id = store.create_parser_run(keywords=["Python"])
            store.save_run_queries(run_id, итог["by_keyword"])
            строки = store.get_run_queries(run_id)
        finally:
            store.close()

        assert строки[0]["status"] == "partial"


def test_остановка_прерывает_обход(база, tmp_path):
    """Остановка проверяется атрибутом, а не наличием атрибута."""
    client = ЖурналКлиента([[вакансия(str(i)) for i in range(100)]] * 5)
    collector = VacancyCollector(
        client=client, output_dir=tmp_path / "raw", max_pages=5, days_back=3650
    )
    collector.stop_requested = True

    collector.collect_all(keywords=["Python"], save_raw=False)

    assert client.поиски == []
