"""
Резка запроса на срезы по регионам (S4‑2b2, S4‑2b3).

Источник отдаёт по запросу не больше 2000 вакансий: по «Рекрутеру» он
знает 10 294 и показывает первую пятую часть. Срезы — единственный
способ достать остальное, и проверяется здесь именно это свойство:
суммарно по частям берётся больше, чем отдаёт запрос целиком.

Отдельно проверяется, что резка не включается сама по себе: она стоит
десятков запросов к источнику, и запрос, помещающийся в выдачу, должен
читаться как раньше.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector import VacancyCollector  # noqa: E402
from src.coverage import доступная_глубина, упёрся  # noqa: E402

ДЕРЕВО = [
    {
        "id": "113",
        "name": "Россия",
        "areas": [
            {"id": "1", "name": "Москва", "areas": []},
            {"id": "2", "name": "Санкт-Петербург", "areas": []},
        ],
    },
]


class TestПравилоУпёрся:

    def test_найдено_больше_доступного(self):
        assert упёрся({"found": 10294, "pages": 20}, max_pages=10) is True

    def test_найдено_помещается(self):
        assert упёрся({"found": 300, "pages": 3}, max_pages=10) is False

    def test_без_найдено_не_режем(self):
        # Без числа судить не о чем, а лишняя резка стоит десятков
        # запросов к источнику.
        assert упёрся({"pages": 20}, max_pages=10) is False

    def test_ровно_по_границе(self):
        assert упёрся({"found": 1000, "pages": 10}, max_pages=10) is False
        assert упёрся({"found": 1001, "pages": 20}, max_pages=10) is True

    def test_глубина_ограничена_источником(self):
        # Наш предел страниц велик, но источник всё равно не отдаст
        # больше двух тысяч.
        assert доступная_глубина({"pages": 20}, max_pages=100) == 2000

    def test_глубина_ограничена_нашим_пределом(self):
        assert доступная_глубина({"pages": 20}, max_pages=5) == 500


def вакансии(префикс: str, сколько: int):
    """Страница выдачи: ровно то, что читает сборщик."""
    return [
        {
            "id": f"{префикс}{n}",
            "name": "Рекрутер",
            # От дня прогона, а не зашитая: зашитая дата через месяц
            # вышла за окно сбора и уронила тесты без правок в коде.
            "published_at": f"{datetime.now() - timedelta(days=3):%Y-%m-%dT10:00:00}+0300",
            "area": {"name": префикс},
            "employer": {"name": "Компания"},
        }
        for n in range(сколько)
    ]


class ИсточникСПределом:
    """
    Подменённый источник с пределом выдачи.

    Запрос без региона знает 10 000 вакансий, но отдаёт только первую
    сотню — как настоящий hh.ru, обрывающий пагинацию. Страна тоже
    переполнена и режется дальше на регионы; у региона выдача целиком
    помещается, и вакансии в разных регионах разные.
    """

    ПЕРЕПОЛНЕНЫ = {None, "113"}

    def __init__(self):
        self.delay = 0
        self.запросы = []

    def search_vacancies(self, keyword, page=0, per_page=100,
                         order_by=None, date_from=None, area=None, date_to=None):
        self.запросы.append((keyword, page, area))
        if page > 0:
            return {"items": [], "found": 10000, "pages": 1}
        метка = "общий" if area is None else f"регион{area}_"
        if area in self.ПЕРЕПОЛНЕНЫ:
            return {"items": вакансии(метка, 100), "found": 10000, "pages": 1}
        return {"items": вакансии(метка, 100), "found": 100, "pages": 1}

    def get_vacancy_details(self, vacancy_id):
        return None

    def get_areas(self):
        return ДЕРЕВО


@pytest.fixture
def сборщик(tmp_path, monkeypatch):
    from src import regions

    monkeypatch.setattr(regions, "ПУТЬ_СПРАВОЧНИКА", tmp_path / "areas.json")
    источник = ИсточникСПределом()
    собиратель = VacancyCollector(
        client=источник,
        output_dir=tmp_path,
        max_pages=1,
        detailed_pages=0,
        резать_упёршиеся=True,
    )
    return собиратель, источник


class TestОхватОтдельноОтГлубины:
    """
    Внутри среза карточки не запрашиваются.

    Это и есть цена резки: чтение выдачи стоит минуты, карточка — запрос
    на каждую новую вакансию. По замеру один глубокий запрос обходится в
    две минуты без карточек и почти четыре часа с ними, и именно из-за
    этой разницы резка полгода лежала выключенной. Глубину догоняет
    отдельный проход по бюджету, для которого неважно, каким сбором
    вакансия попала в базу.
    """

    def test_срезы_не_запрашивают_карточки(self, сборщик, monkeypatch):
        собиратель, источник = сборщик
        карточек = []
        monkeypatch.setattr(
            источник, "get_vacancy_details",
            lambda vid: карточек.append(vid) or None,
        )
        собиратель._collect_by_keyword("рекрутер", delay_between_pages=0)
        assert карточек == [], f"внутри срезов запрошено карточек: {len(карточек)}"

    def test_обычный_запрос_карточки_берёт(self, tmp_path, monkeypatch):
        """Признак касается только срезов: обычный сбор глубину не теряет."""
        from src import regions
        from src.collector import VacancyCollector

        monkeypatch.setattr(regions, "ПУТЬ_СПРАВОЧНИКА", tmp_path / "areas.json")

        class БезПредела(ИсточникСПределом):
            def search_vacancies(self, keyword, page=0, per_page=100, **kwargs):
                return {"items": вакансии("обычный", 3), "found": 3, "pages": 1}

        источник = БезПредела()
        карточек = []
        источник.get_vacancy_details = lambda vid: карточек.append(vid) or None
        собиратель = VacancyCollector(
            client=источник, output_dir=tmp_path, max_pages=1,
            detailed_pages=0, резать_упёршиеся=True,
        )
        собиратель._collect_by_keyword("дизайнер", delay_between_pages=0)
        assert len(карточек) == 3


    def test_отложенные_карточки_посчитаны_и_попадут_в_догон(self, сборщик):
        """
        Отложенная карточка — перенос, а не потеря.

        Вакансия из среза сохраняется с пометкой «деталей нет», и по этой
        пометке её находит проход дозапроса. Счётчик нужен, чтобы после
        глубокого сбора было видно, сколько работы ушло в догон, — иначе
        охват вырос бы молча за счёт глубины.
        """
        собиратель, _ = сборщик
        собранное = собиратель._collect_by_keyword("рекрутер", delay_between_pages=0)

        assert собиратель._stats["details_deferred"] > 0
        без_деталей = [в for в in собранное if not в.get("_has_details")]
        assert len(без_деталей) == собиратель._stats["details_deferred"]


class TestОбходСрезами:

    def test_срезы_дают_больше_чем_целый_запрос(self, сборщик):
        собиратель, источник = сборщик

        собрано = собиратель._collect_by_keyword("Рекрутер", delay_between_pages=0)

        # Без резки был бы предел одного запроса — сто вакансий.
        assert len(собрано) > 100
        # Ушли именно в срезы: запрос повторён с регионами.
        регионы = {area for _, _, area in источник.запросы if area}
        assert регионы == {"113", "1", "2"}

    def test_вакансии_срезов_не_задваиваются(self, сборщик):
        собиратель, _ = сборщик

        собрано = собиратель._collect_by_keyword("Рекрутер", delay_between_pages=0)

        ид = [v["id"] for v in собрано]
        assert len(ид) == len(set(ид))

    def test_найдено_остаётся_числом_широкого_среза(self, сборщик):
        собиратель, _ = сборщик

        собиратель._collect_by_keyword("Рекрутер", delay_between_pages=0)

        # Найдено — это сколько знает источник по запросу, а не сумма по
        # регионам: иначе число зависело бы от того, как мы порезали.
        assert собиратель._stats["by_keyword"]["Рекрутер"]["found"] == 10000

    def test_взято_суммируется_по_срезам(self, сборщик):
        собиратель, _ = сборщик

        собрано = собиратель._collect_by_keyword("Рекрутер", delay_between_pages=0)

        assert собиратель._stats["by_keyword"]["Рекрутер"]["взято"] >= len(собрано)

    def test_бюджет_срезов_останавливает_обход(self, сборщик):
        собиратель, источник = сборщик
        собиратель._срезов_осталось = 1

        собиратель._collect_by_keyword("Рекрутер", delay_between_pages=0)

        # Один срез пройден, дальше обход прекращён: непройденное
        # остаётся в недоборе, а не тратит тысячи запросов.
        регионы = [area for _, _, area in источник.запросы if area]
        assert len(set(регионы)) == 1


class TestБезРезки:

    def test_выключенная_резка_не_трогает_регионы(self, tmp_path):
        источник = ИсточникСПределом()
        собиратель = VacancyCollector(
            client=источник,
            output_dir=tmp_path,
            max_pages=1,
            detailed_pages=0,
            резать_упёршиеся=False,
        )

        собрано = собиратель._collect_by_keyword("Рекрутер", delay_between_pages=0)

        assert len(собрано) == 100
        assert all(area is None for _, _, area in источник.запросы)


class ГородСПределом:
    """
    Источник, где переполнен город — делить по регионам его уже некуда.

    Так выглядит настоящая Москва: 2 043 вакансии «Рекрутер» при пределе
    выдачи 2 000, а вложенных регионов у неё нет.
    """

    def __init__(self):
        self.delay = 0
        self.запросы = []

    def search_vacancies(self, keyword, page=0, per_page=100,
                         order_by=None, date_from=None, area=None, date_to=None):
        self.запросы.append({"page": page, "area": area,
                             "from": date_from, "to": date_to})
        if page > 0:
            return {"items": [], "found": 10000, "pages": 1}
        # Переполнен, пока окно не сузили: у половины окна выдача
        # помещается целиком.
        if date_to is None:
            return {"items": вакансии("общий", 100), "found": 10000, "pages": 1}
        метка = f"окно{date_from}_{date_to}_"
        return {"items": вакансии(метка, 100), "found": 100, "pages": 1}

    def get_vacancy_details(self, vacancy_id):
        return None

    def get_areas(self):
        # Дерева нет: резать по регионам не по чему.
        return []


class TestРезкаПоДатам:

    def сборщик(self, tmp_path, monkeypatch):
        from src import regions

        monkeypatch.setattr(regions, "ПУТЬ_СПРАВОЧНИКА", tmp_path / "areas.json")
        источник = ГородСПределом()
        собиратель = VacancyCollector(
            client=источник,
            output_dir=tmp_path,
            max_pages=1,
            detailed_pages=1,
            резать_упёршиеся=True,
        )
        return собиратель, источник

    def test_окно_режется_пополам(self, tmp_path, monkeypatch):
        собиратель, источник = self.сборщик(tmp_path, monkeypatch)

        собрано = собиратель._collect_by_keyword("Рекрутер", delay_between_pages=0)

        окна = [(з["from"], з["to"]) for з in источник.запросы if з["to"]]
        assert len(окна) >= 2
        assert len(собрано) > 100

    def test_половины_не_пересекаются(self, tmp_path, monkeypatch):
        собиратель, _ = self.сборщик(tmp_path, monkeypatch)

        половины = собиратель._половины_окна(("2026-08-01", "2026-09-01"))

        assert len(половины) == 2
        # Верхняя граница первой половины — нижняя второй: вакансия,
        # опубликованная на рубеже, не попадёт в обе выдачи дважды.
        assert половины[0][1] == половины[1][0]
        assert половины[0][0] == "2026-08-01"
        assert половины[1][1] == "2026-09-01"

    def test_короткое_окно_не_делится(self, tmp_path, monkeypatch):
        собиратель, _ = self.сборщик(tmp_path, monkeypatch)

        # У источника разрешение границ — сутки: делить дальше значит
        # уйти в бесконечность, получая тот же ответ.
        assert собиратель._половины_окна(("2026-09-01", "2026-09-02")) == []

    def test_вакансии_окон_не_задваиваются(self, tmp_path, monkeypatch):
        собиратель, _ = self.сборщик(tmp_path, monkeypatch)

        собрано = собиратель._collect_by_keyword("Рекрутер", delay_between_pages=0)

        ид = [v["id"] for v in собрано]
        assert len(ид) == len(set(ид))


class РегионыРазногоРазмера:
    """Источник, где регионы сильно различаются по числу вакансий."""

    ДЕРЕВО = [
        {
            "id": "113",
            "name": "Россия",
            "areas": [
                {"id": "мелкий", "name": "Марий Эл", "areas": []},
                {"id": "крупный", "name": "Москва", "areas": []},
                {"id": "средний", "name": "Казань", "areas": []},
            ],
        },
    ]

    # Числа умещаются в выдачу: сам регион уже не режется, и в порядке
    # обхода видно только правило «сначала крупные».
    РАЗМЕРЫ = {"мелкий": 12, "крупный": 95, "средний": 40}

    def __init__(self):
        self.delay = 0
        self.обойдено = []

    def search_vacancies(self, keyword, page=0, per_page=100,
                         order_by=None, date_from=None, area=None, date_to=None):
        if per_page > 1 and area in self.РАЗМЕРЫ:
            self.обойдено.append(area)
        if area is None or area == "113":
            return {"items": вакансии("общий", 100), "found": 10000, "pages": 1}
        найдено = self.РАЗМЕРЫ.get(area, 0)
        сколько = min(найдено, 100) if per_page > 1 else 0
        return {"items": вакансии(f"{area}_", сколько), "found": найдено, "pages": 1}

    def get_vacancy_details(self, vacancy_id):
        return None

    def get_areas(self):
        return self.ДЕРЕВО


class TestПорядокСрезов:

    def сборщик(self, tmp_path, monkeypatch, бюджет):
        from src import regions

        monkeypatch.setattr(regions, "ПУТЬ_СПРАВОЧНИКА", tmp_path / "areas.json")
        источник = РегионыРазногоРазмера()
        собиратель = VacancyCollector(
            client=источник,
            output_dir=tmp_path,
            max_pages=1,
            detailed_pages=1,
            резать_упёршиеся=True,
        )
        собиратель._срезов_осталось = бюджет
        return собиратель, источник

    def test_крупный_регион_идёт_первым(self, tmp_path, monkeypatch):
        собиратель, источник = self.сборщик(tmp_path, monkeypatch, бюджет=10)

        собиратель._collect_by_keyword("Рекрутер", delay_between_pages=0)

        assert источник.обойдено[0] == "крупный"
        assert источник.обойдено == ["крупный", "средний", "мелкий"]

    def test_взвешивание_не_съедает_весь_бюджет(self, tmp_path, monkeypatch):
        """
        Лёгкие запросы разведки ограничены, как и сами обходы.

        Живой замер 11.09.2026 поймал обратное: 408 секунд работы и две
        собранные вакансии. Бюджет считал только обходы, а взвешивание
        шло на каждом уровне рекурсии — страны, регионы страны, города
        региона, — и обращения уходили в разведку целиком.
        """
        собиратель, источник = self.сборщик(tmp_path, monkeypatch, бюджет=1)
        собиратель._collect_by_keyword("Рекрутер", delay_between_pages=0)

        # Пять лёгких запросов на срез бюджета — и ни одним больше,
        # сколько бы уровней вглубь ни ушла резка.
        assert собиратель._взвешиваний_сделано <= 1 * 5

    def test_при_нехватке_бюджета_резка_не_начинается(self, tmp_path, monkeypatch):
        """
        Не хватает на все части — читаем запрос напрямую.

        Резка заменяет прямое чтение, а не дополняет его: обойдя срезы,
        вглубь мы уже не идём. Значит обойти три части из девяноста —
        это не «собрать меньше, чем хотели», а собрать меньше, чем без
        резки вообще. Живой замер 11.09.2026 поймал это на «Графическом
        дизайнере»: при бюджете в шесть срезов вышло 55 вакансий против
        тысячи прямым чтением.

        Раньше тест ожидал обхода одного крупнейшего среза. Правило
        изменено: охват со срезами не должен быть меньше, чем без них.
        """
        собиратель, источник = self.сборщик(tmp_path, monkeypatch, бюджет=2)

        собранное = собиратель._collect_by_keyword("Рекрутер", delay_between_pages=0)

        assert источник.обойдено == [], "срезы не обходились"
        assert собранное, "запрос прочитан напрямую, а не потерян"


class TestСправочникПослеПростоя:
    """
    Справочник на диске старше срока годности — и сеть не отвечает.

    После месяца простоя сбор первым запросом шёл за свежим справочником,
    и отказ этого запроса ронял запуск. Старый файл при этом лежал на
    диске: регионы меняются раз в год.
    """

    def _старый_файл(self, tmp_path, monkeypatch):
        import json
        import os
        import time

        from src import regions

        путь = tmp_path / "areas.json"
        путь.write_text(json.dumps([{"id": "113", "name": "Россия", "areas": []}]), encoding="utf-8")
        давно = time.time() - (regions.СРОК_ГОДНОСТИ_ДНЕЙ + 5) * 86400
        os.utime(путь, (давно, давно))
        monkeypatch.setattr(regions, "ПУТЬ_СПРАВОЧНИКА", путь)
        return regions

    def test_отказ_сети_оставляет_старый_справочник(self, tmp_path, monkeypatch):
        regions = self._старый_файл(tmp_path, monkeypatch)
        клиент = MagicMock()
        клиент.get_areas.side_effect = ConnectionError("сеть недоступна")

        assert regions.загрузить(клиент)[0]["id"] == "113"

    def test_пустой_ответ_оставляет_старый_справочник(self, tmp_path, monkeypatch):
        regions = self._старый_файл(tmp_path, monkeypatch)
        клиент = MagicMock()
        клиент.get_areas.return_value = None

        assert regions.загрузить(клиент)[0]["id"] == "113"

    def test_удачный_ответ_заменяет_старый(self, tmp_path, monkeypatch):
        regions = self._старый_файл(tmp_path, monkeypatch)
        клиент = MagicMock()
        клиент.get_areas.return_value = [{"id": "40", "name": "Казахстан", "areas": []}]

        assert regions.загрузить(клиент)[0]["id"] == "40"
        assert regions._свежий(regions.ПУТЬ_СПРАВОЧНИКА)
