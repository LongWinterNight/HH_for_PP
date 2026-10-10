"""
Запросы сбора: список правится с экрана и ничем не подменяется.

Главная проверка здесь — первая. Пустой список запросов молча заменялся
списком из конфига: 58 запросов и часы работы, которых никто не просил.
Кнопка на экране при пустом списке заблокирована, но API открыт —
запустить чужой сбор мог старый интерфейс, ошибка в клиенте или повтор
запроса из истории браузера. Остановить его потом можно было только
руками.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import web.app.main as api


@pytest.fixture
def почта_настроена(monkeypatch):
    """Проверка почты идёт раньше запросов — без неё до них не дойти."""
    monkeypatch.setitem(api.user_settings, "hh_user_email", "человек@example.com")
    monkeypatch.setitem(api.parser_state, "is_running", False)


class TestЗапускБезЗапросов:

    @pytest.mark.parametrize("список", [None, [], [""], ["   "]])
    def test_пустой_список_не_запускает_сбор(self, почта_настроена, список):
        with pytest.raises(HTTPException) as отказ:
            api.start_parser(background_tasks=None, keywords=список)

        assert отказ.value.status_code == 400
        assert "запрос" in отказ.value.detail.lower(), (
            "в отказе должно быть сказано, чего не хватает"
        )

    def test_конфиг_не_подставляется(self, почта_настроена, monkeypatch):
        """
        Список из конфига в веб-запуск не попадает ни при каких условиях.

        Проверяется прямо: подменяем конфиг заметным значением и следим,
        что оно не всплыло в сборе.
        """
        from src.config import config_loader

        # Список читается свойством без сеттера — подменяется на классе.
        monkeypatch.setattr(
            type(config_loader), "search_queries",
            property(lambda _: ["метка-из-конфига"] * 58),
        )

        with pytest.raises(HTTPException) as отказ:
            api.start_parser(background_tasks=None, keywords=[])

        assert "метка-из-конфига" not in отказ.value.detail
        assert api.parser_state["is_running"] is False, "сбор не должен был начаться"


class TestОчисткаСписка:

    def test_пробелы_по_краям_не_создают_запрос(self, почта_настроена):
        """«  » — это не запрос, а промах по клавише пробела."""
        with pytest.raises(HTTPException):
            api.start_parser(background_tasks=None, keywords=["", "  ", None])
