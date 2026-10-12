"""
Сверка базы с моделями при старте.

Колонка попадает в рабочую базу только миграцией, которую запускают
руками. Код, обновлённый раньше базы, падал на первом запросе словами
`no such column`. Здесь проверяется, что расхождение находится заранее
и называется вместе с командой, которая его устраняет.
"""

from __future__ import annotations

import sqlite3

import pytest

from src import schema_check
from src.config import settings
from src.storage import VacancyStorage


@pytest.fixture
def база():
    VacancyStorage(db_path=settings.db_path).close()
    return settings.db_path


def _без_колонки(путь, таблица: str, колонка: str) -> None:
    conn = sqlite3.connect(путь)
    conn.execute(f"ALTER TABLE {таблица} DROP COLUMN {колонка}")
    conn.commit()
    conn.close()


class TestСверка:

    def test_свежая_база_соответствует_коду(self, база):
        assert schema_check.недостающие(база) == {}

    def test_нет_базы_расхождений_нет(self, tmp_path):
        # Базу создаст хранилище: сверять пока не с чем.
        assert schema_check.недостающие(tmp_path / "нет.db") == {}

    def test_отставшая_база_названа_по_колонкам(self, база):
        _без_колонки(база, "parser_runs", "stop_requested")
        _без_колонки(база, "parser_runs", "source")

        assert schema_check.недостающие(база) == {"parser_runs": ["source", "stop_requested"]}

    def test_лишняя_колонка_базы_не_расхождение(self, база):
        conn = sqlite3.connect(база)
        conn.execute("ALTER TABLE parser_runs ADD COLUMN будущее TEXT")
        conn.commit()
        conn.close()

        assert schema_check.недостающие(база) == {}

    def test_объяснение_называет_команду(self, база):
        _без_колонки(база, "parser_runs", "source")

        текст = schema_check.объяснение(schema_check.недостающие(база), база)

        assert "parser_runs: source" in текст
        assert "021_run_source.py" in текст and "--yes" in текст, "без команды объяснение не помогает"

    def test_одноимённая_колонка_ищется_в_своей_таблице(self):
        # `source` есть и у вакансий (017), и у запусков (021).
        assert schema_check.миграция_для("parser_runs", "source") == "021_run_source.py"
        assert schema_check.миграция_для("vacancies", "source") == "017_source_key.py"

    def test_нет_миграции_сказано_прямо(self, база, tmp_path):
        _без_колонки(база, "parser_runs", "source")

        текст = schema_check.объяснение(schema_check.недостающие(база), база, папка=tmp_path)

        assert "не найдена" in текст


class TestКоманда:

    def test_сбор_на_отставшей_базе_не_начинается(self, база, monkeypatch):
        import importlib

        import src.alerts

        отправлено = []
        monkeypatch.setattr(src.alerts, "сообщить", lambda отказ, **прочее: отправлено.append(отказ))
        _без_колонки(база, "parser_runs", "source")
        команда = importlib.import_module("scripts.собрать")

        assert команда.main(["--без-копии"]) == команда.НЕ_НАСТРОЕНО
        assert [отказ.причина for отказ in отправлено] == ["schema"]
        assert "021_run_source.py" in отправлено[0].подробности
