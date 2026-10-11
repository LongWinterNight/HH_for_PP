"""
Сбор по расписанию: один путь сбора, два процесса, честный календарь.

Сбор по расписанию идёт отдельным процессом. Отсюда главные проверки:
приложение не принимает его запись за след собственного умершего сбора,
два сбора не идут одновременно, остановка дотягивается через базу, а
сбор, который не запустился вовсе, виден по календарю.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from src import collection_run, schedule
from src.config import settings
from src.storage import VacancyStorage


@pytest.fixture
def storage():
    хранилище = VacancyStorage(db_path=settings.db_path)
    yield хранилище
    хранилище.close()


def _сдвинуть_живость(storage, запуск: int, минут: int) -> None:
    """Сделать вид, что сбор молчит столько минут."""
    когда = datetime.now() - timedelta(minutes=минут)
    conn = sqlite3.connect(settings.db_path)
    conn.execute("UPDATE parser_runs SET heartbeat_at = ? WHERE id = ?", (когда.isoformat(sep=" "), запуск))
    conn.commit()
    conn.close()


class TestДваПроцесса:

    def test_источник_запуска_записан(self, storage):
        с_экрана = storage.create_parser_run(["Python"])
        по_расписанию = storage.create_parser_run(["Python"], source=collection_run.РАСПИСАНИЕ)
        история = {запись["id"]: запись["source"] for запись in storage.get_parser_runs_history()}
        assert история == {с_экрана: "screen", по_расписанию: "schedule"}

    def test_старт_приложения_не_трогает_живой_сбор_по_расписанию(self, storage):
        свой = storage.create_parser_run(["Python"])
        чужой = storage.create_parser_run(["Python"], source=collection_run.РАСПИСАНИЕ)

        # Так приложение разбирает прерванные сборы на старте.
        помечено = storage.mark_interrupted_runs(stale_after_minutes=0, foreign_stale_minutes=15)

        assert помечено == 1, "свой сбор умер вместе с прежним процессом, чужой — идёт"
        активный = storage.get_active_run()
        assert активный["id"] == чужой and активный["source"] == "schedule"
        статусы = {запись["id"]: запись["status"] for запись in storage.get_parser_runs_history()}
        assert статусы[свой] == "interrupted"

    def test_замолчавший_сбор_по_расписанию_считается_оборванным(self, storage):
        запуск = storage.create_parser_run(["Python"], source=collection_run.РАСПИСАНИЕ)
        _сдвинуть_живость(storage, запуск, минут=40)

        assert storage.mark_interrupted_runs(stale_after_minutes=0, foreign_stale_minutes=15) == 1
        запись = storage.get_parser_runs_history()[0]
        assert запись["status"] == "interrupted" and "расписанию" in запись["error_message"]

    def test_идущий_сбор_блокирует_второй_а_зависший_нет(self, storage):
        запуск = storage.create_parser_run(["Python"], source=collection_run.РАСПИСАНИЕ)
        assert collection_run.идёт_другой_сбор(storage)["id"] == запуск

        _сдвинуть_живость(storage, запуск, минут=collection_run.МОЛЧАНИЕ_ЧУЖОГО_СБОРА_МИН + 5)
        assert collection_run.идёт_другой_сбор(storage) is None, (
            "сбор, умерший вместе с компьютером, не должен блокировать следующие навсегда"
        )

    def test_экран_отказывает_пока_идёт_сбор_по_расписанию(self, storage, monkeypatch):
        from fastapi import HTTPException

        import web.app.main as api

        monkeypatch.setitem(api.user_settings, "hh_user_email", "человек@example.com")
        monkeypatch.setitem(api.parser_state, "is_running", False)
        запуск = storage.create_parser_run(["Python"], source=collection_run.РАСПИСАНИЕ)

        with pytest.raises(HTTPException) as отказ:
            api.start_parser(background_tasks=None, keywords=["Python"])

        assert отказ.value.status_code == 400
        assert "по расписанию" in отказ.value.detail and f"№{запуск}" in отказ.value.detail

    def test_остановка_с_экрана_доходит_через_базу(self, storage, monkeypatch):
        import web.app.main as api

        monkeypatch.setitem(api.parser_state, "is_running", False)
        запуск = storage.create_parser_run(["Python"], source=collection_run.РАСПИСАНИЕ)
        assert storage.is_run_stop_requested(запуск) is False

        ответ = api.stop_parser()

        assert ответ["state"]["status"] == "stopping"
        assert storage.is_run_stop_requested(запуск) is True

    def test_остановить_нечего_отказ(self, monkeypatch):
        from fastapi import HTTPException

        import web.app.main as api

        monkeypatch.setitem(api.parser_state, "is_running", False)
        with pytest.raises(HTTPException):
            api.stop_parser()


class _Сборщик:
    """Сборщик без сети: отдаёт заготовленный итог или падает."""

    итог = {"unique": 12, "new": 5, "updated": 2, "by_keyword": {}, "качество": {}}
    ошибка = None
    остановить_сразу = False

    def __init__(self, **параметры):
        self.параметры = параметры
        self.stop_requested = False
        _Сборщик.последний = self

    def request_stop(self):
        self.stop_requested = True

    def collect_all(self, keywords, save_raw, пройденные):
        if self.ошибка:
            raise self.ошибка
        if self.остановить_сразу:
            self.request_stop()
        self.параметры["on_progress"](SimpleNamespace(
            stage="keyword_saved", keyword=keywords[0], page=1, collected=12, found=12,
            keyword_index=1, keywords_total=len(keywords), keyword_done=12, keyword_total=12,
            new=5, updated=2, vacancy=None,
        ))
        return dict(self.итог)

    def close(self):
        pass


@pytest.fixture
def без_сети(monkeypatch, tmp_path):
    """Сбор без источника и без настоящих оповещений."""
    import src.alerts
    import src.api_client
    import src.collector

    отправлено = []
    monkeypatch.setattr(src.collector, "VacancyCollector", _Сборщик)
    monkeypatch.setattr(src.api_client, "HHAPIClient", lambda **параметры: SimpleNamespace(**параметры))
    monkeypatch.setattr(src.alerts, "сообщить", lambda отказ, **прочее: отправлено.append(отказ))
    monkeypatch.setattr(VacancyStorage, "refresh_currency_rates", lambda self: None)
    monkeypatch.setattr(_Сборщик, "ошибка", None)
    monkeypatch.setattr(_Сборщик, "остановить_сразу", False)
    return отправлено


class TestПроведениеСбора:

    def test_удачный_сбор_записан_в_историю_с_источником(self, storage, без_сети):
        исход = collection_run.провести(["Python"], email="a@b.c", пауза=0.1, источник=collection_run.РАСПИСАНИЕ)

        assert исход.удался and (исход.собрано, исход.новых, исход.обновлено) == (12, 5, 2)
        запись = storage.get_parser_runs_history()[0]
        assert запись["id"] == исход.запуск
        assert (запись["status"], запись["source"], запись["vacancies_new"]) == ("completed", "schedule", 5)
        assert storage.get_active_run() is None
        assert без_сети == [], "удачный сбор никого не будит"

    def test_сборщик_получает_параметры_как_с_экрана(self, без_сети):
        collection_run.провести(
            ["Python"], email="a@b.c", пауза=0.1, max_pages=3, days_back=7, incremental=True, глубоко=False,
        )
        параметры = _Сборщик.последний.параметры
        assert (параметры["max_pages"], параметры["days_back"]) == (3, 7)
        assert параметры["incremental"] is True and параметры["резать_упёршиеся"] is False

    def test_отказ_записан_и_о_нём_сообщено(self, storage, без_сети, monkeypatch):
        monkeypatch.setattr(_Сборщик, "ошибка", RuntimeError("источник молчит"))

        исход = collection_run.провести(["Python"], email="a@b.c", пауза=0.1, источник=collection_run.РАСПИСАНИЕ)

        assert исход.статус == collection_run.ОТКАЗ and исход.причина == "unknown"
        запись = storage.get_parser_runs_history()[0]
        assert запись["status"] == "error" and "источник молчит" in запись["error_message"]
        assert [отказ.запуск for отказ in без_сети] == [исход.запуск]

    def test_остановленный_сбор_не_записан_удачным(self, storage, без_сети, monkeypatch):
        monkeypatch.setattr(_Сборщик, "остановить_сразу", True)

        исход = collection_run.провести(["Python"], email="a@b.c", пауза=0.1)

        assert исход.статус == collection_run.ОСТАНОВЛЕН and not исход.удался
        assert storage.get_parser_runs_history()[0]["status"] == "stopped"
        assert storage.get_last_parser_run(only_successful=True) is None

    def test_состояние_экрана_обновляется_тем_же_сбором(self, без_сети):
        состояние = collection_run.новое_состояние(
            ["Python"], запуск=None, max_pages=10, incremental=True, use_cache=True, глубоко=True,
        )
        исход = collection_run.провести(["Python"], email="a@b.c", пауза=0.1, состояние=состояние)

        assert состояние["status"] == "completed" and состояние["progress"] == 100
        assert состояние["is_running"] is False and состояние["vacancies_collected"] == 12
        assert состояние["queries"][0] == {"keyword": "Python", "status": "done", "found": 12, "new": 5, "updated": 2}
        assert исход.запуск is not None


class TestКоманда:

    def _настроить(self, storage, запросы, почта="человек@example.com"):
        storage.save_collection_settings(email=почта, request_delay=0.1, search_queries=запросы)

    def test_без_запросов_сбор_не_начат_и_об_этом_сообщено(self, storage, без_сети, monkeypatch):
        import importlib

        monkeypatch.setattr(settings, "hh_user_email", "")
        self._настроить(storage, [], почта="")
        команда = importlib.import_module("scripts.собрать")

        assert команда.main([]) == команда.НЕ_НАСТРОЕНО
        assert storage.get_parser_runs_history() == []
        assert len(без_сети) == 1 and без_сети[0].причина in ("no_queries", "no_email")

    def test_сбор_идёт_запуск_пропущен_без_тревоги(self, storage, без_сети):
        import importlib

        self._настроить(storage, ["Python"])
        storage.create_parser_run(["Python"])
        команда = importlib.import_module("scripts.собрать")

        assert команда.main(["--без-копии"]) == команда.ЗАНЯТО
        assert без_сети == [], "человек собирает руками — это не отказ"

    def test_сбор_прошёл_код_ноль_и_только_дописывание(self, storage, без_сети):
        import importlib

        self._настроить(storage, ["Python", "LLM"])
        команда = importlib.import_module("scripts.собрать")

        assert команда.main(["--без-копии"]) == команда.УСПЕХ
        assert _Сборщик.последний.параметры["incremental"] is True
        запись = storage.get_parser_runs_history()[0]
        assert запись["keywords"] == ["Python", "LLM"] and запись["source"] == "schedule"

    def test_отказ_даёт_ненулевой_код(self, storage, без_сети, monkeypatch):
        import importlib

        self._настроить(storage, ["Python"])
        monkeypatch.setattr(_Сборщик, "ошибка", RuntimeError("сеть"))
        команда = importlib.import_module("scripts.собрать")

        assert команда.main(["--без-копии"]) == команда.ОТКАЗ


class TestРасписание:

    def test_запись_читается_обратно(self, tmp_path):
        файл = tmp_path / "schedule.json"
        schedule.записать("03:30", 2, путь=файл)
        assert schedule.прочитать(файл)["время"] == "03:30" and schedule.прочитать(файл)["каждые_дней"] == 2

    @pytest.mark.parametrize("время", ["25:00", "три часа", ""])
    def test_непонятное_время_не_записывается(self, tmp_path, время):
        with pytest.raises(ValueError):
            schedule.записать(время, путь=tmp_path / "schedule.json")

    def test_испорченный_файл_значит_не_установлено(self, tmp_path):
        файл = tmp_path / "schedule.json"
        файл.write_text("{не json", encoding="utf-8")
        assert schedule.прочитать(файл) is None

    def test_следующий_запуск_сегодня_или_завтра(self):
        расписание = {"время": "03:30", "каждые_дней": 1, "установлено": "2026-10-01T12:00:00"}
        assert schedule.следующий_запуск(расписание, datetime(2026, 10, 5, 1, 0)) == datetime(2026, 10, 5, 3, 30)
        assert schedule.следующий_запуск(расписание, datetime(2026, 10, 5, 9, 0)) == datetime(2026, 10, 6, 3, 30)

    def test_раз_в_три_дня_считается_от_установки(self):
        расписание = {"время": "03:30", "каждые_дней": 3, "установлено": "2026-10-01T12:00:00"}
        # Первый запуск — 2 октября, дальше 5-го, 8-го.
        assert schedule.следующий_запуск(расписание, datetime(2026, 10, 3, 9, 0)) == datetime(2026, 10, 5, 3, 30)

    def test_без_расписания_пропуска_нет(self, storage, tmp_path):
        с = schedule.состояние(storage, путь=tmp_path / "нет.json")
        assert с["установлено"] is False and с["пропущен"] is False

    def test_свежее_расписание_ещё_ничего_не_пропустило(self, storage, tmp_path):
        файл = tmp_path / "schedule.json"
        сейчас = datetime(2026, 10, 5, 12, 0)
        schedule.записать("03:30", путь=файл, сейчас=сейчас - timedelta(hours=1))
        assert schedule.состояние(storage, сейчас=сейчас, путь=файл)["пропущен"] is False

    def test_сбора_нет_дольше_обещанного_пропуск(self, storage, tmp_path):
        файл = tmp_path / "schedule.json"
        сейчас = datetime(2026, 10, 5, 12, 0)
        schedule.записать("03:30", путь=файл, сейчас=сейчас - timedelta(days=3))

        с = schedule.состояние(storage, сейчас=сейчас, путь=файл)

        assert с["пропущен"] is True and с["последний_сбор"] is None

    def test_вчерашний_ручной_сбор_пропуском_не_считается(self, storage, tmp_path):
        файл = tmp_path / "schedule.json"
        запуск = storage.create_parser_run(["Python"])
        storage.complete_parser_run(запуск, status="completed", vacancies_collected=3)
        сейчас = datetime.now() + timedelta(hours=20)
        schedule.записать("03:30", путь=файл, сейчас=datetime.now() - timedelta(days=5))

        с = schedule.состояние(storage, сейчас=сейчас, путь=файл)

        assert с["пропущен"] is False and с["дней_без_сбора"] == 0

    def test_о_пропуске_говорится_раз_в_сутки(self, storage, tmp_path, monkeypatch):
        import src.alerts
        import web.app.main as api

        журнал = tmp_path / "оповещения.jsonl"
        monkeypatch.setattr(schedule, "файл_расписания", lambda: tmp_path / "schedule.json")
        monkeypatch.setattr(src.alerts, "_в_телеграм", lambda *а, **к: {"доставлено": False, "настроен": False})
        schedule.записать("03:30", сейчас=datetime.now() - timedelta(days=4))

        assert api._сказать_о_пропуске(storage, журнал=журнал) is True
        assert api._сказать_о_пропуске(storage, журнал=журнал) is False, "второй перезапуск за вечер молчит"
        assert [запись["событие"]["причина"] for запись in src.alerts.последние(журнал=журнал)] == ["missed"]


class TestКопияБазы:

    def test_копия_открывается_и_содержит_данные(self, storage, tmp_path):
        storage.create_parser_run(["Python"])
        копия = schedule.копия_базы(settings.db_path, папка=tmp_path)

        assert копия is not None and копия.name.startswith("расписание_")
        conn = sqlite3.connect(копия)
        assert conn.execute("SELECT COUNT(*) FROM parser_runs").fetchone()[0] == 1
        conn.close()

    def test_хранятся_три_последние_а_чужие_файлы_целы(self, storage, tmp_path):
        чужой = tmp_path / "до_021_20260101_0000.db"
        чужой.write_bytes(b"x")
        for день in range(1, 6):
            schedule.копия_базы(settings.db_path, папка=tmp_path, сейчас=datetime(2026, 10, день, 3, 30))

        свои = sorted(файл.name for файл in tmp_path.glob("расписание_*.db"))
        assert свои == [f"расписание_202610{день:02d}_033000.db" for день in (3, 4, 5)]
        assert чужой.exists()

    def test_нет_базы_нет_копии(self, tmp_path):
        assert schedule.копия_базы(tmp_path / "нет.db", папка=tmp_path) is None
