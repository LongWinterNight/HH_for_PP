"""
Список готовых отчётов: чем файл себя называет и как его убрать.

Экран показывает объём выборки и условия по каждому файлу, а берёт их
из самого файла — не из второй копии в базе, которая разошлась бы с
содержимым. Здесь проверяется, что чтение работает, что чужой файл его
не роняет и что удаление не выходит за папку отчётов: имя приходит из
адреса, и обход каталога — самая дешёвая ошибка в таком месте.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from src.config import settings
from src.report_xlsx import прочитать_срез, собрать_отчёт, описать_срез
from web.app.main import _срезы_файлов, delete_report, list_reports

ВЫБОРКА = pd.DataFrame([
    {
        "vacancy_id": "1", "vacancy_name": "Аналитик", "area": "Москва",
        "experience": "Нет опыта", "hard_skills": "sql", "tools": "",
        "soft_skills": "", "salary_from": 100000, "salary_to": None,
        "salary_currency": "RUB", "published_at": "2026-09-01",
    },
    {
        "vacancy_id": "2", "vacancy_name": "Аналитик данных", "area": "Казань",
        "experience": "Нет опыта", "hard_skills": "python", "tools": "",
        "soft_skills": "", "salary_from": None, "salary_to": None,
        "salary_currency": "RUB", "published_at": "2026-09-02",
    },
])


@pytest.fixture
def папка(tmp_path, monkeypatch):
    """Отдельная папка отчётов: тест не трогает собранное вживую."""
    monkeypatch.setattr(settings, "reports_dir", tmp_path)
    _срезы_файлов.clear()
    return tmp_path


@pytest.fixture
def отчёт(папка):
    return собрать_отчёт(
        ВЫБОРКА,
        путь=папка / "basevacancy_2026-09-12_1200.xlsx",
        срез=описать_срез(ВЫБОРКА, фильтры="поиск «аналитик», регион: Москва"),
    )


class TestЧтениеСреза:

    def test_объём_и_условия_читаются_из_файла(self, отчёт):
        срез = прочитать_срез(отчёт)
        assert срез["вакансий"] == 2
        assert срез["срез"] == "поиск «аналитик», регион: Москва"

    def test_файл_без_листа_среза_молчит(self, папка):
        """Выгрузка старого анализатора не должна выдумывать себе срез."""
        чужой = папка / "hh_analytics_report.xlsx"
        wb = Workbook()
        wb.active.title = "Данные"
        wb.save(чужой)
        assert прочитать_срез(чужой) == {}

    def test_битый_файл_не_роняет_чтение(self, папка):
        недописанный = папка / "basevacancy_2026-09-12_1300.xlsx"
        недописанный.write_bytes(b"PK\x03\x04 and nothing more")
        assert прочитать_срез(недописанный) == {}


class TestСписок:

    def test_срез_приходит_в_список(self, отчёт):
        строка = list_reports()["reports"][0]
        assert строка["name"] == отчёт.name
        assert строка["vacancies"] == 2
        assert "аналитик" in строка["slice"]

    def test_csv_виден_наравне_с_xlsx(self, папка, отчёт):
        (папка / "vacancies_export_20260912_1200.csv").write_text("id\n1\n", encoding="utf-8")
        имена = [r["name"] for r in list_reports()["reports"]]
        assert "vacancies_export_20260912_1200.csv" in имена
        assert отчёт.name in имена

    def test_чужой_файл_остаётся_в_списке_с_пустыми_полями(self, папка):
        (папка / "vacancies_export_20260912_1200.csv").write_text("id\n1\n", encoding="utf-8")
        строка = list_reports()["reports"][0]
        assert строка["vacancies"] is None and строка["slice"] is None

    def test_второй_запрос_не_открывает_файлы_заново(self, отчёт, monkeypatch):
        import src.report_xlsx as модуль

        вызовы = []
        настоящее = модуль.прочитать_срез
        monkeypatch.setattr(
            модуль, "прочитать_срез",
            lambda путь: (вызовы.append(путь), настоящее(путь))[1],
        )

        list_reports()
        list_reports()
        assert len(вызовы) == 1

    def test_перезаписанный_файл_читается_заново(self, отчёт, папка):
        list_reports()
        собрать_отчёт(
            ВЫБОРКА.head(1), путь=отчёт,
            срез=описать_срез(ВЫБОРКА.head(1), фильтры="регион: Казань"),
        )
        строка = list_reports()["reports"][0]
        assert строка["vacancies"] == 1 and строка["slice"] == "регион: Казань"


class TestУдаление:

    def test_файл_удаляется(self, отчёт):
        assert delete_report(отчёт.name) == {"deleted": отчёт.name}
        assert not отчёт.exists()
        assert list_reports()["reports"] == []

    @pytest.mark.parametrize("путь", [
        "../config.yaml",
        "..\config.yaml",
        "sub/../../config.yaml",
    ])
    def test_путь_наружу_отклонён(self, папка, путь):
        снаружи = папка.parent / "config.yaml"
        снаружи.write_text("важное", encoding="utf-8")

        with pytest.raises(HTTPException) as отказ:
            delete_report(путь)

        assert отказ.value.status_code == 400
        assert снаружи.exists()

    def test_отсутствующего_файла_нет(self, папка):
        with pytest.raises(HTTPException) as отказ:
            delete_report("basevacancy_1999-01-01_0000.xlsx")
        assert отказ.value.status_code == 404


class TestСрокХранения:
    """
    Свои отчёты старше срока уходят сами, чужие файлы — только руками.

    Решение владельца 12.09.2026. В папке лежат ещё экспорты и выгрузки
    прежних анализаторов: пересобрать их продукт не может, и уборка по
    сроку унесла бы единственную копию.
    """

    def test_свой_старый_убран_свежий_и_чужой_остались(self, папка, отчёт, monkeypatch):
        import src.report_xlsx as модуль

        чужой = папка / "hh_analytics_report_20260418.xlsx"
        чужой.write_bytes(отчёт.read_bytes())
        старый = папка / "basevacancy_2026-08-01_1200.xlsx"
        старый.write_bytes(отчёт.read_bytes())

        # Уборка со сроком в ноль дней трогает всё своё и ничего чужого.
        убранные = модуль.убрать_устаревшие(папка, срок=-1)
        assert sorted(убранные) == sorted([отчёт.name, старый.name])
        assert чужой.exists()

    def test_свежий_отчёт_уборку_переживает(self, папка, отчёт):
        from src.report_xlsx import убрать_устаревшие

        assert убрать_устаревшие(папка) == []
        assert отчёт.exists()

    def test_список_называет_убранное_и_срок(self, папка, отчёт, monkeypatch):
        import src.report_xlsx as модуль

        monkeypatch.setattr(модуль, "убрать_устаревшие", lambda папка: ["basevacancy_старый.xlsx"])
        ответ = list_reports()
        assert ответ["retention"] == {"days": 30, "removed": ["basevacancy_старый.xlsx"]}

    def test_истекает_только_свой_файл(self):
        from src.report_xlsx import собран_продуктом
        from web.app.main import _состояние_файла

        день = 86400
        свой = _состояние_файла("basevacancy_x.xlsx", 0, 28 * день, собран_продуктом, 30, 3)
        assert свой == {"state": "expiring", "expires_in_days": 2}

        молодой = _состояние_файла("basevacancy_x.xlsx", 0, 5 * день, собран_продуктом, 30, 3)
        assert молодой == {"state": "ready", "expires_in_days": 25}

        чужой = _состояние_файла("vacancies_export.csv", 0, 200 * день, собран_продуктом, 30, 3)
        assert чужой == {"state": "ready", "expires_in_days": None}
