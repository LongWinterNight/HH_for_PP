"""
Продолжение оборванного сбора (S6‑2a, S6‑2b).

Сбор идёт фоновой задачей внутри веб-процесса, а с резкой на срезы —
десятки минут. Перезапуск сервера означал «начинать заново»: собранное
оставалось в базе, но какие запросы пройдены, знала только память
процесса.

Проверяется и обратное свойство, более важное: продолжается только то,
что оборвалось само. Сбор, остановленный человеком, молча дособирать
нельзя — он сказал «хватит».
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.collector import VacancyCollector  # noqa: E402
from src.storage import ParserRunModel, VacancyStorage  # noqa: E402


@pytest.fixture
def склад(tmp_path, monkeypatch):
    """Хранилище на отдельной базе: тест не трогает рабочую."""
    from src import storage as модуль

    monkeypatch.setattr(модуль.settings, "db_path", tmp_path / "проверка.db")
    склад = VacancyStorage()
    yield склад
    склад.close()


def завести_сбор(склад, keywords, status, пройденные, часов_назад=1):
    """Запись о сборе с состоянием обхода, как её оставляет обрыв."""
    from sqlalchemy.orm import Session

    with Session(склад.engine) as session:
        run = ParserRunModel(
            started_at=datetime.now() - timedelta(hours=часов_назад),
            status=status,
            keywords=json.dumps(keywords, ensure_ascii=False),
            progress_state=json.dumps(
                {"пройденные_запросы": пройденные}, ensure_ascii=False
            ),
        )
        session.add(run)
        session.commit()
        return run.id


class TestСостояниеОбхода:

    def test_состояние_переживает_перезапуск(self, склад):
        run_id = завести_сбор(склад, ["Рекрутер"], "running", [])

        склад.save_run_progress(run_id, {
            "пройденные_запросы": ["Рекрутер", "HR"],
            "текущий_запрос": "HR",
        })

        # Читает другой экземпляр хранилища — как после перезапуска.
        другой = VacancyStorage()
        try:
            состояние = другой.get_run_progress(run_id)
        finally:
            другой.close()

        assert состояние["пройденные_запросы"] == ["Рекрутер", "HR"]

    def test_пустое_состояние_читается_как_пустое(self, склад):
        run_id = завести_сбор(склад, ["Рекрутер"], "running", [])

        assert склад.get_run_progress(run_id) == {"пройденные_запросы": []}

    def test_сбор_без_состояния_ничего_не_обещает(self, склад):
        # Записи до миграции 016 состояния не имеют. Пустой словарь тут
        # значит «неизвестно», и продолжать по нему нечего.
        from sqlalchemy.orm import Session

        with Session(склад.engine) as session:
            run = ParserRunModel(started_at=datetime.now(), status="interrupted",
                                 keywords=json.dumps(["Рекрутер"]))
            session.add(run)
            session.commit()
            run_id = run.id

        assert склад.get_run_progress(run_id) == {}
        assert склад.find_resumable_run(["Рекрутер"]) is None


class TestПоискПродолжаемого:

    def test_оборванный_сбор_продолжается(self, склад):
        завести_сбор(склад, ["Рекрутер", "HR"], "interrupted", ["Рекрутер"])

        найдено = склад.find_resumable_run(["Рекрутер", "HR"])

        assert найдено is not None
        assert найдено["состояние"]["пройденные_запросы"] == ["Рекрутер"]

    def test_остановленный_человеком_не_продолжается(self, склад):
        # Человек нажал «Остановить». Дособрать за него — сделать не то,
        # о чём просили.
        завести_сбор(склад, ["Рекрутер", "HR"], "stopped", ["Рекрутер"])

        assert склад.find_resumable_run(["Рекрутер", "HR"]) is None

    def test_завершённый_не_продолжается(self, склад):
        завести_сбор(склад, ["Рекрутер"], "completed", ["Рекрутер"])

        assert склад.find_resumable_run(["Рекрутер"]) is None

    def test_другой_набор_запросов_не_подходит(self, склад):
        завести_сбор(склад, ["Рекрутер", "HR"], "interrupted", ["Рекрутер"])

        assert склад.find_resumable_run(["Рекрутер", "Кадровик"]) is None

    def test_порядок_запросов_не_важен(self, склад):
        завести_сбор(склад, ["Рекрутер", "HR"], "interrupted", ["Рекрутер"])

        assert склад.find_resumable_run(["HR", "Рекрутер"]) is not None

    def test_старый_сбор_не_продолжается(self, склад):
        # За сутки выдача источника успевает смениться, и «продолжение»
        # собирало бы сегодняшнее вперемешку со вчерашним.
        завести_сбор(склад, ["Рекрутер"], "interrupted", ["Рекрутер"], часов_назад=48)

        assert склад.find_resumable_run(["Рекрутер"]) is None

    def test_обрыв_до_первого_запроса_нечего_продолжать(self, склад):
        завести_сбор(склад, ["Рекрутер", "HR"], "interrupted", [])

        assert склад.find_resumable_run(["Рекрутер", "HR"]) is None


class ПустойИсточник:
    """Источник без вакансий: проверяется только порядок обхода."""

    def __init__(self):
        self.delay = 0
        self.запрошено = []

    def search_vacancies(self, keyword, page=0, per_page=100,
                         order_by=None, date_from=None, area=None, date_to=None):
        self.запрошено.append(keyword)
        return {"items": [], "found": 0, "pages": 0}

    def get_vacancy_details(self, vacancy_id):
        return None

    def get_areas(self):
        return []


class TestПропускПройденных:

    def test_пройденные_запросы_пропускаются(self, tmp_path):
        источник = ПустойИсточник()
        сборщик = VacancyCollector(client=источник, output_dir=tmp_path, max_pages=1)

        сборщик.collect_all(
            keywords=["Рекрутер", "HR", "Кадровик"],
            save_raw=False,
            пройденные=["Рекрутер", "HR"],
        )

        assert источник.запрошено == ["Кадровик"]

    def test_без_продолжения_обходятся_все(self, tmp_path):
        источник = ПустойИсточник()
        сборщик = VacancyCollector(client=источник, output_dir=tmp_path, max_pages=1)

        сборщик.collect_all(keywords=["Рекрутер", "HR"], save_raw=False)

        assert источник.запрошено == ["Рекрутер", "HR"]
