"""
Тесты состояния сбора в базе.

Ход работы жил в словаре в памяти процесса. Перезапуск сервера уносил его
с собой: фоновая задача умирала, запись о запуске навсегда оставалась со
статусом «running», а интерфейс показывал «сбора нет».

Запуск: pytest tests/test_run_state.py -v
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.storage import VacancyStorage


@pytest.fixture
def хранилище(tmp_path):
    store = VacancyStorage(db_path=tmp_path / "test.db")
    yield store
    store.close()


class TestЗаписьХода:
    def test_прогресс_попадает_в_запись(self, хранилище):
        run_id = хранилище.create_parser_run(keywords=["Python"])

        записано = хранилище.update_run_progress(
            run_id, collected=42, current_keyword="Python", current_page=2,
            found_estimate=200, percent=21,
        )
        активный = хранилище.get_active_run()

        assert записано is True
        assert активный["vacancies_collected"] == 42
        assert активный["current_keyword"] == "Python"
        assert активный["current_page"] == 2
        assert активный["found_estimate"] == 200
        assert активный["progress"] == 21

    def test_база_процент_хранит_а_не_считает(self, хранилище):
        """
        Прежде база делила собранное на найденное сама: 712 собранных за
        весь сбор на 175 найденных по второму запросу давали 99 % при
        трёх запросах впереди. Считает `src.progress`, база хранит.
        """
        run_id = хранилище.create_parser_run(keywords=["3dsmax", "рендер"])

        хранилище.update_run_progress(run_id, collected=712, found_estimate=175, percent=39)

        assert хранилище.get_active_run()["progress"] == 39

    def test_процент_в_базе_не_ходит_назад(self, хранилище):
        run_id = хранилище.create_parser_run(keywords=["Python"])

        хранилище.update_run_progress(run_id, collected=10, percent=60, min_interval=0)
        хранилище.update_run_progress(run_id, collected=20, percent=45, min_interval=0)

        assert хранилище.get_active_run()["progress"] == 60

    def test_процент_без_знаменателя_не_выдумывается(self, хранилище):
        """Источник не сказал, сколько всего, — процента нет."""
        run_id = хранилище.create_parser_run(keywords=["Python"])

        хранилище.update_run_progress(run_id, collected=10)

        assert хранилище.get_active_run()["progress"] == 0

    def test_запись_прореживается_по_времени(self, хранилище):
        """
        Событий хода приходят сотни, а ценность у записи одна: показать,
        что работа идёт. Без прореживания сбор конкурировал бы сам с
        собой за базу.
        """
        run_id = хранилище.create_parser_run(keywords=["Python"])

        первая = хранилище.update_run_progress(run_id, collected=1)
        вторая = хранилище.update_run_progress(run_id, collected=2)

        assert первая is True
        assert вторая is False
        # В базе осталось значение первой записи.
        assert хранилище.get_active_run()["vacancies_collected"] == 1

    def test_прореживание_отключается_параметром(self, хранилище):
        run_id = хранилище.create_parser_run(keywords=["Python"])

        хранилище.update_run_progress(run_id, collected=1)
        вторая = хранилище.update_run_progress(run_id, collected=5, min_interval=0)

        assert вторая is True
        assert хранилище.get_active_run()["vacancies_collected"] == 5


class TestИдущийСбор:
    def test_без_сборов_ничего_не_идёт(self, хранилище):
        assert хранилище.get_active_run() is None

    def test_завершённый_сбор_не_считается_идущим(self, хранилище):
        run_id = хранилище.create_parser_run(keywords=["Python"])
        хранилище.complete_parser_run(run_id, status="completed", vacancies_collected=5)

        assert хранилище.get_active_run() is None


class TestОборвавшиесяСборы:
    def test_старый_running_помечается_прерванным(self, хранилище):
        run_id = хранилище.create_parser_run(keywords=["Python"])
        # Отметка живости давняя: процесс не пережил перезапуск.
        хранилище.update_run_progress(run_id, collected=3)
        _состарить(хранилище, run_id, минут=30)

        помечено = хранилище.mark_interrupted_runs(stale_after_minutes=5)

        assert помечено == 1
        assert хранилище.get_active_run() is None
        история = хранилище.get_parser_runs_history(limit=1)[0]
        assert история["status"] == "interrupted"
        assert "перезапущено" in (история.get("error_message") or "")

    def test_живой_сбор_не_трогается(self, хранилище):
        run_id = хранилище.create_parser_run(keywords=["Python"])
        хранилище.update_run_progress(run_id, collected=3)

        помечено = хранилище.mark_interrupted_runs(stale_after_minutes=5)

        assert помечено == 0
        assert хранилище.get_active_run() is not None

    def test_запись_без_отметки_живости_считается_оборвавшейся(self, хранилище):
        """
        Сбор, упавший до первого события, отметки не оставил — но он
        точно не идёт: процесс, который его вёл, уже мёртв.
        """
        хранилище.create_parser_run(keywords=["Python"])

        assert хранилище.mark_interrupted_runs(stale_after_minutes=5) == 1


class TestСнимкиМетрик:
    """
    Точки истории. Тренды нельзя считать сравнением периодов внутри
    одного среза базы: источник отдаёт только открытые вакансии, и старые
    дни к моменту сбора успевают опустеть — выходит «рост рынка» там, где
    затухание архива.
    """

    def test_снимок_считает_состояние_базы(self, хранилище):
        import pandas as pd

        хранилище.save_vacancies_incremental(pd.DataFrame([
            _вакансия("1", salary_from=100000, employer="Первая"),
            _вакансия("2", salary_from=200000, employer="Вторая"),
        ]))

        снимок = хранилище.save_metrics_snapshot()

        assert снимок["active_vacancies"] == 2
        assert снимок["unique_companies"] == 2
        assert снимок["with_salary"] == 2
        assert снимок["median_salary_rub"] == 150000
        assert снимок["source"] == "measured"

    def test_снимки_читаются_от_новых_к_старым(self, хранилище):
        import pandas as pd

        хранилище.save_vacancies_incremental(pd.DataFrame([_вакансия("1")]))
        хранилище.save_metrics_snapshot()
        хранилище.save_vacancies_incremental(pd.DataFrame([_вакансия("2")]))
        хранилище.save_metrics_snapshot()

        точки = хранилище.get_metrics_snapshots(limit=5)

        assert len(точки) == 2
        assert точки[0]["active_vacancies"] == 2
        assert точки[1]["active_vacancies"] == 1

    def test_восстановленные_отделимы_от_замеров(self, хранилище):
        """
        У восстановленных точек нет зарплатных метрик, и выдавать их за
        замер нельзя: в базе лежит сегодняшняя зарплата, а не та, что
        была на дату снимка.
        """
        import pandas as pd
        from sqlalchemy import text

        хранилище.save_vacancies_incremental(pd.DataFrame([_вакансия("1")]))
        хранилище.save_metrics_snapshot()

        with хранилище.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO metrics_snapshots (taken_at, source, total_vacancies) "
                "VALUES (:t, 'reconstructed', 100)"
            ), {"t": datetime.now() - timedelta(days=30)})

        все = хранилище.get_metrics_snapshots(limit=10)
        только_замеры = хранилище.get_metrics_snapshots(limit=10, only_measured=True)

        assert len(все) == 2
        assert len(только_замеры) == 1
        assert только_замеры[0]["source"] == "measured"


def _вакансия(vacancy_id: str, salary_from: float = 100000, employer: str = "Компания") -> dict:
    return {
        "vacancy_id": vacancy_id,
        "vacancy_name": "Аналитик",
        "published_at": "2026-09-01T10:00:00+0300",
        "salary_from": salary_from,
        "salary_currency": "RUB",
        "employer_name": employer,
        "area": "Москва",
        "experience": "От 1 года до 3 лет",
        "skill_count": 2,
    }


class TestНастройкиСбора:
    """
    Почта и пауза между запросами. Прежде они жили в словаре в памяти и в
    файле окружения, куда почту дописывали заменой по регулярному
    выражению, а пауза не доходила до клиента вовсе.
    """

    def test_настройки_сохраняются_и_читаются(self, хранилище):
        сохранено = хранилище.save_collection_settings(
            email="analyst@company.ru", request_delay=0.5
        )

        assert сохранено["email"] == "analyst@company.ru"
        assert сохранено["request_delay"] == 0.5
        assert хранилище.get_collection_settings()["email"] == "analyst@company.ru"

    def test_частичное_сохранение_не_стирает_остальное(self, хранилище):
        хранилище.save_collection_settings(email="analyst@company.ru", request_delay=0.5)

        хранилище.save_collection_settings(request_delay=2.0)

        итог = хранилище.get_collection_settings()
        assert итог["email"] == "analyst@company.ru"
        assert итог["request_delay"] == 2.0

    def test_первичные_значения_берутся_из_окружения(self, хранилище, monkeypatch):
        """
        При первом запуске база пуста, а настроенное в окружении терять
        незачем — иначе сбор потребует ввести почту заново.
        """
        from src import storage as storage_module

        monkeypatch.setattr(storage_module.settings, "hh_user_email", "from@env.ru")

        assert хранилище.get_collection_settings()["email"] == "from@env.ru"

    def test_сохранённое_важнее_окружения(self, хранилище, monkeypatch):
        from src import storage as storage_module

        monkeypatch.setattr(storage_module.settings, "hh_user_email", "from@env.ru")
        хранилище.save_collection_settings(email="saved@company.ru")

        assert хранилище.get_collection_settings()["email"] == "saved@company.ru"


def _состарить(хранилище, run_id: int, минут: int) -> None:
    """Отодвинуть отметку живости в прошлое."""
    from sqlalchemy import text

    with хранилище.engine.begin() as conn:
        conn.execute(
            text("UPDATE parser_runs SET heartbeat_at = :t WHERE id = :id"),
            {"t": datetime.now() - timedelta(minutes=минут), "id": run_id},
        )
