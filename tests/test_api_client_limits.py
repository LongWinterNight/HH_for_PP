"""
Тесты поведения клиента при отказе источника по частоте запросов.

Отказ 429 прежде бросался как общий `HTTPError`, которого не было в
условии повтора: исключение уходило наружу, превращалось в `None`, и
страница молча терялась — в данных это выглядело как отсутствие вакансий.
Вдобавок задержка удваивалась навсегда, и весь оставшийся сбор шёл вдвое
медленнее из-за одного отказа.

Запуск: pytest tests/test_api_client_limits.py -v
"""

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.api_client import HHAPIClient, TooManyRequests, ПричинаОтказа


class Ответ:
    """Подставной ответ источника."""

    def __init__(self, status_code: int, headers: dict = None, payload: dict = None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload if payload is not None else {"items": [], "found": 0}
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def клиент(monkeypatch):
    """Клиент без сети и без пауз: время в тестах не тратится."""
    monkeypatch.setattr("time.sleep", lambda _: None)
    return HHAPIClient(email="test@example.com", delay=1.0, access_token="токен")


def подменить_ответы(клиент, ответы):
    """Сессия отдаёт заготовленные ответы по очереди и считает запросы."""
    журнал = []

    def get(url, params=None, timeout=None):
        журнал.append(params)
        return ответы[min(len(журнал) - 1, len(ответы) - 1)]

    клиент.session.get = get
    return журнал


def test_отказ_по_частоте_приводит_к_повтору(клиент):
    """Страница не теряется: после отказа запрос повторяется."""
    журнал = подменить_ответы(клиент, [
        Ответ(429),
        Ответ(200, payload={"items": [{"id": "1"}], "found": 1}),
    ])

    результат = клиент.search_vacancies("Python")

    assert результат["found"] == 1
    assert len(журнал) == 2


def test_отказы_считаются(клиент):
    """По счётчику видно, что выборка неполна не потому, что вакансий нет."""
    подменить_ответы(клиент, [Ответ(429), Ответ(200)])

    клиент.search_vacancies("Python")

    assert клиент.rate_limit_hits == 1


def test_пауза_берётся_из_заголовка(клиент, monkeypatch):
    """Сколько ждать, решает источник, а не наша экспонента."""
    паузы = []
    monkeypatch.setattr("src.api_client.time.sleep", lambda s: паузы.append(s))
    подменить_ответы(клиент, [Ответ(429, headers={"Retry-After": "7"}), Ответ(200)])

    клиент.search_vacancies("Python")

    assert 7 in паузы


def test_слишком_долгая_пауза_ограничена(клиент, monkeypatch):
    """Источник может попросить ждать час — сбор не должен зависать."""
    паузы = []
    monkeypatch.setattr("src.api_client.time.sleep", lambda s: паузы.append(s))
    подменить_ответы(клиент, [Ответ(429, headers={"Retry-After": "3600"}), Ответ(200)])

    клиент.search_vacancies("Python")

    assert max(паузы) <= HHAPIClient.MAX_RETRY_AFTER


def test_задержка_растёт_временно_и_имеет_потолок(клиент):
    подменить_ответы(клиент, [Ответ(429), Ответ(429), Ответ(200)])

    клиент.search_vacancies("Python")

    assert клиент.delay > клиент.base_delay
    assert клиент.delay <= клиент.base_delay * 8


def test_задержка_возвращается_после_успешной_серии(клиент):
    """Разовый отказ не должен замедлять весь оставшийся сбор."""
    подменить_ответы(клиент, [Ответ(429), Ответ(200)])
    клиент.search_vacancies("Python")
    assert клиент.delay > клиент.base_delay

    подменить_ответы(клиент, [Ответ(200)])
    for _ in range(HHAPIClient.SUCCESSES_TO_RESTORE):
        клиент.search_vacancies("Python")

    assert клиент.delay == клиент.base_delay


def test_ошибка_клиента_не_повторяется(клиент):
    """403 — это не про частоту: повторять его бессмысленно."""
    журнал = подменить_ответы(клиент, [Ответ(403)])

    результат = клиент.search_vacancies("Python")

    assert результат is None
    assert len(журнал) == 1


class TestПроверкаДоступа:
    """
    Проверка связи — один лёгкий запрос вместо целого сбора. Узнать, что
    ключ отклонён, лучше до запуска работы на десять минут.
    """

    def test_доступ_есть(self, клиент):
        подменить_ответы(клиент, [Ответ(200, payload={"items": [], "found": 0})])

        итог = клиент.проверить_доступ()

        assert итог["доступно"] is True
        assert итог["причина"] is None
        assert итог["задержка_мс"] >= 0

    def test_отказ_без_ключа_отличается_от_отклонённого(self, monkeypatch):
        """
        «Ключа нет» и «ключ отклонён» требуют разного: получить новый или
        обновить существующий. В общем сообщении они неразличимы.
        """
        monkeypatch.setattr("time.sleep", lambda _: None)

        без_ключа = HHAPIClient(email="test@example.com", access_token="")
        подменить_ответы(без_ключа, [Ответ(403)])
        assert без_ключа.проверить_доступ()["причина"] == ПричинаОтказа.НЕТ_ТОКЕНА

        с_ключом = HHAPIClient(email="test@example.com", access_token="токен")
        подменить_ответы(с_ключом, [Ответ(403)])
        assert с_ключом.проверить_доступ()["причина"] == ПричинаОтказа.ТОКЕН_ОТКЛОНЁН

    def test_недоступный_источник(self, клиент):
        import requests

        def падает(*args, **kwargs):
            raise requests.ConnectionError("сеть недоступна")

        клиент.session.get = падает

        итог = клиент.проверить_доступ()

        assert итог["доступно"] is False
        assert итог["причина"] == ПричинаОтказа.СЕТЬ

    def test_отказ_по_частоте_виден_отдельно(self, клиент):
        подменить_ответы(клиент, [Ответ(429)])

        assert клиент.проверить_доступ()["причина"] == ПричинаОтказа.СЛИШКОМ_ЧАСТО


def test_упорный_отказ_прерывает_сбор(клиент):
    """
    Если источник отказывает и после всех попыток, ошибка идёт наверх и
    сбор прекращается.

    Это осознанный выбор: продолжать значило бы набрать выборку с дырами
    и записать её как полную. Уже собранное при этом не теряется — сбор
    сохраняет результат каждого запроса сразу, а не в конце.
    """
    подменить_ответы(клиент, [Ответ(429)])

    with pytest.raises(TooManyRequests):
        клиент.search_vacancies("Python")
