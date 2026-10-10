"""
Состояние сборки отчёта.

Кнопка отвечала «Генерация запущена» и замолкала: сборка идёт секунды и
может отказать, но упавшая выглядела так же, как удачная — файл просто
не появлялся в списке. Тест закрепляет три вещи, из которых состоит
честный ответ: состояние читается, отказ назван словами, а пустая база
и второй запуск поверх первого до сборки не доходят.

Запуск: pytest tests/test_статус_отчёта.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi import BackgroundTasks

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import anyio

import src.storage as storage_module
import web.app.main as main
from src.storage import VacancyStorage


def вакансия(vacancy_id: str = "1") -> dict:
    """Строка в том виде, в каком её отдаёт нормализация сбора."""
    return {
        "vacancy_id": vacancy_id,
        "vacancy_name": "Аналитик данных",
        "published_at": "2026-09-01T10:00:00+0300",
        "salary_from": 100000,
        "salary_to": 150000,
        "salary_currency": "RUB",
        "employer_name": "Компания",
        "employer_id": vacancy_id,
        "employer_url": "",
        "vacancy_url": "",
        "experience": "От 1 года до 3 лет",
        "employment": "Полная занятость",
        "schedule": "Удалённо",
        "area": "Москва",
        "all_skills": "python",
        "hard_skills": "python",
        "soft_skills": "",
        "tools": "",
        "skill_count": 1,
        "hard_skill_count": 1,
        "soft_skill_count": 0,
        "tools_count": 0,
    }


@pytest.fixture(autouse=True)
def чистое_состояние():
    """Состояние сборки живёт в модуле — тесты не должны наследовать чужое."""
    было = dict(main.состояние_отчёта)
    main.состояние_отчёта.update({
        "status": "idle", "started_at": None, "finished_at": None,
        "file": None, "vacancies": None, "error": None,
    })
    yield
    main.состояние_отчёта.update(было)


def база(tmp_path, monkeypatch, строки, имя="проба.db"):
    """Подменяет хранилище на временное с заданными вакансиями."""
    путь = tmp_path / имя
    склад = VacancyStorage(db_path=путь)
    if строки:
        склад.save_vacancies_incremental(pd.DataFrame(строки))
    склад.close()
    monkeypatch.setattr(
        storage_module, "VacancyStorage", lambda *a, **k: VacancyStorage(db_path=путь)
    )
    return путь


def собрать():
    """Запуск сборки вместе с её фоновой задачей."""
    задачи = BackgroundTasks()
    ответ = main.generate_report(задачи)
    anyio.run(задачи)
    return ответ


class TestСостояниеЧитается:
    """idle → running → done, и каждое состояние доступно снаружи."""

    def test_путь_от_запуска_до_готового_файла(self, tmp_path, monkeypatch):
        база(tmp_path, monkeypatch, [вакансия("1"), вакансия("2")])
        monkeypatch.setattr(main._app_settings, "reports_dir", tmp_path / "отчёты")
        (tmp_path / "отчёты").mkdir()

        assert main.report_status()["status"] == "idle"

        задачи = BackgroundTasks()
        ответ = main.generate_report(задачи)
        assert ответ["accepted"] is True
        assert main.report_status()["status"] == "running", "сборка идёт — это видно"

        anyio.run(задачи)

        итог = main.report_status()
        assert итог["status"] == "done"
        assert итог["file"].endswith(".xlsx")
        assert итог["vacancies"] == 2
        assert итог["error"] is None


class TestОтказНазванСловами:
    """Причина отказа должна подсказывать следующий шаг."""

    def test_пустая_база_не_собирается(self, tmp_path, monkeypatch):
        база(tmp_path, monkeypatch, [])

        ответ = main.generate_report(BackgroundTasks())

        assert ответ["accepted"] is False
        assert ответ["status"] == "error"
        assert "нет вакансий" in ответ["error"]
        assert "соберите данные" in ответ["error"].lower()

    def test_второй_запуск_поверх_идущего_отклоняется(self, tmp_path, monkeypatch):
        база(tmp_path, monkeypatch, [вакансия("1")])
        main.состояние_отчёта["status"] = "running"

        ответ = main.generate_report(BackgroundTasks())

        assert ответ["accepted"] is False
        assert "уже собирается" in ответ["error"]

    def test_поломка_сборки_объясняется_а_не_кодируется(self, tmp_path, monkeypatch):
        база(tmp_path, monkeypatch, [вакансия("1")])

        def падает(*args, **kwargs):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr("src.report_xlsx.собрать_отчёт", падает)

        собрать()

        итог = main.report_status()
        assert итог["status"] == "error"
        assert итог["file"] is None
        # Человек читает тост, а не лог: «Errno 13» ему ничего не говорит.
        assert "Errno" not in итог["error"]
        assert "Excel" in итог["error"]

    def test_неизвестная_причина_не_выдумывается(self, tmp_path, monkeypatch):
        база(tmp_path, monkeypatch, [вакансия("1")])

        def падает(*args, **kwargs):
            raise ValueError("лист «Срез» не собрался")

        monkeypatch.setattr("src.report_xlsx.собрать_отчёт", падает)

        собрать()

        итог = main.report_status()
        assert итог["status"] == "error"
        assert "лист «Срез» не собрался" in итог["error"]
