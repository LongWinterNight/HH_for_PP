"""
Журнал на диске и оповещение об отказе.

Сбор лежал месяц, и об этом никто не узнал: журнала не было, а отказ
жил в памяти процесса. Здесь проверяется, что работа оставляет след в
файле, что секреты в него не попадают и что об отказе сообщается — а
если сообщить не удалось, то и это записано.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from src import alerts, journal
from src.alerts import ОБЪЯСНЕНИЯ, Отказ, последние, сообщить


@pytest.fixture
def журнал(tmp_path):
    """Журнал в отдельной папке: рабочий файл тест не трогает."""
    корень = logging.getLogger()
    прежние = [о for о in корень.handlers if getattr(о, journal._метка, False)]
    for о in прежние:
        корень.removeHandler(о)

    обработчик = journal.подключить(tmp_path / "работа.log", принудительно=True)
    yield обработчик

    корень.removeHandler(обработчик)
    обработчик.close()
    for о in прежние:
        корень.addHandler(о)


def прочитать(обработчик) -> str:
    обработчик.flush()
    return Path(обработчик.baseFilename).read_text(encoding="utf-8")


class TestЖурнал:

    def test_запись_модуля_попадает_в_файл(self, журнал):
        """Модуль о журнале не знает: он просто пишет в свой логгер."""
        logging.getLogger("src.проверка").error("сбор не удался на запросе «рендер»")
        assert "сбор не удался на запросе «рендер»" in прочитать(журнал)

    def test_в_имени_файла_стоит_дата(self, журнал):
        logging.getLogger("src.проверка").error("запись")
        журнал.flush()
        assert Path(журнал.baseFilename).name == f"работа_{date.today():%Y-%m-%d}.log"

    def test_трассировка_исключения_в_файле(self, журнал):
        try:
            raise OverflowError("Python int too large to convert to SQLite INTEGER")
        except OverflowError:
            logging.getLogger("src.проверка").exception("сбор упал")

        текст = прочитать(журнал)
        assert "Traceback" in текст and "OverflowError" in текст

    def test_повторное_подключение_не_удваивает_записи(self, журнал, tmp_path):
        assert journal.подключить(tmp_path / "другой.log", принудительно=True) is журнал
        logging.getLogger("src.проверка").error("одна запись")
        assert прочитать(журнал).count("одна запись") == 1

    def test_новый_день_новый_файл(self, журнал, tmp_path):
        """Приложение живёт неделями и не должно писать в файл дня запуска."""
        вчера = date.today() - timedelta(days=1)
        журнал._день = вчера
        журнал.baseFilename = os.fspath((tmp_path / f"работа_{вчера:%Y-%m-%d}.log").resolve())

        logging.getLogger("src.проверка").error("запись нового дня")

        assert Path(журнал.baseFilename).name == f"работа_{date.today():%Y-%m-%d}.log"
        assert "запись нового дня" in прочитать(журнал)
        assert not (tmp_path / f"работа_{вчера:%Y-%m-%d}.log").exists(), "во вчерашний файл ничего не ушло"

    def test_старые_файлы_убираются(self, tmp_path):
        старый = tmp_path / "работа_2026-01-01.log"
        свежий = tmp_path / "работа_2026-10-01.log"
        чужой = tmp_path / "оповещения.jsonl"
        for файл in (старый, свежий, чужой):
            файл.write_text("x", encoding="utf-8")
        давно = (datetime.now() - timedelta(days=journal.ХРАНИТЬ_ДНЕЙ + 5)).timestamp()
        os.utime(старый, (давно, давно))
        os.utime(чужой, (давно, давно))

        journal.ДневнойЖурнал(tmp_path / "работа.log").close()

        assert not старый.exists()
        assert свежий.exists()
        assert чужой.exists(), "уборка журнала трогает только файлы журнала"

    def test_под_тестами_рабочий_журнал_не_подключается(self):
        корень = logging.getLogger()
        прежние = [о for о in корень.handlers if getattr(о, journal._метка, False)]
        for о in прежние:
            корень.removeHandler(о)
        try:
            assert journal.подключить() is None
        finally:
            for о in прежние:
                корень.addHandler(о)


class TestСекреты:

    def test_пароль_и_токен_из_окружения_скрыты(self, журнал, monkeypatch):
        monkeypatch.setenv("BASIC_AUTH_PASSWORD", "sEcReT-пароль-стенда")
        monkeypatch.setenv("HH_ACCESS_TOKEN", "APPLTOKEN1234567890")

        logging.getLogger("src.проверка").error("вход с паролем sEcReT-пароль-стенда и ключом APPLTOKEN1234567890")

        текст = прочитать(журнал)
        assert "sEcReT-пароль-стенда" not in текст and "APPLTOKEN1234567890" not in текст
        assert "***" in текст

    def test_секрет_в_трассировке_скрыт(self, журнал, monkeypatch):
        """Секрет попадает в журнал не только сообщением, но и текстом ошибки."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABC-токен-бота")
        try:
            raise ConnectionError("https://api.telegram.org/bot123456:ABC-токен-бота/sendMessage недоступен")
        except ConnectionError:
            logging.getLogger("src.проверка").exception("канал недоступен")

        assert "123456:ABC-токен-бота" not in прочитать(журнал)

    def test_заголовок_авторизации_скрыт_чей_бы_ни_был(self):
        assert journal.скрыть("Authorization: Bearer abcdefgh12345678") == "Authorization: Bearer ***"

    def test_короткие_значения_не_скрываются(self, monkeypatch):
        """Иначе единица из DEBUG_TOKEN=1 исчезла бы из каждой строки журнала."""
        monkeypatch.setenv("DEBUG_TOKEN", "1")
        assert journal.скрыть("страница 1 из 10") == "страница 1 из 10"


class TestОповещение:

    @pytest.fixture
    def канал(self, monkeypatch):
        """Подставной канал: запоминает отправленное, в сеть не ходит."""
        отправлено = []
        monkeypatch.setattr(alerts, "КАНАЛЫ", {
            "подставной": lambda текст: отправлено.append(текст) or {"доставлено": True, "настроен": True},
        })
        return отправлено

    def test_оповещение_читается_без_журнала(self, канал, tmp_path):
        сообщить(
            Отказ(причина="token_rejected", подробности="403 Forbidden", запуск=38, запросы=["рендер"]),
            журнал=tmp_path / "оповещения.jsonl",
        )

        текст = канал[0]
        assert "Ключ доступа отклонён" in текст          # что случилось
        assert "срок действия истёк" in текст            # почему
        assert "рендер" in текст and "№38" in текст      # где
        assert текст.index("Ключ доступа отклонён") < текст.index("403 Forbidden"), "слова системы — последними"

    def test_исход_записан_в_журнал_оповещений(self, канал, tmp_path):
        файл = tmp_path / "оповещения.jsonl"
        сообщить(Отказ(причина="network", запуск=7), журнал=файл)

        запись = json.loads(файл.read_text(encoding="utf-8").splitlines()[0])
        assert запись["доставлено"] is True
        assert запись["событие"]["заголовок"] == "Источник недоступен"
        assert запись["каналы"]["подставной"]["доставлено"] is True

    def test_отказ_канала_не_роняет_и_не_теряется(self, monkeypatch, tmp_path):
        def упасть(текст):
            raise ConnectionError("https://api.telegram.org/botСЕКРЕТ/sendMessage")

        monkeypatch.setattr(alerts, "КАНАЛЫ", {"telegram": упасть})
        файл = tmp_path / "оповещения.jsonl"

        запись = сообщить(Отказ(причина="unknown"), журнал=файл)

        assert запись["доставлено"] is False
        assert "ConnectionError" in запись["каналы"]["telegram"]["почему"]
        assert "СЕКРЕТ" not in файл.read_text(encoding="utf-8"), "адрес с токеном в журнал не попадает"

    def test_ненастроенный_канал_назван_а_не_пропущен(self, monkeypatch, tmp_path):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        запись = сообщить(Отказ(причина="unknown"), журнал=tmp_path / "оповещения.jsonl")

        assert запись["каналы"]["telegram"] == {
            "доставлено": False, "настроен": False,
            "почему": "не заданы TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в .env",
        }

    def test_телеграм_получает_текст_и_чат(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABCDEF")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
        вызовы = []

        class Ответ:
            status_code = 200

        monkeypatch.setattr(alerts.requests, "post", lambda url, **кв: вызовы.append((url, кв)) or Ответ())

        запись = сообщить(Отказ(причина="network"), журнал=tmp_path / "оповещения.jsonl")

        url, кв = вызовы[0]
        assert url == "https://api.telegram.org/bot123456:ABCDEF/sendMessage"
        assert кв["json"]["chat_id"] == "42" and "Источник недоступен" in кв["json"]["text"]
        assert кв["timeout"] == alerts.ОЖИДАНИЕ_КАНАЛА
        assert запись["доставлено"] is True

    def test_отказ_телеграма_назван_словами_канала(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABCDEF")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

        class Ответ:
            status_code = 400

            @staticmethod
            def json():
                return {"ok": False, "description": "Bad Request: chat not found"}

        monkeypatch.setattr(alerts.requests, "post", lambda url, **кв: Ответ())

        запись = сообщить(Отказ(причина="network"), журнал=tmp_path / "оповещения.jsonl")

        assert запись["каналы"]["telegram"]["почему"] == "канал ответил 400: Bad Request: chat not found"

    def test_последние_оповещения_свежие_первыми(self, канал, tmp_path):
        файл = tmp_path / "оповещения.jsonl"
        сообщить(Отказ(причина="network", запуск=1), журнал=файл)
        сообщить(Отказ(причина="token_rejected", запуск=2), журнал=файл)
        with файл.open("a", encoding="utf-8") as поток:
            поток.write("{оборванная строка")

        assert [з["событие"]["запуск"] for з in последние(10, журнал=файл)] == [2, 1]

    def test_под_тестами_без_явного_журнала_наружу_ничего_не_уходит(self, канал):
        """Тест, уронивший сбор, не должен будить владельца сообщением."""
        запись = сообщить(Отказ(причина="unknown"))
        assert канал == [] and запись["каналы"] == {}


class TestОбъясненияНеРасходятсяСЭкраном:

    def test_заголовки_и_тексты_те_же_что_на_экране_сбора(self):
        """
        Причина отказа объясняется в двух местах: на экране сбора и в
        оповещении. Человек не должен читать про один отказ два разных
        описания — поэтому два списка сверяются.
        """
        корень = Path(__file__).resolve().parents[1]
        исходник = (корень / "frontend/src/utils/collectionErrors.js").read_text(encoding="utf-8")
        на_экране = {
            код: (заголовок, текст)
            for код, заголовок, текст in re.findall(r"(\w+): \{\s*title: '([^']+)',\s*text: '([^']+)'", исходник)
        }

        assert на_экране, "объяснения на экране не разобраны — проверка ничего не проверяет"
        for код, (заголовок, текст) in на_экране.items():
            assert ОБЪЯСНЕНИЯ[код] == {"title": заголовок, "text": текст}, код
