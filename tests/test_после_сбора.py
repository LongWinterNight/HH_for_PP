"""
Шаги после сбора по расписанию и замок прогона разбора (S10‑11h, S10‑11i).

Проверяется то, на чём автоматика могла бы навредить: второй разбор не
запускается поверх идущего, брошенный упавшим прогоном замок не держит
вечно, а отказ шагов после сбора не превращается в исключение.
"""

from __future__ import annotations

import os
import subprocess
from types import SimpleNamespace

from src import after_collection, process_lock
from src.config import settings


class TestЗамок:

    def test_свой_процесс_жив_а_несуществующий_нет(self):
        assert process_lock.жив(os.getpid())
        assert not process_lock.жив(4_000_000)

    def test_захват_и_освобождение(self, tmp_path):
        замок = tmp_path / "разбор.pid"
        assert process_lock.захватить(замок)
        assert process_lock.кто_держит(замок) == os.getpid()
        process_lock.освободить(замок)
        assert not замок.exists()

    def test_брошенный_замок_забирается(self, tmp_path):
        замок = tmp_path / "разбор.pid"
        замок.write_text("4000000", encoding="utf-8")
        assert process_lock.кто_держит(замок) is None
        assert process_lock.захватить(замок)

    def test_живой_чужой_замок_не_отдаётся(self, tmp_path):
        замок = tmp_path / "разбор.pid"
        чужой = subprocess.Popen(["python", "-c", "import time; time.sleep(30)"])
        try:
            замок.write_text(str(чужой.pid), encoding="utf-8")
            assert not process_lock.захватить(замок)
        finally:
            чужой.kill()


class TestПослеСбора:

    def test_под_тестами_ничего_не_запускается(self, monkeypatch):
        """Тесты сбора проводят собрать.py до успеха — настоящие процессы им запускать нельзя."""
        monkeypatch.setattr(after_collection, "тексты", lambda *_: (_ for _ in ()).throw(AssertionError("докачка под тестами")))
        monkeypatch.setattr(after_collection, "разбор", lambda *_: (_ for _ in ()).throw(AssertionError("разбор под тестами")))
        assert after_collection.после_сбора()["пропущено"] == "под тестами"

    def test_тексты_без_копии_и_с_сетью(self, monkeypatch, tmp_path):
        monkeypatch.setattr(after_collection, "ЖУРНАЛ_ТЕКСТОВ", tmp_path / "тексты.log")
        вызов = {}

        def запуск(команда, **kw):
            вызов["команда"] = команда
            return SimpleNamespace(returncode=0)

        assert after_collection.тексты(запуск) == 0
        assert {"--yes", "--сеть", "--без-копии"} <= set(вызов["команда"]), "копию базы уже снял сбор"

    def test_отказ_докачки_не_роняет(self):
        def запуск(*_, **__):
            raise OSError("нет питона")

        assert after_collection.тексты(запуск) == 1

    def test_разбор_не_запускается_поверх_идущего(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "db_path", tmp_path / "база.db")
        (tmp_path / "разбор.pid").write_text(str(os.getpid()), encoding="utf-8")

        def запуск(*_, **__):
            raise AssertionError("второй разбор поверх идущего")

        assert after_collection.разбор(запуск) is None

    def test_разбор_запускается_в_фоне_сам_выбирая_карту(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "db_path", tmp_path / "база.db")
        monkeypatch.setattr(after_collection, "ЖУРНАЛ_РАЗБОРА", tmp_path / "разбор.log")
        вызов = {}

        def запуск(команда, **kw):
            вызов["команда"], вызов["kw"] = команда, kw
            return SimpleNamespace(pid=12345)

        assert after_collection.разбор(запуск) == 12345
        assert "--сам" in вызов["команда"], "карту или процессор прогон выбирает сам"
        assert вызов["kw"]["stdin"] is subprocess.DEVNULL


class TestОкноМодели:

    def test_сервер_модели_запускается_без_окна(self):
        """Прогон без консоли открывал серверу модели окно на каждой порции."""
        import subprocess
        import sys

        from src.ai import модели

        if sys.platform != "win32":
            assert модели.флаги_процесса(True) == 0
            return
        assert модели.флаги_процесса(False) & subprocess.CREATE_NO_WINDOW
        assert модели.флаги_процесса(True) & subprocess.CREATE_NO_WINDOW
        assert модели.флаги_процесса(True) & subprocess.BELOW_NORMAL_PRIORITY_CLASS, "в фоне — приоритет ниже обычного"
        assert not модели.флаги_процесса(False) & subprocess.BELOW_NORMAL_PRIORITY_CLASS
