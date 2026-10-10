"""
Справочник регионов источника (S4‑2b1).

Главное свойство: пустой справочник — это «не по чему резать», а не
«регионов нет». Перепутать их значит порезать запрос вслепую и молча
собрать пустоту.
"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import regions  # noqa: E402

ДЕРЕВО = [
    {
        "id": "113",
        "name": "Россия",
        "areas": [
            {"id": "1", "name": "Москва", "areas": []},
            {
                "id": "1624",
                "name": "Республика Татарстан",
                "areas": [
                    {"id": "88", "name": "Казань", "areas": []},
                ],
            },
        ],
    },
    {"id": "40", "name": "Казахстан", "areas": [{"id": "159", "name": "Астана", "areas": []}]},
]


@pytest.fixture
def свой_файл(tmp_path, monkeypatch):
    """Справочник в отдельном файле: тест не трогает рабочий."""
    путь = tmp_path / "areas.json"
    monkeypatch.setattr(regions, "ПУТЬ_СПРАВОЧНИКА", путь)
    return путь


class TestЧтениеСправочника:

    def test_свежий_файл_читается_без_сети(self, свой_файл):
        свой_файл.write_text(json.dumps(ДЕРЕВО, ensure_ascii=False), encoding="utf-8")
        клиент = MagicMock()

        дерево = regions.загрузить(клиент)

        assert len(дерево) == 2
        клиент.get_areas.assert_not_called()

    def test_устаревший_файл_перечитывается(self, свой_файл):
        свой_файл.write_text("[]", encoding="utf-8")
        старость = time.time() - (regions.СРОК_ГОДНОСТИ_ДНЕЙ + 1) * 86400
        import os

        os.utime(свой_файл, (старость, старость))

        клиент = MagicMock()
        клиент.get_areas.return_value = ДЕРЕВО

        дерево = regions.загрузить(клиент)

        assert regions.имя(дерево, "1") == "Москва"
        клиент.get_areas.assert_called_once()

    def test_ответ_источника_сохраняется(self, свой_файл):
        клиент = MagicMock()
        клиент.get_areas.return_value = ДЕРЕВО

        regions.загрузить(клиент)

        assert свой_файл.exists()
        assert json.loads(свой_файл.read_text(encoding="utf-8"))[0]["name"] == "Россия"

    def test_без_файла_и_без_клиента_пусто(self, свой_файл):
        # Пустой список означает «резать не по чему». Выдумать регионы
        # неоткуда, и молча продолжить как раньше — правильнее, чем
        # порезать запрос по несуществующим кодам.
        assert regions.загрузить(None) == []

    def test_битый_файл_не_роняет(self, свой_файл):
        свой_файл.write_text("{не json", encoding="utf-8")
        клиент = MagicMock()
        клиент.get_areas.return_value = ДЕРЕВО

        дерево = regions.загрузить(клиент)

        assert len(дерево) == 2


class TestОбходДерева:

    def test_корни_это_страны(self):
        assert regions.корни(ДЕРЕВО) == ["113", "40"]

    def test_дети_региона(self):
        assert regions.дети(ДЕРЕВО, "113") == ["1", "1624"]
        assert regions.дети(ДЕРЕВО, "1624") == ["88"]

    def test_лист_без_детей(self):
        # Резать дальше нечем: остаток по такому срезу честно уходит в
        # недобор, а не притворяется собранным.
        assert regions.дети(ДЕРЕВО, "1") == []

    def test_неизвестный_регион(self):
        assert regions.дети(ДЕРЕВО, "99999") == []
        assert regions.узел(ДЕРЕВО, "99999") is None

    def test_имя_для_сообщений(self):
        assert regions.имя(ДЕРЕВО, "88") == "Казань"
        assert regions.имя(ДЕРЕВО, "99999") == "99999"

    def test_пустое_дерево_не_роняет(self):
        assert regions.корни([]) == []
        assert regions.дети([], "1") == []
