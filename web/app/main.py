"""
Минимальная версия веб-приложения HH.ru Analytics.
"""

from fastapi import Body, FastAPI, Query, BackgroundTasks, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
import pandas as pd

# Пути
WEB_DIR = Path(__file__).parent  # web/app
WEB_ROOT = WEB_DIR.parent  # web
PROJECT_ROOT = WEB_ROOT.parent  # hh_analytics
# Интерфейс живёт в отдельном дереве frontend/ и собирается Vite.
# Раздаётся собранный результат — исходники в продукт не попадают.
FRONTEND_DIST = WEB_ROOT.parent / "frontend" / "dist"  # frontend/dist

sys.path.insert(0, str(PROJECT_ROOT))

# Логгер
from src.copies import без_копий, размеры_групп, сколько_копий
from src.data_cache import запомнить
from src.budget import оценка
from src.выборка import Фильтры, отобрать, словами
from src.coverage import сводка_недобора
from src.salary_sanity import только_правдоподобные
from src.utils import get_logger
logger = get_logger(__name__)

# Конфиг (читает .env при импорте через load_dotenv)
from src.config import settings as _app_settings

# Путь к .env для записи
_ENV_PATH = PROJECT_ROOT / ".env"

# Приложение
app = FastAPI(title="HH.ru Analytics", version="2.0.0")


@app.on_event("startup")
def разобрать_оборвавшиеся_сборы():
    """
    Пометить сборы, чьи процессы не пережили перезапуск.

    Фоновая задача сбора умирает вместе с процессом, а запись о запуске
    остаётся со статусом «running». Без этой уборки интерфейс ждёт сбор,
    которого нет, а история копит вечно идущие запуски.
    """
    from src.storage import VacancyStorage

    # Сбои самого сервера — в тот же журнал на диске. Здесь, а не при
    # импорте: сервер настраивает свои логгеры после загрузки приложения.
    from src.journal import подключить_сервер

    подключить_сервер()

    # Модель поиска по смыслу поднимается заранее и в стороне: первый
    # поиск иначе ждал бы её загрузки несколько секунд.
    from src.search import служба as поиск

    поиск.прогреть()

    # База сверяется с моделями до первого запроса к ней: отставшая база
    # иначе скажет о себе словами `no such column` посреди работы.
    try:
        from src import schema_check

        расхождения = schema_check.проверить()
        if расхождения:
            from src.alerts import Отказ, сообщить

            сообщить(Отказ(
                причина="schema",
                подробности=schema_check.объяснение(расхождения, _app_settings.db_path),
            ))
    except Exception as e:
        logger.warning(f"Сверка базы с моделями не выполнена: {e}")

    storage = VacancyStorage()
    try:
        # Порог ноль: на старте любая запись «running» — след прошлого
        # процесса. Наш сбор ещё не начинался, а тот, что вёл запись,
        # умер вместе со своим приложением. Ждать здесь пять минут значит
        # оставить окно, в котором интерфейс ждёт мёртвый сбор.
        #
        # Ограничение: при двух экземплярах приложения на одной базе
        # старт второго пометит сбор первого прерванным. Продукт
        # рассчитан на один процесс; если экземпляров станет несколько,
        # признак принадлежности процессу нужно хранить в самой записи.
        #
        # Сбор по расписанию идёт в другом процессе и перезапуск
        # приложения переживает — он считается оборванным, только если
        # сам давно молчит.
        from src.collection_run import МОЛЧАНИЕ_ЧУЖОГО_СБОРА_МИН

        помечено = storage.mark_interrupted_runs(
            stale_after_minutes=0, foreign_stale_minutes=МОЛЧАНИЕ_ЧУЖОГО_СБОРА_МИН
        )
        if помечено:
            logger.info(f"При старте помечено прерванных сборов: {помечено}")
            # Оборванный сбор — тоже отказ, и самый тихий из всех: в
            # этот момент на экран никто не смотрит, а процесс, который
            # мог бы о нём сказать, уже умер.
            from src.alerts import Отказ, сообщить

            последний = storage.get_last_parser_run(only_successful=False) or {}
            сообщить(Отказ(
                причина="interrupted",
                подробности=f"оборвано сборов: {помечено}",
                запуск=последний.get("id"),
                запросы=последний.get("keywords") or [],
            ))
        _сказать_о_пропуске(storage)
    except Exception as e:
        # Уборка не должна мешать приложению подняться.
        logger.warning(f"Не удалось разобрать прерванные сборы: {e}")
    finally:
        storage.close()

def _сказать_о_пропуске(storage, журнал=None) -> bool:
    """
    Сообщить, что сбор по расписанию не прошёл.

    Отказ сбора шлёт оповещение сам. А сбор, который не запустился, не
    шлёт ничего: некому. Заметить его может только тот, кто знает
    расписание и смотрит на календарь, — приложение при старте.

    Об одном пропуске говорится раз в сутки: приложение перезапускается
    при каждой правке, и десять одинаковых сообщений за вечер приучили
    бы их не читать.
    """
    from src import schedule
    from src.alerts import Отказ, последние, сообщить

    состояние = schedule.состояние(storage)
    if not состояние["пропущен"]:
        return False

    сутки_назад = (datetime.now() - timedelta(days=1)).isoformat()
    for запись in последние(30, журнал=журнал):
        событие = запись.get("событие", {})
        if событие.get("причина") == "missed" and событие.get("когда", "") > сутки_назад:
            return False

    сообщить(Отказ(
        причина="missed",
        подробности=(
            f"последний удачный сбор: {состояние['последний_сбор'] or 'не было'}; "
            f"расписание: раз в {состояние['каждые_дней']} дн. в {состояние['время']}"
        ),
    ), журнал=журнал)
    return True


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Статика собранного интерфейса. Имена файлов в сборке содержат хеш
# содержимого, поэтому их можно кешировать надолго — в отличие от
# index.html, который отдаётся ниже и меняется при каждом развёртывании.
class ФайлыСОтпечатком(StaticFiles):
    """
    Файлы сборки, которые браузер вправе хранить год и не переспрашивать.

    В имени каждого файла — отпечаток его содержимого: изменился файл —
    изменилось имя, и по старому адресу ничего другого не появится. Без
    срока хранения браузер при каждом открытии сайта спрашивал сервер о
    каждом из восьмидесяти файлов, не изменился ли он. На этой машине
    это незаметно, через интернет — основная доля ожидания.
    """

    async def get_response(self, path, scope):
        ответ = await super().get_response(path, scope)
        if ответ.status_code == 200:
            ответ.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return ответ


if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", ФайлыСОтпечатком(directory=str(FRONTEND_DIST / "assets")), name="assets")

# Настройки пользователя — инициализируем из .env при старте
def _настройки_сбора() -> dict:
    """Настройки сбора из базы, с первичными значениями из окружения."""
    from src.storage import VacancyStorage

    storage = VacancyStorage()
    try:
        return storage.get_collection_settings()
    except Exception as e:
        logger.warning(f"Не удалось прочитать настройки сбора: {e}")
        return {"email": user_settings.get("hh_user_email") or "", "request_delay": 1.0}
    finally:
        storage.close()


# Идущий сейчас сбор. Нужен, чтобы просьба об остановке дошла до него
# напрямую: сбор работает в фоновой задаче, а просьба приходит из
# обработчика HTTP.
active_collector = None

user_settings = {
    "hh_user_email": _app_settings.hh_user_email or None,
}

# Сколько последних вакансий держит лента «только что найдено».
parser_state = {
    "is_running": False,
    "status": "idle",
    "progress": 0,
    "current_keyword": "",
    "current_page": 0,
    "total_pages": 0,
    "vacancies_collected": 0,
    "keywords": [],
    "error_message": None,
    "started_at": None,
    "completed_at": None,
    "stop_requested": False  # Флаг для остановки
}

# =============================================================================
# Доступ по логину и паролю
#
# У продукта нет слоя аккаунтов: ни пользователей, ни сессий. Пока его
# нет, а приложение выставлено наружу, единственная защита — одна пара
# логин/пароль на всех, кто тестирует.
#
# Защита включается наличием переменных в .env. Без них приложение
# работает как раньше: локальная разработка не должна требовать пароля,
# иначе его начнут отключать правкой кода.
#
# Что именно защищается: всё, кроме проверки здоровья. Открытым остаётся
# только /api/health — по нему туннель и мониторинг понимают, что
# приложение живо, и никаких данных он не отдаёт.
# =============================================================================

import base64
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

AUTH_USER = os.getenv("BASIC_AUTH_USER", "")
AUTH_PASSWORD = os.getenv("BASIC_AUTH_PASSWORD", "")
AUTH_ENABLED = bool(AUTH_USER and AUTH_PASSWORD)

PUBLIC_PATHS = {"/api/health"}


# Сколько неудачных входов с одного адреса допускается за окно и на
# сколько адрес после этого закрывается. Порт стенда открыт в интернет,
# и его находят за минуты: в первом же журнале — шесть чужих адресов,
# перебиравших пути вроде /mcp и /sse. Пароль из двадцати случайных
# знаков перебором не взять, но бесконечные попытки — это и нагрузка, и
# шум, за которым не видно настоящего входа.
ПОПЫТОК_ВХОДА = 10
ОКНО_ПОПЫТОК_СЕК = 600
ЗАКРЫТЬ_НА_СЕК = 900


class СчётчикНеудач:
    """
    Неудачные входы по адресам — в памяти процесса.

    В памяти, а не в базе: счёт нужен минуты, а перезапуск, который его
    обнуляет, случается реже, чем истекает окно. Число адресов
    ограничено: иначе сам счётчик стал бы способом занять память.
    """

    ПРЕДЕЛ_АДРЕСОВ = 10_000

    def __init__(self) -> None:
        self._неудачи: dict = {}   # адрес -> [времена неудач]
        self._закрыт_до: dict = {}  # адрес -> момент, до которого закрыт

    def закрыт(self, адрес: str, сейчас: float) -> int:
        """Сколько секунд адрес ещё закрыт. Ноль — открыт."""
        до = self._закрыт_до.get(адрес)
        if до is None:
            return 0
        if сейчас >= до:
            self._закрыт_до.pop(адрес, None)
            return 0
        return int(до - сейчас) + 1

    def неудача(self, адрес: str, сейчас: float) -> bool:
        """Записать неудачу. True — адрес этим исчерпал попытки и закрыт."""
        if len(self._неудачи) >= self.ПРЕДЕЛ_АДРЕСОВ and адрес not in self._неудачи:
            # Старейшие записи уходят первыми: словарь хранит порядок вставки.
            self._неудачи.pop(next(iter(self._неудачи)))
        свежие = [t for t in self._неудачи.get(адрес, []) if сейчас - t < ОКНО_ПОПЫТОК_СЕК]
        свежие.append(сейчас)
        self._неудачи[адрес] = свежие
        if len(свежие) >= ПОПЫТОК_ВХОДА:
            self._закрыт_до[адрес] = сейчас + ЗАКРЫТЬ_НА_СЕК
            self._неудачи.pop(адрес, None)
            return True
        return False

    def успех(self, адрес: str) -> None:
        self._неудачи.pop(адрес, None)


неудачи_входа = СчётчикНеудач()


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Проверка логина и пароля перед всем остальным."""

    async def dispatch(self, request, call_next):
        if not AUTH_ENABLED or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        адрес = request.client.host if request.client else "неизвестно"
        сейчас = time.monotonic()

        ждать = неудачи_входа.закрыт(адрес, сейчас)
        if ждать:
            # Закрытому адресу пароль даже не сверяется: иначе закрытие
            # ничего не стоило бы тому, кто перебирает.
            return Response(
                status_code=429,
                content="Слишком много неудачных попыток входа. Повторите позже.",
                headers={"Retry-After": str(ждать)},
            )

        header = request.headers.get("Authorization", "")

        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8")
                user, _, password = decoded.partition(":")
            except Exception:
                user = password = ""

            # Сравнение постоянного времени: обычное == подсказывает
            # длину и первые символы по времени ответа.
            user_ok = secrets.compare_digest(user, AUTH_USER)
            password_ok = secrets.compare_digest(password, AUTH_PASSWORD)

            if user_ok and password_ok:
                неудачи_входа.успех(адрес)
                return await call_next(request)

            # Неудачей считается только неверная пара. Запрос вовсе без
            # заголовка — это браузер, который ещё не спросил пароль, и
            # считать его значило бы закрывать честного человека на
            # первой же странице.
            if неудачи_входа.неудача(адрес, сейчас):
                logger.warning(
                    f"Адрес {адрес} закрыт на {ЗАКРЫТЬ_НА_СЕК // 60} мин: "
                    f"{ПОПЫТОК_ВХОДА} неудачных входов за {ОКНО_ПОПЫТОК_СЕК // 60} мин"
                )

        return Response(
            status_code=401,
            content="Требуется вход",
            headers={"WWW-Authenticate": 'Basic realm="BaseVacancy", charset="UTF-8"'},
        )


if AUTH_ENABLED:
    app.add_middleware(BasicAuthMiddleware)
    logger.info("Доступ защищён логином и паролем (BASIC_AUTH_USER задан)")
else:
    logger.warning(
        "Доступ открыт без пароля. Для публичного адреса задайте "
        "BASIC_AUTH_USER и BASIC_AUTH_PASSWORD в .env"
    )


# =============================================================================
# Занятость процесса
#
# Нужна надзорному процессу (`scripts/serve.py`), который перезапускает
# сервер при правке кода. Перезапускать вслепую нельзя: сбор данных идёт
# фоновым потоком внутри этого же процесса и живёт десятки минут, а
# пользователь на открытой странице получил бы ошибку сети на ровном
# месте. Поэтому сервер сам отвечает, занят ли он.
# =============================================================================

# Момент последнего запроса от кого-либо, кроме самого надзора. Хранится
# в памяти: писать на диск на каждый запрос — это тысячи записей за день
# ради значения, которое не нужно переживать перезапуск.
_последний_запрос = time.monotonic()

ПУТЬ_ЗАНЯТОСТИ = "/api/health/idle"


class ОтметкаАктивности(BaseHTTPMiddleware):
    """Запоминает, когда сервер в последний раз о чём-то просили."""

    async def dispatch(self, request, call_next):
        global _последний_запрос
        # Опрос самого надзора активностью не считается: иначе тишина не
        # наступит никогда и перезапуск не случится вовсе.
        if request.url.path != ПУТЬ_ЗАНЯТОСТИ:
            _последний_запрос = time.monotonic()
        return await call_next(request)


app.add_middleware(ОтметкаАктивности)

# Сжатие ответов. Добавлено последним, то есть стоит снаружи остальных
# слоёв и сжимает всё, что они отдали: справочник профессий — 146 КБ
# текста — уезжает в несколько раз меньшим. Мелкие ответы не трогаются:
# на них сжатие дороже выигрыша.
from starlette.middleware.gzip import GZipMiddleware  # noqa: E402

app.add_middleware(GZipMiddleware, minimum_size=1024)
PUBLIC_PATHS.add(ПУТЬ_ЗАНЯТОСТИ)


@app.get(ПУТЬ_ЗАНЯТОСТИ)
def занятость(request: Request):
    """
    Занят ли сервер: идёт ли сбор и давно ли его о чём-то просили.

    Отвечает только на локальные запросы. Пароль здесь неуместен —
    надзорный процесс не должен знать учётные данные, — а состояние
    сбора снаружи знать незачем.
    """
    хост = request.client.host if request.client else ""
    if хост not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(404, "Не найдено")

    from src.storage import VacancyStorage

    storage = VacancyStorage()
    try:
        активный = storage.get_active_run()
    finally:
        storage.close()

    # Память процесса и база вместе: запись в базе переживает перезапуск,
    # а флаг в памяти успевает подняться раньше, чем появится запись.
    сбор_идёт = bool(активный) or bool(parser_state.get("is_running"))

    return {
        "сбор_идёт": сбор_идёт,
        "секунд_тишины": round(time.monotonic() - _последний_запрос, 1),
    }


# =============================================================================
# Достоверность агрегатов
#
# Ниже пяти вакансий агрегат не показывается: медиана по трём выглядит
# как факт и читается как факт, не значив ничего. Тренд считается только
# сравнением с предыдущим периодом такой же длины — до этого здесь стоял
# random.uniform «для демо», и дашборд показывал выдуманные проценты
# роста, неотличимые от настоящих.
# =============================================================================

MIN_SAMPLE = 5

PERIOD_DAYS = {
    "today": 1,
    "week": 7,
    "month": 30,
    "quarter": 90,
    "year": 365,
}


def apply_vacancy_filters(df, domain=None, regions=None, experience=None, salary_only=False):
    """Фильтры среза, общие для KPI и графиков. Период применяется отдельно:
    предыдущий период фильтруется теми же условиями, но другими датами."""
    if domain:
        if "domain" in df.columns:
            df = df[df["domain"].str.contains(domain, case=False, na=False)]
        elif "profession" in df.columns:
            df = df[df["profession"].str.contains(domain, case=False, na=False)]

    if regions:
        region_list = [r.strip() for r in regions.split(",") if r.strip()]
        if region_list and "area" in df.columns:
            df = df[df["area"].str.contains("|".join(region_list), case=False, na=False)]

    if experience and "experience" in df.columns:
        df = df[df["experience"] == experience]

    if salary_only and "salary_from" in df.columns:
        df = df[df["salary_from"].notna()]

    return df


def period_windows(df, period):
    """Границы текущего и предыдущего окна одинаковой длины.

    Возвращает (current_start, current_end, previous_start) или None,
    если период не ограничен: у «всего времени» предыдущего периода нет,
    и тренд для него не существует, а не равен нулю.
    """
    days = PERIOD_DAYS.get(period)
    if not days or "published_at" not in df.columns:
        return None

    tz = df["published_at"].dt.tz if hasattr(df["published_at"], "dt") else None
    now = pd.Timestamp.now(tz=tz) if tz is not None else pd.Timestamp.now()
    start = now - pd.Timedelta(days=days)
    return start, now, start - pd.Timedelta(days=days)


def trend_reliability(df, previous_start):
    """Можно ли сравнивать текущий период с предыдущим.

    Сейчас — нельзя, и это свойство данных, а не недоделка.

    База хранит срез активных вакансий на момент сбора, а не историю
    рынка: hh.ru отдаёт только открытые вакансии, закрытые в выборку не
    попадают. Чем старше день, тем меньше его вакансий дожило до сбора.
    На реальных данных это выглядит так: 20 августа — 2 вакансии,
    3 сентября — 166. Разделив одно на другое, получаем «рост рынка
    в восемьдесят раз» вместо затухания архива.

    Раньше на этом месте стоял random.uniform «для демо» — выдуманные
    проценты, неотличимые от настоящих. Сравнение по дате публикации
    выглядит достовернее, но врёт так же уверенно, поэтому тренд не
    показывается до появления снимков метрик: сравнивать нужно два
    сбора между собой, а не два куска одного снимка.

    Возвращает причину отказа словами, которые не стыдно показать
    на экране, или None, когда сравнение станет возможным.
    """
    if "published_at" not in df.columns or df["published_at"].isna().all():
        return "у вакансий нет даты публикации"

    return (
        "база хранит срез активных вакансий на момент сбора, а не историю: "
        "сравнение периодов внутри одного снимка завышает свежие дни"
    )


def slice_period(df, start, end):
    if "published_at" not in df.columns:
        return df
    return df[(df["published_at"] >= start) & (df["published_at"] < end)]


def _курс_для_ответа():
    """Дата курса ЦБ, по которому посчитан эквивалент.

    Эквивалент без даты ничем не подтверждён: «≈ 80 000 ₽» по какому
    курсу и на когда — вопрос, на который ответ должен приезжать тем же
    ответом, что и число.
    """
    from src.storage import VacancyStorage

    storage = VacancyStorage()
    try:
        курсы = storage.get_currency_rates()
    except Exception as e:
        logger.warning(f"Не удалось прочитать курсы: {e}")
        return None
    finally:
        storage.close()

    return курсы.на_дату.isoformat() if курсы else None


def _тренды_по_снимкам() -> dict:
    """
    Тренды из точек истории: разница между двумя последними снимками.

    Возвращает только те метрики, по которым обе точки заполнены. У
    восстановленных снимков нет зарплатных метрик — в базе лежит
    последнее известное значение зарплаты, а не историческое, — поэтому
    зарплатный тренд по ним не строится.
    """
    from src.storage import VacancyStorage

    storage = VacancyStorage()
    try:
        точки = storage.get_metrics_snapshots(limit=2)
    except Exception as e:
        logger.warning(f"Не удалось прочитать снимки метрик: {e}")
        return {}
    finally:
        storage.close()

    if len(точки) < 2:
        return {}

    новая, прежняя = точки[0], точки[1]

    # Зарплатный тренд считается по исходной валюте — по медиане
    # рублёвых вакансий, а не по рублёвому эквиваленту всей выборки.
    #
    # Эквивалент пересчитывается по курсу дня, и разница двух снимков
    # смешала бы два движения: рынок и курс. Если рубль за месяц упал на
    # десять процентов, эквивалент сумовых зарплат вырастет на те же
    # десять — и график покажет рост зарплат там, где выросла только
    # цена валюты. Пока снимок не хранит курс своего дня (К4‑4), тренда
    # по эквиваленту быть не может; когда начнёт — считать его надо
    # курсом того снимка, а не сегодняшним.
    соответствие = {
        "total_vacancies": "active_vacancies",
        "unique_companies": "unique_companies",
        "unique_regions": "unique_regions",
        "median_salary": "median_salary_rub",
    }

    тренды = {}
    for метрика, поле in соответствие.items():
        сейчас, было = новая.get(поле), прежняя.get(поле)
        if сейчас is None or было is None:
            continue
        тренды[метрика] = trend_of(сейчас, было)

    return тренды


def collect_kpi_values(df):
    """Значения метрик без трендов.

    Средней здесь нет и не будет. Одна вакансия на 800 000 сдвигает её
    так, что число перестаёт описывать рынок, — поэтому она не считается
    и не попадает в ответ ни одного эндпоинта. Зарплату описывают медиана
    и квартили. Рядом с зарплатными метриками всегда идёт объём выборки:
    без n надёжность числа оценить нельзя."""
    salary_df = только_правдоподобные(df) if "salary_from" in df.columns else pd.DataFrame()

    # Зарплатных метрик две, и складывать их в одну нельзя.
    #
    # `median_salary` — по вакансиям в рублях. Раньше она считалась по
    # всем валютам разом: 6 000 000 сум входили в неё числом 6 000 000,
    # и плитка «Медиана зарплаты · RUB» показывала 90 000 там, где по
    # рублёвым вакансиям было 82 000. Подпись называла валюту, которой
    # число не соответствовало.
    #
    # `median_salary_rub` — по рублёвому эквиваленту всей выборки: он
    # приводит семь валют к общему знаменателю по курсу ЦБ на дату
    # сбора, и только он описывает базу целиком.
    # Копии одной вакансии по городам схлопываются: работодатель
    # размещает её в десятках городов, и в медиане она весила как
    # тридцать. На живой базе это давало 81 500 вместо 90 000 (S5).
    рублёвые = (salary_df[salary_df["salary_currency"] == "RUB"]
                if "salary_currency" in salary_df.columns else salary_df)
    рублёвые = без_копий(рублёвые, "salary_from")
    salary_n = len(рублёвые)
    enough = salary_n >= MIN_SAMPLE

    эквивалент = (без_копий(salary_df, "salary_from_rub")["salary_from_rub"].dropna()
                  if "salary_from_rub" in salary_df.columns else pd.Series(dtype=float))
    эквивалент_n = len(эквивалент)
    эквивалент_хватает = эквивалент_n >= MIN_SAMPLE

    hard_skills_set = set()
    if "hard_skills" in df.columns:
        for skills_str in df["hard_skills"].dropna():
            if isinstance(skills_str, str):
                hard_skills_set.update(s.strip() for s in skills_str.split(",") if s.strip())

    soft_skills_set = set()
    if "soft_skills" in df.columns:
        for skills_str in df["soft_skills"].dropna():
            if isinstance(skills_str, str):
                soft_skills_set.update(s.strip() for s in skills_str.split(",") if s.strip())

    return {
        "median_salary": float(рублёвые["salary_from"].median()) if enough else None,
        "salary_sample": salary_n,
        "median_salary_rub": float(эквивалент.median()) if эквивалент_хватает else None,
        "salary_sample_rub": эквивалент_n,
        "total_vacancies": len(df),
        "total_skills": int(df["skill_count"].sum()) if "skill_count" in df.columns else 0,
        "unique_companies": int(df["employer_name"].nunique()) if "employer_name" in df.columns else 0,
        "unique_regions": int(df["area"].nunique()) if "area" in df.columns else 0,
        "hard_skills_count": len(hard_skills_set),
        "soft_skills_count": len(soft_skills_set),
    }


def trend_of(current, previous):
    """Процент изменения к предыдущему периоду.

    Возвращает пустой тренд, если сравнивать не с чем: отсутствие тренда
    честнее нуля, потому что ноль означает «не изменилось».
    """
    if current is None or previous is None or not previous:
        return {"trend_percent": None, "trend_direction": None}

    change = (current - previous) / previous * 100
    direction = "up" if change > 0 else "down" if change < 0 else "same"
    return {"trend_percent": round(abs(change), 1), "trend_direction": direction}


# Корзины зарплат и короткие подписи оси живут в `src/salary_slice.py`:
# ими пользуется и этот файл, и срез зарплат окна аналитики, а расчёт,
# лежащий в обработчике запроса, без веб-сервера не проверить.
from src.salary_slice import format_short, salary_histogram  # noqa: E402,F401


# =============================================================================
# Endpoints
# =============================================================================

def index_response():
    """Точка входа интерфейса.

    Если сборки нет, честно говорим, что делать: пустая страница или
    500 заставили бы искать причину в бэкенде, которого она не касается.
    """
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        # Страница, в отличие от файлов сборки, имени не меняет: её
        # браузер обязан перепроверять, иначе после пересборки он
        # открывал бы старую страницу со ссылками на файлы, которых нет.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    from fastapi.responses import HTMLResponse
    return HTMLResponse(
        "<h1>Интерфейс не собран</h1>"
        "<p>Выполните <code>npm install &amp;&amp; npm run build</code> в папке <code>frontend/</code>.</p>",
        status_code=503
    )


@app.get("/")
def root():
    return index_response()

@app.get("/favicon.ico")
def favicon():
    """Возвращает favicon.ico или заглушку."""
    favicon_path = FRONTEND_DIST / "favicon.svg"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/svg+xml")
    # Возвращаем пустую заглушку если favicon нет
    from fastapi.responses import Response
    return Response(content="", status_code=204)

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
def chrome_devtools():
    """Заглушка для Chrome DevTools."""
    from fastapi.responses import JSONResponse
    return JSONResponse(content={})

@app.get("/analytics")
def analytics_page():
    """Аналитика — маршрут внутри интерфейса, а не отдельная страница."""
    return index_response()

@app.get("/api/health")
def health():
    return {"status": "ok"}

def _исход_последнего_запуска(storage) -> Optional[dict]:
    """Последний запуск сбора коротко: исход, причина, время."""
    запуск = storage.get_last_parser_run(only_successful=False)
    if not запуск:
        return None

    не_удался = запуск["status"] in ("error", "interrupted")
    причина = запуск.get("error_type") or ("interrupted" if запуск["status"] == "interrupted" else "unknown")
    итог = {
        "id": запуск["id"],
        "status": запуск["status"],
        "failed": не_удался,
        "finished_at": запуск["completed_at"] or запуск["started_at"],
    }
    if не_удался:
        from src.alerts import ОБЪЯСНЕНИЯ

        объяснение = ОБЪЯСНЕНИЯ.get(причина, ОБЪЯСНЕНИЯ["unknown"])
        итог.update({"reason": причина, "title": объяснение["title"], "text": объяснение["text"]})
    return итог


# =============================================================================
# Слой понимания текста: состояние и кандидаты в словарь
#
# Модель здесь не вызывается: она работает офлайн, прогоном по базе.
# Экран показывает, что прогон нашёл, и принимает решение человека.
# =============================================================================

def _замеры_навыков() -> dict:
    """Последние замеры извлечения — из файла, который пишет сам замер."""
    файл = Path(_app_settings.db_path).parent / "замер_навыков.json"
    if not файл.exists():
        return {}
    try:
        return json.loads(файл.read_text(encoding="utf-8")).get("замеры", {})
    except (OSError, ValueError):
        return {}


@app.get("/api/ai/state")
def состояние_слоя():
    """
    Слой понимания текста одним ответом: включён ли, чем разбирает,
    сколько вакансий ждёт, сколько кандидатов накоплено и что показал
    замер. Качество не прячется в журнале.
    """
    import sqlite3

    from src import ai
    from src.ai import кандидаты, кэш, модели, прогон

    итог = {"включён": ai.включён(), "порог_работодателей": кандидаты.ПОРОГ_РАБОТОДАТЕЛЕЙ, "замеры": _замеры_навыков()}
    try:
        кандидат = модели.выбранный()
        версия = f"{кандидат.версия(модели.версия_рантайма(кандидат))}|{прогон.ВЕРСИЯ_ПРОМПТА}"
        итог.update({"модель": кандидат.имя, "описание_модели": кандидат.описание, "версия": версия})
    except KeyError as e:
        итог.update({"модель": None, "версия": "", "ошибка_настройки": str(e)})
        return итог

    conn = sqlite3.connect(f"file:{_app_settings.db_path}?mode=ro", uri=True)
    try:
        итог["в_очереди"] = прогон.сколько_ждёт(conn, версия)
        итог["разобрано"] = conn.execute(
            "SELECT COUNT(*) FROM vacancies WHERE COALESCE(ai_version, '') != ''").fetchone()[0]
        итог["кандидаты"] = кандидаты.сводка(conn)
        итог["траты"] = кэш.траты(conn)
    except sqlite3.OperationalError as e:
        итог["ошибка_базы"] = str(e)
    finally:
        conn.close()
    return итог


@app.get("/api/ai/candidates")
def кандидаты_в_словарь(status: str = "new", limit: int = Query(100, ge=1, le=500)):
    """
    Кандидаты в словарь навыков: название, число встреч, число разных
    работодателей и цитаты, из которых кандидат получен. Новые
    показываются от порога в три работодателя — опечатка одного
    объявления до человека не доходит.
    """
    import sqlite3

    from src.ai import кандидаты

    if status not in (кандидаты.НОВЫЙ, кандидаты.ПОДТВЕРЖДЁН, кандидаты.ОТКЛОНЁН):
        raise HTTPException(400, "Состояние кандидата: new, confirmed или rejected")
    conn = sqlite3.connect(f"file:{_app_settings.db_path}?mode=ro", uri=True)
    try:
        return {"кандидаты": кандидаты.список(conn, статус=status, предел=limit), "сводка": кандидаты.сводка(conn)}
    except sqlite3.OperationalError:
        return {"кандидаты": [], "сводка": {"новых": 0, "ждут_решения": 0, "подтверждено": 0, "отклонено": 0}}
    finally:
        conn.close()


@app.post("/api/ai/candidates/decide")
def решить_кандидата(payload: dict = Body(...)):
    """
    Решение человека по кандидату: подтвердить (навык уходит в словарь и
    дальше находится без модели) или отклонить (больше не предлагается).
    """
    import sqlite3

    from src.ai import кандидаты

    имя = str(payload.get("ключ") or "").strip()
    решение = payload.get("решение")
    if not имя or решение not in ("confirm", "reject"):
        raise HTTPException(400, "Нужны ключ кандидата и решение: confirm или reject")

    conn = sqlite3.connect(_app_settings.db_path, timeout=30)
    try:
        if решение == "reject":
            принято = кандидаты.отклонить(conn, имя)
        else:
            try:
                принято = кандидаты.подтвердить(
                    conn, имя,
                    раздел=(payload.get("раздел") or None),
                    название=(str(payload.get("название") or "").strip() or None),
                )
            except ValueError as e:
                raise HTTPException(400, str(e))
        if not принято:
            raise HTTPException(404, "Такого кандидата нет")
        conn.commit()
        if решение == "confirm":
            # Подсказки поиска собраны по прежнему словарю.
            try:
                from src.search import служба as поиск

                getattr(поиск, "сбросить_словарь", lambda: None)()
            except Exception:
                pass
        return {"принято": True, "сводка": кандидаты.сводка(conn)}
    finally:
        conn.close()


@app.get("/api/system/state")
def состояние_систем():
    """
    Что происходит в продукте прямо сейчас: сбор, разбор, база, поиск,
    журнал и оповещения — живыми числами. Экран «Как устроено» рисует по
    ним схему; без них схема была бы картинкой устройства, которого нет.
    """
    from src.system_state import собрать

    return собрать()


@app.get("/api/system/story")
def главы_устройства():
    """
    Данные для глав экрана «Как устроено»: одна настоящая вакансия и то,
    что система делает с ней и со всей базой на каждом шаге.
    """
    from src.system_story import собрать

    return {
        **собрать(),
        # Пороги входа отдаются отсюда, где они действуют: переписанные
        # в текст экрана, они разошлись бы с кодом при первой правке.
        "защита": {
            "вход_по_паролю": AUTH_ENABLED,
            "неудач": ПОПЫТОК_ВХОДА,
            "окно_минут": ОКНО_ПОПЫТОК_СЕК // 60,
            "закрыт_минут": ЗАКРЫТЬ_НА_СЕК // 60,
        },
    }


@app.get("/api/search/explain")
def объяснить_поиск(q: str = Query(..., min_length=1, max_length=200)):
    """
    Поиск по шагам: как разобран запрос, что нашли слова, что нашёл
    смысл и как списки слились. Считает тот же код, что ищет на экране
    «Вакансии».
    """
    from src.search import служба

    шаги = служба.объяснить(q.strip())
    if шаги is None:
        raise HTTPException(404, "Индексы поиска не построены. Запустите python scripts/построить_поиск.py")
    return шаги


@app.get("/api/overview")
def получить_состояние_базы():
    """
    Сколько вакансий в базе и когда собирали в последний раз.

    Отдельно от «/api/dashboard»: тот считает спарклайны за две недели и
    топ навыков, а шапка стоит на всех шести экранах и запрашивает это
    при каждом переходе. Здесь два счётчика — COUNT и одна строка
    журнала запусков, без чтения базы в pandas.
    """
    from src.storage import VacancyStorage

    storage = VacancyStorage()
    try:
        последний = storage.get_last_parser_run(only_successful=True)
        сводка = storage.get_active_summary()
        return {
            "vacancies": storage.get_vacancy_count(),
            # Активные и найденные по запросу — то, по чему считаются
            # графики, — и их счёт по валютам. Экраны берут эти числа
            # отсюда, а не из расчёта дашборда.
            "active": сводка["active"],
            "currencies": сводка["currencies"],
            # Сколько вакансий скрыто как найденные не по запросу. Число
            # названо, чтобы скрытое не выглядело потерянным.
            "off_query": storage.get_off_query_count(),
            "last_collected_at": последний["completed_at"] if последний else None,
            # Чем кончился самый последний запуск, удачный или нет.
            # Из базы, а не из памяти процесса: отказ должен быть виден
            # и после перезапуска, и тому, кто не открывал экран сбора.
            "last_run": _исход_последнего_запуска(storage),
        }
    finally:
        storage.close()


@app.get("/api/vacancies")
def get_vacancies(
    page: int = 1,
    per_page: int = 20,
    search: str = "",
    area: str = "",
    experience: str = "",
    skill: str = "",
    salary_only: bool = False,
    currency: str = "",
    sort_by: str = "salary",  # salary | date | none
    sort_order: str = "desc",  # asc | desc
    include_inactive: bool = False,
    source: str = ""
):
    from src.storage import VacancyStorage
    import pandas as pd

    storage = VacancyStorage()
    try:
        # Снятые с публикации вакансии по умолчанию не показываются:
        # список описывает текущий рынок. Архив доступен явным
        # include_inactive — он нужен истории, а не работе с выборкой.
        df = storage.get_all_vacancies(include_inactive=include_inactive)
        if df.empty:
            return {"total": 0, "page": page, "items": [], "источники": {}}

        # Какие источники есть в базе — считается до фильтров: иначе
        # выбор источника исчезал бы, стоило его применить.
        источники = {}
        if "source" in df.columns:
            источники = {
                str(имя): int(сколько)
                for имя, сколько in df["source"].value_counts().items()
            }

        # Отбор — общей функцией, той же, по которой собирается отчёт.
        # Держать здесь свою копию условий значило бы получить экран и
        # файл, показывающие разные числа по одному и тому же фильтру.
        #
        # Про источник: пока он один, фильтр на экране не показывается —
        # но параметр есть, чтобы ссылка на срез по источнику работала с
        # первого дня второго. Про валюту: она сужает выборку до одного
        # рынка, а порядок между валютами держит рублёвый эквивалент по
        # курсу ЦБ (К1, К2).
        df = отобрать(df, Фильтры(
            поиск=search, регион=area, опыт=experience, навык=skill,
            валюта=currency, источник=source,
            только_с_зарплатой=salary_only, включая_снятые=include_inactive,
        ))

        # Что поиск сделал с запросом: исправил опечатку, ослабил
        # условие, искал ли по смыслу. Читается сразу после отбора —
        # сортировка эти сведения сохранять не обязана.
        сведения_поиска = dict(df.attrs.get("поиск") or {})

        # Сортировка
        if sort_by == "relevance" and "search_rank" in df.columns:
            # По соответствию запросу: порядок, в котором вакансии
            # выдал поиск. Без запроса такой колонки нет, и список
            # остаётся в порядке базы — как при sort_by=none.
            df = df.sort_values(by="search_rank")
        elif sort_by == "salary" and "salary_from" in df.columns:
            # По чему сравнивать суммы, решает выбранная валюта.
            #
            # Валюта выбрана — рынок один, и сравнивать надо исходные
            # суммы: эквивалент пересчитан по курсу и округлён, внутри
            # одной валюты он только теряет точность.
            #
            # Валюты нет — в списке лежат рубли, сумы и тенге вперемешку,
            # и сравнивать их номиналы бессмысленно: 19 000 000 сум
            # всегда оказались бы выше 300 000 рублей. Общий знаменатель
            # даёт рублёвый эквивалент по курсу ЦБ.
            по_эквиваленту = not currency and "salary_from_rub" in df.columns
            колонка = "salary_from_rub" if по_эквиваленту else "salary_from"

            # na_position="last" при любом порядке: запись без суммы (или
            # без эквивалента — валюты, которой нет в курсах ЦБ) уходит в
            # конец. При возрастании она иначе встала бы первой и читалась
            # бы как самая дешёвая, хотя про неё просто ничего не известно.
            df = df.sort_values(
                by=[колонка, "published_at"],
                ascending=[sort_order == "asc", False],  # ЗП по порядку, дата всегда по убыванию
                na_position="last"
            )
        elif sort_by == "date" and "published_at" in df.columns:
            # Сортировка только по дате
            df = df.sort_values(
                by="published_at",
                ascending=sort_order == "asc",
                na_position="last"
            )
        # else: sort_by == "none" — без сортировки, порядок из БД

        total = len(df)
        start = (page - 1) * per_page
        df_page = df.iloc[start:start + per_page]

        # Сколько объявлений у этой же вакансии в других городах.
        #
        # Работодатель размещает одну вакансию в десятках городов, и в
        # списке она занимает десятки строк. Скрывать их нельзя —
        # человеку, который ищет работу в Самаре, нужна именно его
        # строка, — но сказать, что строка не одинока, стоит: иначе
        # список выглядит как повтор одного и того же по ошибке.
        размеры = размеры_групп(df)

        from src import ai

        слой_включён = ai.включён()

        items = []
        for _, row in df_page.iterrows():
            item = {}
            for col in df.columns:
                val = row.get(col)
                if pd.isna(val):
                    val = None
                elif hasattr(val, 'isoformat'):
                    val = str(val)
                else:
                    val = val
                item[col] = val
            # Навыки модели уходят на экран разобранными и только при
            # включённом слое: выключение должно выключать и показ.
            найденное = item.pop("ai_skills", None)
            if слой_включён and найденное:
                try:
                    item["ai_skills"] = json.loads(найденное)
                except (TypeError, ValueError):
                    pass
            if not слой_включён:
                item.pop("ai_version", None)
            if not размеры.empty:
                ключ = (row.get("vacancy_name"), row.get("employer_name"))
                item["копий"] = int(размеры.get(ключ, 1))

            items.append(item)

        # Дата курса отдаётся вместе с данными, а не отдельным запросом:
        # эквивалент без даты ничем не подтверждён, и подпись должна
        # приезжать тем же ответом, что и числа, которые она объясняет.
        курсы = storage.get_currency_rates()

        # Источники посчитаны выше, до фильтров: экран по этому числу
        # решает, показывать ли выбор источника. Один источник — фильтр
        # без выбора, лишний элемент на экране.
        return {
            "total": total,
            "page": page,
            "items": items,
            "источники": источники,
            "rate_date": курсы.на_дату.isoformat() if курсы else None,
            # Замены в запросе, ослабление условия и способы поиска.
            # Пусто, когда поиска не было или он шёл по-старому.
            "поиск": сведения_поиска,
        }
    finally:
        storage.close()

@app.get("/api/dashboard")
@запомнить
def get_dashboard():
    """Дашборд с расширенной статистикой."""
    from src.storage import VacancyStorage
    import pandas as pd
    import math

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        if df.empty:
            return {
                "total_vacancies": 0,
                "total_skills": 0,
                "recent_vacancies": [],
                "top_skills": [],
                "vacancies_by_currency": {},
                "vacancies_by_area": {},
            }

        def get_top_skills(column, limit=10):
            counts = {}
            for s in column.dropna():
                if isinstance(s, str):
                    for skill in s.split(","):
                        skill = skill.strip()
                        if skill:
                            counts[skill] = counts.get(skill, 0) + 1
            return [{"name": k, "value": v} for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]]

        def safe_value(val):
            """Преобразует NaN/None в None для JSON-сериализации."""
            if val is None:
                return None
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                return None
            return val

        top_skills = get_top_skills(df["hard_skills"], 10) if "hard_skills" in df.columns else []

        # Недавние вакансии с валютами
        recent = df.sort_values(by="published_at", ascending=False).head(5) if "published_at" in df.columns else df.head(5)
        recent_vacancies = []
        for _, row in recent.iterrows():
            recent_vacancies.append({
                "name": str(row.get("vacancy_name", ""))[:50] if pd.notna(row.get("vacancy_name")) else "",
                "company": str(row.get("employer_name", ""))[:30] if pd.notna(row.get("employer_name")) else "",
                "area": str(row.get("area", "")) if pd.notna(row.get("area")) else "",
                "salary": safe_value(row.get("salary_from")),
                "currency": row.get("salary_currency", "RUB") if pd.notna(row.get("salary_currency")) else "RUB"
            })

        # Статистика по зарплате
        salary_df = только_правдоподобные(df) if "salary_from" in df.columns else pd.DataFrame()

        # Распределение по валютам
        vacancies_by_currency = {}
        if "salary_currency" in df.columns:
            currency_counts = df["salary_currency"].value_counts().to_dict()
            for currency, count in currency_counts.items():
                curr_df = без_копий(
                    только_правдоподобные(df[df["salary_currency"] == currency]),
                    "salary_from",
                )
                # Медиана и объём выборки — то, что показывается на экране.
                # Средней в ответе нет: её тянут выбросы, и одна вакансия
                # на 600 000 сдвигает число так, что оно перестаёт
                # описывать рынок.
                salary_n = len(curr_df)
                if salary_n:
                    enough = salary_n >= MIN_SAMPLE
                    salaries = curr_df["salary_from"]
                    vacancies_by_currency[currency] = {
                        "count": int(count),
                        "sample": salary_n,
                        "median_salary": float(salaries.median()) if enough else None,
                        # Квартили вместо крайних значений. В объявлениях
                        # попадаются «50 ₽» и «400 сум» — оператор ошибся
                        # разрядом, а минимум показывает эту опечатку как
                        # границу рынка. Между Q1 и Q3 лежит половина
                        # вакансий, и одна ошибка её не сдвигает.
                        "q1_salary": float(salaries.quantile(0.25)) if enough else None,
                        "q3_salary": float(salaries.quantile(0.75)) if enough else None,
                        "min_salary": float(salaries.min()) if enough else None,
                        "max_salary": float(salaries.max()) if enough else None,
                    }

        # Топ регионов
        vacancies_by_area = {}
        if "area" in df.columns:
            vacancies_by_area = df["area"].value_counts().head(5).to_dict()

        # Динамики зарплат здесь нет намеренно.
        #
        # Недельный ряд считался средней и складывал все валюты в одно
        # число: 6 000 000 сум и 350 000 тенге ложились в ту же точку,
        # что и рубли. Медиана по такой смеси врёт не меньше средней,
        # поэтому ряд удалён, а не исправлен. Динамику зарплат строит
        # экран аналитики (E4): помесячная медиана внутри одной валюты,
        # с объёмом выборки и пометкой при выборке меньше пяти.

        # Sparklines данные для KPI карточек
        # Вакансии по дням (последние 14 дней)
        vacancies_sparkline = []
        if "published_at" in df.columns and "created_at" in df.columns:
            df_with_dates = df[df["published_at"].notna()].copy()
            if not df_with_dates.empty:
                df_with_dates["published_at"] = pd.to_datetime(df_with_dates["published_at"])
                df_with_dates["published_at"] = df_with_dates["published_at"].dt.tz_localize(None)
                daily_counts = df_with_dates.groupby(df_with_dates["published_at"].dt.date).size()
                last_14_days = pd.date_range(end=pd.Timestamp.now(), periods=14, freq='D')
                for day in last_14_days:
                    date_only = day.date()
                    count = int(daily_counts.get(date_only, 0))
                    vacancies_sparkline.append(count)

        # Навыки по дням (последние 14 дней)
        skills_sparkline = []
        if "published_at" in df.columns and "skill_count" in df.columns:
            df_with_dates = df[df["published_at"].notna() & df["skill_count"].notna()].copy()
            if not df_with_dates.empty:
                df_with_dates["published_at"] = pd.to_datetime(df_with_dates["published_at"])
                df_with_dates["published_at"] = df_with_dates["published_at"].dt.tz_localize(None)
                daily_skills = df_with_dates.groupby(df_with_dates["published_at"].dt.date)["skill_count"].sum()
                last_14_days = pd.date_range(end=pd.Timestamp.now(), periods=14, freq='D')
                for day in last_14_days:
                    date_only = day.date()
                    count = int(daily_skills.get(date_only, 0))
                    skills_sparkline.append(count)

        return {
            "total_vacancies": len(df),
            "total_skills": int(df["skill_count"].sum()) if "skill_count" in df.columns and pd.notna(df["skill_count"].sum()) else 0,
            "recent_vacancies": recent_vacancies,
            "top_skills": top_skills,
            "vacancies_by_currency": vacancies_by_currency,
            "vacancies_by_area": vacancies_by_area,
            "sparklines": {
                "vacancies": vacancies_sparkline,
                "skills": skills_sparkline
            },
            "last_updated": storage.get_last_parser_run(only_successful=True)["completed_at"] if storage.get_last_parser_run(only_successful=True) else None
        }
    finally:
        storage.close()

@app.get("/api/analytics/advanced")
@запомнить
def get_analytics():
    """Расширенная аналитика + распределение."""
    from src.storage import VacancyStorage
    from src.advanced_analyzer import AdvancedAnalytics
    import pandas as pd

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        if df.empty:
            return {
                "technologies": {},
                "hard_skills": {},
                "soft_skills": {},
                "salary_stats": {},
                "total_vacancies": 0
            }

        analytics = AdvancedAnalytics(df)

        # Получаем упрощенные данные по навыкам (только названия и количество)
        tech_summary = analytics.compute_technology_summary()
        hard_summary = analytics.compute_hard_skills_summary()
        soft_summary = analytics.compute_soft_skills_summary()

        # Преобразуем в простой формат {навык: количество}
        def simplify_skills(data):
            if not data:
                return {}
            result = {}
            for key, value in data.items():
                if isinstance(value, dict):
                    # Если это группа с count
                    result[key] = value.get("count", 0)
                else:
                    # Если это просто число
                    result[key] = value
            return result

        # Статистика по зарплате
        salary_stats = {}
        if "salary_from" in df.columns:
            salary_df = без_копий(только_правдоподобные(df), "salary_from")
            if not salary_df.empty:
                salary_stats = {
                    "min": float(salary_df["salary_from"].min()),
                    "max": float(salary_df["salary_from"].max()),
                    "median": float(salary_df["salary_from"].median()),
                }

        return {
            "technologies": simplify_skills(tech_summary),
            "hard_skills": simplify_skills(hard_summary),
            "soft_skills": simplify_skills(soft_summary),
            "salary_stats": salary_stats,
            "total_vacancies": len(df)
        }
    finally:
        storage.close()

@app.get("/api/analytics/distribution")
@запомнить
def get_distribution(currency: str = "RUB"):
    """Распределение вакансий по категориям.

    Зарплатные графики строятся внутри одной валюты. Раньше здесь стояла
    конвертация по захардкоженным курсам (USD = 92 руб), из-за которой
    «распределение зарплат» смешивало рубли, сумы и тенге, а точность
    выглядела настоящей, хотя курс на дату сбора неизвестен.
    """
    from src.storage import VacancyStorage
    import pandas as pd

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        if df.empty:
            return {
                "experience": {},
                "employment": {},
                "salary_distribution": {},
                "salary_stats": {},
                "salary_stats_kzt": {},
                "salary_stats_usd": {},
                "currencies": {}
            }

        # Распределение по опыту
        experience_counts = {}
        if "experience" in df.columns:
            experience_counts = df["experience"].value_counts().to_dict()

        # Распределение по занятости
        employment_counts = {}
        if "employment" in df.columns:
            employment_counts = df["employment"].value_counts().to_dict()

        # Зашитых курсов здесь нет и быть не должно.
        #
        # Раньше на этом месте лежал словарь «примерных» курсов: доллар
        # по 92 при настоящих 86,47, сум по 0,0072 при 0,00733485, а
        # неизвестной валюте молча ставился курс 1.0 — сом считался бы
        # рублём. Словарь выглядел рабочим, и следующий, кому понадобился
        # бы рублёвый вид, взял бы готовое. Пересчёт живёт в
        # `src/cbr_rates.py` и делается по курсу ЦБ на дату сбора:
        # эквивалент лежит в `salary_from_rub` вместе с `rate_date`,
        # которая его подтверждает.

        # Распределение зарплат внутри выбранной валюты, без пересчёта.
        currency_df = df[df["salary_currency"] == currency] if "salary_currency" in df.columns else df
        # Без сомнительных: одна «18 EUR» растягивает шкалу гистограммы
        # так, что вся настоящая масса схлопывается в первый столбик.
        # Гистограмма и медиана считают вакансии, а не объявления по
        # городам: иначе одна вакансия в тридцати городах формирует
        # столбик, которого на рынке нет.
        currency_df = без_копий(только_правдоподобные(currency_df), "salary_from")
        salary_values = currency_df["salary_from"] if "salary_from" in currency_df.columns else pd.Series(dtype=float)
        salary_histogram_bins = salary_histogram(salary_values)
        salary_sample = int(salary_values.notna().sum())

        # Рублёвый вид: та же гистограмма, но по эквиваленту и по всей
        # выборке сразу. Внутри одной валюты человеку приходится смотреть
        # семь гистограмм и держать в голове, что 6 000 000 сум и
        # 300 000 рублей — соседние величины. Границы корзин и здесь
        # считаются по данным: та же функция, другие числа.
        все_правдоподобные = (
            без_копий(только_правдоподобные(df), "salary_from_rub")
            if "salary_from" in df.columns else pd.DataFrame()
        )
        эквивалент = (все_правдоподобные["salary_from_rub"]
                      if "salary_from_rub" in все_правдоподобные.columns
                      else pd.Series(dtype=float))
        эквивалент_чистый = эквивалент.dropna()

        # Валюты, которых нет в курсах ЦБ, эквивалента не получают.
        # Молча выбросить их нельзя: число «по 1 234 вакансиям» должно
        # сходиться с тем, что человек видит в списке.
        без_курса = int(len(все_правдоподобные) - len(эквивалент_чистый))

        histogram_rub = salary_histogram(эквивалент_чистый)
        stats_rub = {}
        if len(эквивалент_чистый) >= MIN_SAMPLE:
            stats_rub = {
                "currency": "RUB",
                "basis": "equivalent",
                "sample": int(len(эквивалент_чистый)),
                "median": float(эквивалент_чистый.median()),
                "q1": float(эквивалент_чистый.quantile(0.25)),
                "q3": float(эквивалент_чистый.quantile(0.75)),
            }

        # Статистика по выбранной валюте. Средняя не отдаётся: её тянут
        # выбросы, и правило системы допускает только медиану.
        salary_stats = {}
        clean = salary_values.dropna()
        if len(clean) >= MIN_SAMPLE:
            salary_stats = {
                "currency": currency,
                "sample": int(len(clean)),
                "median": float(clean.median()),
                "q1": float(clean.quantile(0.25)),
                "q3": float(clean.quantile(0.75))
            }

        # Статистика по валютам
        salary_stats_by_currency = {}
        if "salary_currency" in df.columns:
            for code in df["salary_currency"].unique():
                if pd.isna(code):
                    continue
                df_curr = df[df["salary_currency"] == code]
                if "salary_from" in df_curr.columns:
                    salary_df_curr = без_копий(только_правдоподобные(df_curr), "salary_from")
                    if not salary_df_curr.empty:
                        salary_stats_by_currency[code] = {
                            "min": float(salary_df_curr["salary_from"].min()),
                            "max": float(salary_df_curr["salary_from"].max()),
                            "median": float(salary_df_curr["salary_from"].median()),
                            "count": len(salary_df_curr)
                        }

        # Распределение по валютам
        currencies = {}
        if "salary_currency" in df.columns:
            currencies = df["salary_currency"].value_counts().to_dict()

        return {
            "experience": experience_counts,
            "employment": employment_counts,
            # Корзины зарплат по выбранной валюте: список, а не словарь,
            # потому что порядок корзин — часть смысла.
            "salary_histogram": salary_histogram_bins,
            "salary_currency": currency,
            "salary_sample": salary_sample,
            "salary_stats": salary_stats,
            "salary_stats_by_currency": salary_stats_by_currency,
            # Рублёвый вид приезжает тем же ответом: это вид, а не срез,
            # и переключение не должно ходить на сервер.
            "salary_histogram_rub": histogram_rub,
            "salary_sample_rub": int(len(эквивалент_чистый)),
            "salary_stats_rub": stats_rub,
            "without_rate": без_курса,
            "rate_date": _курс_для_ответа(),
            "currencies": currencies
        }
    finally:
        storage.close()

@app.get("/api/analytics/salary")
@запомнить
def get_salary_slice(
    basis: str = "currency",
    currency: str = "RUB",
    period: str = "all",
    experience: str = "",
    sphere: str = "",
    format: str = "",
    area: str = "",
    by: str = "experience",
    bucket: Optional[int] = None,
    step: str = "week",
    compare: str = "",
):
    """
    Срез зарплат для раскрытого окна «Распределение зарплат».

    Один ответ на всё окно: гистограмма среза, зарплатные уровни по
    выбранному измерению, состав корзины и ряд во времени. Блоки
    окна описывают одну и ту же выборку, и собирать их из четырёх
    запросов значило бы на мгновение показывать числа разных срезов
    рядом. Незнакомое значение среза даёт пустой срез, а не ошибку:
    ссылка с устаревшим названием сферы не должна ронять экран.
    """
    from src import salary_slice
    from src.storage import VacancyStorage

    срез = salary_slice.Срез(
        вид="rub" if basis in ("rub", "equivalent") else "currency",
        валюта=currency, период=period, опыт=experience, сфера=sphere, формат=format, регион=area,
    )
    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        ответ = salary_slice.собрать(df, срез, по=by, корзина=bucket, шаг=step, сравнить=compare)
        ответ["rate_date"] = _курс_для_ответа() if срез.в_рублях else None
        return ответ
    finally:
        storage.close()


@app.get("/api/analytics/geo")
@запомнить
def get_geo(basis: str = "currency", currency: str = "RUB"):
    """
    География зарплат для окна «Медиана по регионам»: страны, регионы и
    города одним ответом.

    Уровни приезжают вместе — их меньше пятисот строк, — и экран
    переходит от страны к её регионам и городам без запроса. Других
    измерений здесь нет намеренно: окно отвечает только на вопросы
    географии.
    """
    from src import geo_slice
    from src.storage import VacancyStorage

    storage = VacancyStorage()
    try:
        ответ = geo_slice.собрать(storage.get_all_vacancies(), вид=basis, валюта=currency)
        ответ["rate_date"] = _курс_для_ответа() if ответ["basis"] == "equivalent" else None
        return ответ
    finally:
        storage.close()


@app.get("/api/parser/status")
def parser_status():
    """
    Состояние сбора.

    Источник истины — база: состояние в памяти не переживает перезапуск
    приложения, и после него интерфейс показывал «сбора нет», пока запись
    висела в статусе «running».
    """
    from src.storage import VacancyStorage

    storage = VacancyStorage()
    try:
        активный = storage.get_active_run()
    finally:
        storage.close()

    if not активный:
        # Ничего не идёт — отдаём последнее известное состояние процесса,
        # чтобы интерфейс увидел итог только что закончившегося сбора.
        return {"state": parser_state}

    state = dict(parser_state)
    state.update({
        "is_running": True,
        "status": "running",
        "parser_run_id": активный["id"],
        "keywords": активный["keywords"],
        "current_keyword": активный["current_keyword"],
        "current_page": активный["current_page"],
        "vacancies_collected": активный["vacancies_collected"],
        "found_estimate": активный["found_estimate"],
        "progress": активный["progress"],
        "started_at": активный["started_at"],
    })
    return {"state": state}

@app.get("/api/parser/stop")
def stop_parser():
    """
    Остановка сбора.

    Сбор, идущий в этом процессе, получает просьбу напрямую. Сбор по
    расписанию идёт в другом процессе: ему просьба записывается в базу,
    и он читает её на ближайшем событии.
    """
    global parser_state
    if parser_state["is_running"]:
        parser_state["stop_requested"] = True
        parser_state["status"] = "stopping"
        # Просьба доходит до сбора напрямую: он идёт в фоновой задаче и
        # проверяет её на каждой странице.
        if active_collector is not None:
            active_collector.request_stop()
        logger.info("Запрошена остановка парсера")
        return {"message": "Остановка запрошена", "state": parser_state}

    from src.storage import VacancyStorage

    storage = VacancyStorage()
    try:
        активный = storage.get_active_run()
        if активный and storage.request_run_stop(активный["id"]):
            logger.info(f"Запрошена остановка сбора №{активный['id']} ({активный['source']})")
            return {"message": "Остановка запрошена", "state": {**parser_state, "status": "stopping"}}
    finally:
        storage.close()

    raise HTTPException(400, "Парсер не запущен")


@app.get("/api/parser/estimate")
def оценка_сбора(keywords_count: int = 1, max_pages: int = 10, упрутся: int | None = None):
    """
    Во что обойдётся сбор: обращений к источнику и минут.

    Считается на сервере, потому что цена зависит от его настроек —
    паузы между запросами и того, во сколько срезов режется упёршийся
    запрос. Экран прежде считал по полминуты за запрос и обещал «1 мин»
    там, где сбор занимал восемнадцать.

    `упрутся` — сколько запросов упрётся в предел выдачи; его называет
    разведка. Без него считается по худшему: режутся все, и цена
    завышается во столько раз, сколько срезов в бюджете.
    """
    настройки = _настройки_сбора()
    срезов = _app_settings.max_slices if _app_settings.резать_упёршиеся else 1

    return оценка(
        запросов=max(0, keywords_count),
        max_pages=max(1, max_pages),
        пауза=настройки.get("request_delay", 1.0),
        срезов=срезов,
        упрутся=упрутся,
    )


@app.post("/api/parser/scout")
def разведка_сбора(payload: dict):
    """
    Сколько запросов упрётся в предел выдачи — до того, как собирать.

    Стоит по одному лёгкому запросу на ключевое слово: спрашивается
    страница из одной вакансии, из ответа берётся только «найдено».
    Пятьдесят восемь запросов конфига — это около минуты, и она окупает
    честную оценку: без разведки экран вынужден считать по худшему.
    """
    keywords = [str(k).strip() for k in (payload.get("keywords") or []) if str(k).strip()]
    if not keywords:
        raise HTTPException(400, "Список запросов пуст")

    from src.collector import VacancyCollector  # локально: тянет тяжёлые зависимости

    сборщик = VacancyCollector(max_pages=_app_settings.max_pages, use_cache=True)
    итог = сборщик.разведать(keywords)
    настройки = _настройки_сбора()
    срезов = _app_settings.max_slices if _app_settings.резать_упёршиеся else 1

    return {
        **итог,
        "оценка": оценка(
            запросов=len(keywords),
            max_pages=_app_settings.max_pages,
            пауза=настройки.get("request_delay", 1.0),
            срезов=срезов,
            упрутся=len(итог["упрутся"]),
        ),
    }


# Сколько запросов принимает сбор за раз. Каждый удлиняет работу примерно
# на полминуты, а с резкой на срезы — на минуты; сотня запросов означает
# сбор длиной в сутки, который человек запустил, не заметив.
ПРЕДЕЛ_ЗАПРОСОВ = 50


@app.get("/api/settings/collection")
def настройки_сбора():
    """
    Настройки сбора: почта, пауза между запросами и список запросов.

    Список отдаётся как есть, включая `null`. Пусто и «пустой список» —
    разные вещи: в первом случае экран предложит заготовку из конфига,
    во втором покажет пустоту, которую человек сделал сам.
    """
    данные = _настройки_сбора()
    return {
        "email": данные["email"],
        "request_delay": данные["request_delay"],
        "search_queries": данные.get("search_queries"),
        "is_configured": bool(данные["email"]),
    }


@app.post("/api/settings/collection")
def сохранить_настройки_сбора(payload: dict):
    """
    Сохранить настройки сбора.

    Пауза ниже 200 мс — прямой путь к отказам источника по частоте,
    поэтому меньшее значение не принимается: настройка, позволяющая
    сломать сбор одним числом, вредна.
    """
    from src.storage import VacancyStorage

    email = (payload.get("email") or "").strip()
    if email and not EMAIL_REGEX.match(email):
        raise HTTPException(400, "Неверный формат email")

    задержка = payload.get("request_delay")
    if задержка is not None:
        try:
            задержка = float(задержка)
        except (TypeError, ValueError):
            raise HTTPException(400, "Пауза должна быть числом секунд")
        if задержка < 0.2:
            raise HTTPException(400, "Пауза меньше 0,2 секунды приводит к отказам источника")
        if задержка > 10:
            raise HTTPException(400, "Пауза больше 10 секунд сделает сбор бесконечным")

    запросы = payload.get("search_queries")
    if запросы is not None:
        if not isinstance(запросы, list):
            raise HTTPException(400, "Список запросов должен быть массивом строк")
        запросы = [str(з).strip() for з in запросы if str(з).strip()]
        # Один и тот же запрос дважды удлиняет сбор и ничего не
        # добавляет: порядок при этом сохраняется, человек его сам
        # выстроил.
        запросы = list(dict.fromkeys(запросы))
        if len(запросы) > ПРЕДЕЛ_ЗАПРОСОВ:
            raise HTTPException(
                400,
                f"Запросов больше {ПРЕДЕЛ_ЗАПРОСОВ} — такой сбор идёт сутками. "
                "Разбейте его на несколько.",
            )

    storage = VacancyStorage()
    try:
        сохранено = storage.save_collection_settings(
            email=email or None,
            request_delay=задержка,
            search_queries=запросы,
        )
    finally:
        storage.close()

    # Состояние в памяти держим в согласии с базой: его читают места,
    # которым нужен быстрый ответ без обращения к хранилищу.
    if сохранено["email"]:
        user_settings["hh_user_email"] = сохранено["email"]

    return {**сохранено, "is_configured": bool(сохранено["email"])}


@app.get("/api/parser/check")
def проверить_связь():
    """
    Проверка доступа к источнику.

    Один лёгкий запрос вместо целого сбора: узнать, что токен протух,
    лучше до запуска работы на десять минут, а не на её середине.
    """
    from src.api_client import HHAPIClient, ПричинаОтказа

    почта = user_settings.get("hh_user_email")
    if not почта:
        return {
            "доступно": False,
            "задержка_мс": 0,
            "причина": ПричинаОтказа.НЕТ_ПОЧТЫ,
            "подробности": "Укажите почту в настройках сбора",
        }

    try:
        client = HHAPIClient(email=почта, delay=_настройки_сбора()["request_delay"])
        return client.проверить_доступ()
    except Exception as e:
        return {
            "доступно": False,
            "задержка_мс": 0,
            "причина": ПричинаОтказа.НЕИЗВЕСТНО,
            "подробности": str(e)[:200],
        }


@app.get("/api/parser/cache/stats")
def cache_stats():
    """Статистика кэша API."""
    from src.api_cache import APICache

    try:
        cache = APICache()
        stats = cache.get_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.post("/api/parser/cache/clear")
def clear_cache(days: int = Query(default=7, description="Очистить кэш старше N дней")):
    """Очистка кэша API."""
    from src.api_cache import APICache

    try:
        cache = APICache()
        cache.clear_old(days)
        return {
            "success": True,
            "message": f"Кэш очищен (старше {days} дней)"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.post("/api/parser/start")
def start_parser(
    background_tasks: BackgroundTasks,
    keywords: Optional[list[str]] = Query(None),
    max_pages: Optional[int] = Query(None),
    days_back: Optional[int] = Query(None),
    incremental: bool = Query(False),
    use_cache: bool = Query(True),
    глубоко: bool = Query(True),
):
    """
    Запуск парсера (поддерживает обычный и оптимизированный режим).

    `глубоко` — резать ли запрос, упёршийся в предел выдачи. По умолчанию
    да: источник отдаёт не больше 2000 вакансий на запрос, и без резки по
    популярному слову видно пятую часть рынка. Внутри среза карточки не
    берутся, поэтому охват стоит минут; снять галочку имеет смысл, когда
    нужен быстрый поверхностный проход.
    """
    from src.storage import VacancyStorage
    global parser_state

    # Проверка: email пользователя настроен?
    user_email = user_settings.get("hh_user_email")
    if not user_email:
        raise HTTPException(
            403,
            "Для запуска парсера необходимо настроить email. "
            "Укажите ваш email от HH.ru в настройках (иконка ⚙️ в навигации)."
        )

    if parser_state["is_running"]:
        raise HTTPException(400, "Парсер уже запущен")

    # Запросы приходят от человека и ничем не подменяются.
    #
    # Раньше пустой список молча заменялся списком из конфига — это 58
    # запросов и часы работы, которых никто не просил. Экран кнопку при
    # пустом списке блокирует, но API открыт: старый интерфейс, ошибка в
    # клиенте или повтор запроса из истории браузера запускали чужой
    # сбор, а остановить его можно было только вручную.
    keywords = [к.strip() for к in (keywords or []) if к and к.strip()]
    if not keywords:
        raise HTTPException(
            400,
            "Не указано ни одного запроса. Добавьте запрос на экране «Сбор данных» "
            "— собирать по списку из конфига мы не будем.",
        )

    from src import collection_run

    storage = VacancyStorage()
    try:
        # Сбор может идти и не здесь: по расписанию он идёт отдельным
        # процессом. Два сбора сразу писали бы в одну базу и делили бы
        # один предел запросов к источнику.
        другой = collection_run.идёт_другой_сбор(storage)
        if другой:
            кто = "по расписанию" if другой["source"] == collection_run.РАСПИСАНИЕ else "в другом окне"
            raise HTTPException(400, f"Сбор уже идёт {кто} (№{другой['id']}). Дождитесь его или остановите.")

        # Продолжаем ли оборванный сбор.
        #
        # Продолжается только то, что оборвалось само: перезапуск
        # приложения посреди работы. Сбор, остановленный человеком,
        # продолжать нельзя — он сказал «хватит». Пройденные запросы
        # пропускаются: их вакансии уже в базе, а повторный обход стоит
        # столько же, сколько первый.
        продолжение = storage.find_resumable_run(keywords)
        пропустить = list((продолжение or {}).get("состояние", {}).get("пройденные_запросы", []))
        if пропустить:
            logger.info(
                f"Найден оборванный сбор #{продолжение['id']}: "
                f"{len(пропустить)} запросов уже пройдено, они будут пропущены"
            )

        # Запись о запуске создаётся до начала работы: её номер нужен
        # экрану сразу.
        parser_run_id = storage.create_parser_run(
            keywords=keywords,
            max_pages=max_pages or 10,
            days_back=days_back or 30,
            is_incremental=incremental,
            use_cache=use_cache,
            source=collection_run.ЭКРАН,
        )
    finally:
        storage.close()

    parser_state = collection_run.новое_состояние(
        keywords, запуск=parser_run_id, max_pages=max_pages, incremental=incremental,
        use_cache=use_cache, глубоко=глубоко, пропустить=пропустить,
    )
    # Словарь состояния передаётся в сбор и обновляется им по ходу; имя
    # `parser_state` за время сбора может быть переназначено только
    # следующим запуском, а он невозможен, пока идёт этот.
    состояние = parser_state

    def запомнить(collector):
        # Ссылка на идущий сбор: по ней остановка доходит до сборщика
        # напрямую, без опроса общего словаря состояния.
        global active_collector
        active_collector = collector

    def run():
        global active_collector
        try:
            # Сбор один на оба способа запуска — см. `src/collection_run.py`.
            collection_run.провести(
                keywords,
                email=user_email,
                пауза=_настройки_сбора()["request_delay"],
                max_pages=max_pages,
                days_back=days_back,
                incremental=incremental,
                use_cache=use_cache,
                глубоко=глубоко,
                источник=collection_run.ЭКРАН,
                запуск=parser_run_id,
                состояние=состояние,
                пропустить=пропустить,
                на_сборщик=запомнить,
            )
        finally:
            active_collector = None

    background_tasks.add_task(run)
    return {"message": "Парсер запущен", "state": parser_state}

# =============================================================================
# API для последнего парсинга и настроек
# =============================================================================

@app.get("/api/collection/suggestions")
@запомнить
def предложения_запросов():
    """
    Чего не хватает в базе: профессии, которые набрались попутно и ни
    одним запросом не собираются, и запросы с тонкой выборкой. У каждого
    предложения названо основание. Сбор отсюда не запускается.
    """
    import sqlite3

    from src import gaps

    запросы = _настройки_сбора().get("search_queries") or []
    conn = sqlite3.connect(_app_settings.db_path, timeout=30)
    try:
        return {
            "предложения": gaps.обновить(conn, запросы),
            "тонкие_запросы": gaps.найти(conn, запросы)["тонкие_запросы"],
            "принято": gaps.предложения(conn, статус=gaps.ПРИНЯТО, предел=20),
            "порог_тонкой_выборки": gaps.ТОНКАЯ_ВЫБОРКА,
        }
    except sqlite3.OperationalError as e:
        logger.warning(f"Пробелы базы не посчитаны: {e}")
        return {"предложения": [], "тонкие_запросы": [], "принято": [], "порог_тонкой_выборки": gaps.ТОНКАЯ_ВЫБОРКА}
    finally:
        conn.close()


@app.post("/api/collection/suggestions/decide")
def решить_предложение(payload: dict = Body(...)):
    """
    Решение человека по предложенному запросу. Принятый дописывается в
    список запросов сбора — и только: сбор по нему человек запускает
    сам, кнопкой, как и по остальным.
    """
    import sqlite3

    from src import gaps
    from src.storage import VacancyStorage

    ключ = str(payload.get("ключ") or "").strip()
    решение = payload.get("решение")
    if not ключ or решение not in ("accept", "reject"):
        raise HTTPException(400, "Нужны ключ предложения и решение: accept или reject")

    conn = sqlite3.connect(_app_settings.db_path, timeout=30)
    try:
        запрос = gaps.решить(conn, ключ, принять=решение == "accept")
    finally:
        conn.close()
    if запрос is None:
        raise HTTPException(404, "Такого предложения нет или по нему уже решено")

    запросы = list(_настройки_сбора().get("search_queries") or [])
    if запрос and запрос.lower() not in {з.lower() for з in запросы}:
        запросы.append(запрос)
        storage = VacancyStorage()
        try:
            storage.save_collection_settings(search_queries=запросы)
        finally:
            storage.close()
    return {"принято": решение == "accept", "запрос": запрос, "search_queries": запросы}


@app.get("/api/schedule")
def расписание_сбора():
    """
    Расписание сбора и то, держится ли оно: когда следующий запуск,
    когда был последний удачный сбор и не пропущен ли обещанный.
    """
    from src import schedule
    from src.storage import VacancyStorage

    storage = VacancyStorage()
    try:
        return schedule.состояние(storage)
    finally:
        storage.close()


@app.get("/api/parser/last-run")
def get_last_parser_run():
    """Получить данные о последнем запуске парсера."""
    from src.storage import VacancyStorage
    storage = VacancyStorage()
    try:
        last_run = storage.get_last_parser_run(only_successful=True)
        return {"last_run": last_run}
    finally:
        storage.close()

@app.get("/api/parser/history")
@запомнить
def get_parser_history(limit: int = 20):
    """Получить историю запусков парсера."""
    from src.storage import VacancyStorage
    storage = VacancyStorage()
    try:
        history = storage.get_parser_runs_history(limit=limit)
        # К каждой записи — разбивка по запросам. Она объясняет итог:
        # почему собрано столько и что помешало собрать больше.
        for run in history:
            run["queries"] = storage.get_run_queries(run["id"])
            # Что сбор не увидел. Пометка «partial» говорила об этом
            # словом, которого человек не знает, и не называла размер
            # потери: по запросу с несколькими тысячами вакансий мы
            # читаем первую тысячу, и итог сбора выглядит как весь рынок.
            run["недобор"] = сводка_недобора(run["queries"])

        # Качество собранного — рядом с числом собранного.
        #
        # «Собрано 1891» ничего не говорит о том, годятся ли эти записи
        # для аналитики. Карточка вакансии даёт 14,7 навыка против 2,4
        # без неё, и доля записей без карточки — прямой ответ на вопрос,
        # почему навыков мало. Раньше это можно было узнать только
        # запросом к базе руками.
        df = storage.get_all_vacancies(include_inactive=True)
        качество = {"всего": 0, "с_карточкой": 0, "без_навыков": 0}
        if not df.empty:
            с_карточкой = int(df["has_details"].fillna(0).astype(bool).sum())
            качество = {
                "всего": len(df),
                "с_карточкой": с_карточкой,
                "без_навыков": int((df["skill_count"].fillna(0) == 0).sum()),
            }

        return {"history": history, "качество": качество}
    finally:
        storage.close()

@app.get("/api/app/settings")
def get_app_settings():
    """Получить настройки приложения."""
    from src.storage import VacancyStorage
    storage = VacancyStorage()
    try:
        app_settings = storage.get_app_settings()
        return {"settings": app_settings}
    finally:
        storage.close()

# =============================================================================
# API для настроек пользователя (email для HH API)
# =============================================================================

import re

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

@app.get("/api/user/email")
def get_user_email():
    """Получить сохранённый email пользователя."""
    return {
        "email": user_settings.get("hh_user_email"),
        "is_configured": user_settings.get("hh_user_email") is not None
    }

@app.post("/api/user/email")
def set_user_email(email_data: dict):
    """Сохранить email пользователя для HH API."""
    email = email_data.get("email", "").strip()

    if not email:
        raise HTTPException(400, "Email не может быть пустым")

    if not EMAIL_REGEX.match(email):
        raise HTTPException(400, "Неверный формат email")

    user_settings["hh_user_email"] = email

    # Почта сохраняется в базу, а не заменой строки в .env.
    #
    # Прежде она дописывалась в файл окружения регулярным выражением:
    # под замену попадала любая строка с HH_USER_EMAIL, включая
    # закомментированную, а при сбое записи файл оставался испорченным.
    # Настройке место в базе — файл окружения задаёт первичные значения
    # и дальше не меняется.
    from src.storage import VacancyStorage

    storage = VacancyStorage()
    try:
        storage.save_collection_settings(email=email)
    except Exception as e:
        logger.error(f"Не удалось сохранить почту: {e}")
        raise HTTPException(500, "Почта не сохранена")
    finally:
        storage.close()

    logger.info(f"Email пользователя установлен: {email}")
    return {"message": "Email сохранён", "email": email}

# =============================================================================
# API для отчётов
# =============================================================================

# Разобранные срезы готовых файлов: ключ — имя, размер и время правки.
#
# Срез читается из самого файла, и открывать десяток xlsx на каждый
# запрос списка незачем: файл, у которого не изменились ни размер, ни
# время правки, не изменился и внутри. Перезапись файла тем же именем
# кэш не обманет — время правки станет другим.
_срезы_файлов: dict = {}


def _срез_файла(путь, размер: int, изменён: float) -> dict:
    from src.report_xlsx import прочитать_срез

    ключ = (путь.name, размер, изменён)
    if ключ not in _срезы_файлов:
        # Кэш растёт по числу файлов в папке, а не по числу запросов:
        # прежние ключи того же имени больше не нужны.
        for прежний in [к for к in _срезы_файлов if к[0] == путь.name]:
            _срезы_файлов.pop(прежний, None)
        _срезы_файлов[ключ] = прочитать_срез(путь)
    return _срезы_файлов[ключ]


def _состояние_файла(имя, создан, сейчас, свой, срок, предупредить_за) -> dict:
    """
    Состояние файла одним словом и сколько ему осталось.

    «Истекает» получает только файл, которого уборка действительно
    коснётся. Экспорт и выгрузки прежних анализаторов срок не трогает,
    и пометить их истекающими значило бы пообещать то, чего не будет.
    """
    if not свой(имя):
        return {"state": "ready", "expires_in_days": None}
    осталось = срок - int((сейчас - создан) // 86400)
    return {
        "state": "expiring" if осталось <= предупредить_за else "ready",
        "expires_in_days": max(осталось, 0),
    }


@app.get("/api/reports/list")
def list_reports():
    """
    Готовые файлы: чем каждый является, а не только как назван.

    Имя файла несёт дату сборки и больше ничего: по списку нельзя было
    понять, собран файл по всей базе или по выборке из восемнадцати
    вакансий. Объём и условия читаются из листа «Срез» внутри файла —
    там они уже есть, и там их нельзя разойтись с содержимым.

    CSV в списке наравне с XLSX: выгрузка со экрана «Вакансии» кладёт
    файл в ту же папку, а список его не показывал — человек искал его в
    файловой системе.
    """
    from src.config import settings
    from datetime import datetime

    from src.report_xlsx import (
        ПРЕДУПРЕДИТЬ_ЗА_ДНЕЙ, СРОК_ХРАНЕНИЯ_ДНЕЙ, собран_продуктом, убрать_устаревшие,
    )

    reports_dir = settings.reports_dir
    хранение = {"days": СРОК_ХРАНЕНИЯ_ДНЕЙ, "removed": []}
    if not reports_dir.exists():
        return {"reports": [], "retention": хранение}

    # Уборка по сроку — здесь, при обращении к списку: таймер внутри
    # процесса пропускал бы её ровно тогда, когда приложение месяц не
    # запускали. Убранное называется в ответе: файл, исчезнувший из
    # списка молча, выглядит как потеря.
    хранение["removed"] = убрать_устаревшие(reports_dir)
    сейчас = datetime.now().timestamp()

    reports = []
    for f in sorted(reports_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() not in (".xlsx", ".csv"):
            continue
        сведения = f.stat()
        срез = _срез_файла(f, сведения.st_size, сведения.st_mtime)
        reports.append({
            "name": f.name,
            "size": сведения.st_size,
            "created_at": datetime.fromtimestamp(сведения.st_ctime).isoformat(),
            # Пустые поля у файла, который продукт не собирал: экран
            # покажет прочерк, а не выдуманный срез.
            "vacancies": срез.get("вакансий"),
            "slice": срез.get("срез"),
            "data_collected": срез.get("данные_собраны"),
            "period": срез.get("период"),
            **_состояние_файла(
                f.name, сведения.st_ctime, сейчас,
                собран_продуктом, СРОК_ХРАНЕНИЯ_ДНЕЙ, ПРЕДУПРЕДИТЬ_ЗА_ДНЕЙ,
            ),
        })

    return {
        "reports": sorted(reports, key=lambda x: x["created_at"], reverse=True),
        "retention": хранение,
    }

def _файл_отчёта(filename: str):
    """
    Путь к файлу отчёта по имени из адреса — либо отказ.

    Имя приходит от клиента, и доверять ему нельзя. Скачивание брало его
    как есть: `/api/reports/download/../.env` отдавал файл с паролем и
    токеном источника любому, кто вошёл под учётной записью тестера.

    Правило одно на все системы: имя файла — это имя, без пути. Любой
    разделитель, прямой или обратный, отклоняется сам по себе. Сравнение
    итогового пути с папкой здесь недостаточно: на Linux обратный слэш —
    обычный символ, и `..\\config.yaml` там не обход, а странное имя;
    на Windows — обход. Один и тот же запрос не должен значить разное
    в зависимости от того, где запущен сервер.
    """
    from src.config import settings

    if not filename or "/" in filename or "\\" in filename or filename in (".", ".."):
        logger.warning(f"Имя файла отчёта отклонено: {filename!r}")
        raise HTTPException(400, "Нужно имя файла из папки отчётов, без пути")

    папка = settings.reports_dir.resolve()
    цель = (папка / filename).resolve()
    # Страховка на случай ссылок и особых имён устройств: итог обязан
    # лежать прямо в папке отчётов.
    if цель.parent != папка:
        logger.warning(f"Имя файла отчёта ведёт наружу: {filename!r}")
        raise HTTPException(400, "Нужно имя файла из папки отчётов, без пути")

    if not цель.is_file():
        raise HTTPException(404, "Отчёт не найден")
    return цель


@app.get("/api/reports/download/{filename:path}")
def download_report(filename: str):
    from fastapi.responses import FileResponse

    filepath = _файл_отчёта(filename)

    # Тип — по расширению: в списке есть и CSV, а отдавать его как
    # таблицу Excel значит предлагать открыть файл не той программой.
    тип = (
        "text/csv; charset=utf-8" if filepath.suffix.lower() == ".csv"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return FileResponse(path=filepath, filename=filepath.name, media_type=тип)


@app.delete("/api/reports/{filename:path}")
def delete_report(filename: str):
    """
    Удалить готовый файл из списка.

    Папка отчётов копится: собранный ради проверки файл на восемнадцать
    вакансий лежит в ней рядом с отчётом, который отправили заказчику, и
    отличить их глазами тем труднее, чем больше файлов. Убрать лишнее
    можно было только из файловой системы.

    Имя приходит из адреса и проверяется тем же правилом, что и при
    скачивании (`_файл_отчёта`): имя без пути, итог — прямо в папке
    отчётов.
    """
    цель = _файл_отчёта(filename)

    try:
        цель.unlink()
    except PermissionError:
        # Открытый в Excel файл Windows не отдаёт. Код ошибки человеку
        # ничего не подсказывает, а «закройте его в Excel» подсказывает.
        raise HTTPException(409, "Файл занят другой программой. Закройте его и повторите.")
    except OSError as e:
        logger.exception("Отчёт не удалён")
        raise HTTPException(500, f"Файл не удалён: {e}")

    for ключ in [к for к in _срезы_файлов if к[0] == цель.name]:
        _срезы_файлов.pop(ключ, None)

    logger.info(f"Отчёт удалён: {цель.name}")
    return {"deleted": цель.name}


# Состояние сборки отчёта — в памяти процесса.
#
# Сборка живёт секунды и не переживает перезапуск приложения осмысленно:
# после него файл всё равно не появится, и «идёт» из базы было бы ложью.
# Поэтому здесь, в отличие от сбора вакансий, базы нет.
состояние_отчёта = {
    "status": "idle",        # idle | running | done | error
    "started_at": None,
    "finished_at": None,
    "file": None,            # имя готового файла
    "vacancies": None,       # сколько вакансий вошло в файл
    "error": None,           # причина отказа словами
}


def _причина_отказа(ошибка: Exception) -> str:
    """Отказ сборки словами, которые что-то говорят человеку.

    «PermissionError: [Errno 13]» не подсказывает следующего шага, а
    «файл открыт в Excel» — подсказывает. Причины, которые нельзя
    назвать точно, честно называются общими словами: выдумывать
    объяснение хуже, чем признать, что оно неизвестно.
    """
    if isinstance(ошибка, PermissionError):
        return ("Файл отчёта занят другой программой. Закройте его в Excel "
                "и соберите заново.")
    if isinstance(ошибка, (FileNotFoundError, NotADirectoryError)):
        return "Папка для отчётов недоступна. Проверьте путь в настройках."
    if isinstance(ошибка, OSError) and getattr(ошибка, "errno", None) == 28:
        return "На диске не осталось места для файла отчёта."
    if isinstance(ошибка, MemoryError):
        return "Не хватило памяти на сборку файла. Попробуйте сузить выборку."
    return f"Сборка прервалась: {ошибка}"


def _статус_отчёта():
    """Копия состояния: вызывающий не должен править его случайно."""
    return dict(состояние_отчёта)


# Ниже этого числа выборка не годится для отчёта как документа: медианы
# по десяти вакансиям — не показатель рынка, а листы «Сводка» и «Навыки»
# получаются из двух строк. Собрать всё равно можно — предупреждение, а
# не запрет: срез на пять вакансий бывает нужен для проверки.
МАЛАЯ_ВЫБОРКА_ОТЧЁТА = 10


@app.get("/api/reports/status")
def report_status():
    """
    Состояние сборки отчёта: idle, running, done или error.

    Кнопка «Собрать отчёт» отвечала «Генерация запущена» и замолкала.
    Сборка идёт секунды и может отказать — человек об этом не узнавал:
    файл просто не появлялся в списке, и было непонятно, ждать ещё или
    уже нет.
    """
    return _статус_отчёта()


@app.get("/api/reports/preview")
def предпросмотр_отчёта(
    search: str = "",
    area: str = "",
    experience: str = "",
    skill: str = "",
    currency: str = "",
    source: str = "",
    salary_only: bool = False,
    include_inactive: bool = False,
):
    """
    Что попадёт в файл, если собрать отчёт по этой выборке.

    Отдельным ответом, а не догадкой на экране: человек должен видеть
    состав файла до сборки. Отчёт по трём вакансиям — потраченное время
    и файл, который стыдно отправить, а понять это после сборки дороже,
    чем до.

    Фильтры те же и применяются той же функцией, что список и сборка:
    третьей копии условий в продукте быть не должно.
    """
    from src.report_xlsx import состав_файла
    from src.storage import VacancyStorage

    фильтры = Фильтры(
        поиск=search, регион=area, опыт=experience, навык=skill,
        валюта=currency, источник=source,
        только_с_зарплатой=salary_only, включая_снятые=include_inactive,
    )

    storage = VacancyStorage()
    try:
        отобранное = отобрать(
            storage.get_all_vacancies(include_inactive=include_inactive), фильтры
        )
    finally:
        storage.close()

    состав = состав_файла(отобранное)
    return {
        **состав,
        "срез": словами(фильтры, всего=состав["вакансий"]),
        "малая_выборка_от": МАЛАЯ_ВЫБОРКА_ОТЧЁТА,
    }


@app.post("/api/reports/generate")
def generate_report(
    background_tasks: BackgroundTasks,
    search: str = "",
    area: str = "",
    experience: str = "",
    skill: str = "",
    currency: str = "",
    source: str = "",
    salary_only: bool = False,
    include_inactive: bool = False,
):
    """
    Собрать отчёт по текущей выборке экрана.

    Фильтры те же, что у списка вакансий, и применяются той же функцией:
    человек настроил выборку и должен получить файл ровно по ней, а не по
    всей базе. Без параметров собирается вся база — как раньше.
    """
    from src.storage import VacancyStorage

    фильтры = Фильтры(
        поиск=search, регион=area, опыт=experience, навык=skill,
        валюта=currency, источник=source,
        только_с_зарплатой=salary_only, включая_снятые=include_inactive,
    )

    if состояние_отчёта["status"] == "running":
        # Второй запуск поверх первого дал бы два файла с одинаковым
        # именем и гонку за него.
        return {**_статус_отчёта(), "accepted": False,
                "error": "Отчёт уже собирается. Дождитесь, пока файл появится в списке."}

    # Пустой отчёт не собирается: файл из нулевых строк выглядит как
    # поломка отчёта, а не как пустая база.
    storage = VacancyStorage()
    try:
        отобранное = отобрать(
            storage.get_all_vacancies(include_inactive=include_inactive), фильтры
        )
        пусто = отобранное.empty
    finally:
        storage.close()

    if пусто:
        # Пустая выборка и пустая база — разные беды, и лечатся по-разному:
        # в первом случае надо ослабить фильтр, во втором собрать данные.
        причина = (
            "По этим фильтрам вакансий нет. Ослабьте условия — отчёт собирается по выборке."
            if not фильтры.пусты else
            "В базе нет вакансий. Сначала соберите данные — отчёт собирается по ним."
        )
        состояние_отчёта.update({
            "status": "error",
            "finished_at": datetime.now().isoformat(),
            "file": None,
            "vacancies": 0,
            "error": причина,
        })
        return {**_статус_отчёта(), "accepted": False}

    def run():
        from src.storage import VacancyStorage
        from src.report_xlsx import описать_срез, собрать_отчёт

        storage = VacancyStorage()
        try:
            df = отобрать(
                storage.get_all_vacancies(include_inactive=include_inactive), фильтры
            )

            # Когда собраны данные — из последнего сбора, а не из времени
            # сборки файла: отчёт может собираться спустя неделю после
            # сбора, и получателю важна дата данных, а не дата файла.
            последний = storage.get_last_parser_run()
            завершён = последний.get("completed_at") if последний else None
            собран = None
            if завершён:
                момент = pd.to_datetime(завершён, errors="coerce")
                собран = f"{момент:%d.%m.%Y, %H:%M}" if pd.notna(момент) else None

            путь = собрать_отчёт(df, срез=описать_срез(
                df,
                # Условия словами: получатель файла не видел экрана, с
                # которого отчёт собран, и «активные вакансии» врали бы
                # про выборку по фильтру.
                фильтры=словами(фильтры),
                данные_собраны=собран,
            ))
            состояние_отчёта.update({
                "status": "done",
                "finished_at": datetime.now().isoformat(),
                "file": путь.name,
                "vacancies": len(df),
                "error": None,
            })
        except Exception as e:
            # Причина словами, а не кодом: человек читает тост, а не лог.
            # Тип исключения остаётся в логе — там он и нужен.
            logger.exception("Отчёт не собрался")
            состояние_отчёта.update({
                "status": "error",
                "finished_at": datetime.now().isoformat(),
                "file": None,
                "error": _причина_отказа(e),
            })
        finally:
            storage.close()

    состояние_отчёта.update({
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "file": None,
        "vacancies": None,
        "error": None,
    })
    background_tasks.add_task(run)
    return {**_статус_отчёта(), "accepted": True}

@app.get("/api/export/vacancies")
def export_vacancies(format: str = "csv"):
    from src.storage import VacancyStorage
    from src.config import settings
    from datetime import datetime

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        if df.empty:
            raise HTTPException(404, "Нет данных")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format == "csv":
            filepath = settings.reports_dir / f"vacancies_export_{timestamp}.csv"
            df.to_csv(filepath, index=False, encoding="utf-8-sig")
            media_type = "text/csv"
        else:
            filepath = settings.reports_dir / f"vacancies_export_{timestamp}.xlsx"
            df.to_excel(filepath, index=False, engine="openpyxl")
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        return FileResponse(path=filepath, filename=filepath.name, media_type=media_type)
    finally:
        storage.close()

# =============================================================================
# API для профессий
# =============================================================================

# Кэш для каталога профессий
_professions_catalog_cache = None

# Сколько вакансий в базе стоит за каждой профессией справочника.
#
# Справочник — снимок: он перечисляет профессии рынка и несёт числа того
# сбора, при котором был составлен. База с тех пор собиралась по другим
# запросам, и её содержимое со справочником разошлось: из 1339 профессий
# вакансии находились у 108, а 65 % собранных вакансий не попадали ни в
# одну профессию. Человек выбирал профессию и попадал в пустоту, потому
# что число рядом с ней описывало прошлое.
#
# Поэтому число считается по текущей базе, а не читается из файла.
_счёт_профессий_кэш = {"ключ": None, "значения": {}}


def _счёт_вакансий_по_профессиям(df, профессии):
    """
    Сопоставление профессий справочника с названиями вакансий.

    Совпадением считается название профессии, стоящее в названии
    вакансии отдельным словом, — с окончанием не длиннее двух букв.
    Это компромисс между двумя способами промахнуться:

    - подстрока без границ ловит чужие слова: «Логист» находится внутри
      «Логистика», «IT» — внутри «Retail» и «Digital»;
    - строгая граница слова теряет словоформы: «Менеджеров» и
      «Аналитики» перестают считаться, а это те же профессии.

    Полного разбора морфологии здесь не делается намеренно: он потребует
    словаря и всё равно будет ошибаться на английских названиях, которых
    в выдаче половина.
    """
    from collections import Counter

    названия = df["vacancy_name"].fillna("").str.lower().tolist() if not df.empty else []
    # Одинаковые названия считаются один раз, с кратностью: «менеджер по
    # продажам» встречается сотни раз, а проверять его достаточно однажды.
    кратность = Counter(названия)
    уникальные = list(кратность)
    # Все названия одной строкой — для быстрого вопроса «встречается ли
    # это имя хоть где-нибудь». Перевод строки в названиях профессий не
    # встречается, поэтому имя не может совпасть на стыке двух названий.
    весь_текст = "\n".join(уникальные)

    счёт = {}
    for профессия in профессии:
        имя = (профессия.get("name") or "").strip().lower()
        if not имя:
            счёт[профессия.get("key")] = 0
            continue
        # Шаблон требует, чтобы имя стояло в названии буквально, — значит
        # без этой подстроки совпадения быть не может. У девяти профессий
        # из десяти вакансий в базе нет вовсе, и прежде ради этого нуля
        # шаблон примерялся к каждому названию: 1 339 профессий на 6 500
        # названий, почти семь секунд после каждого сбора и перезапуска.
        if имя not in весь_текст:
            счёт[профессия["key"]] = 0
            continue
        шаблон = re.compile(r"(?<!\w)" + re.escape(имя) + r"\w{0,2}(?!\w)")
        счёт[профессия["key"]] = sum(
            кратность[название] for название in уникальные if имя in название and шаблон.search(название)
        )

    return счёт


def _профессии_с_числами():
    """
    Профессии справочника с актуальным числом вакансий.

    Результат запоминается до следующего изменения базы: ключом служит
    объём базы и момент последнего сбора.
    """
    from src.storage import VacancyStorage

    каталог = _load_professions_catalog()
    профессии = list(каталог.get("professions", {}).values())
    if not профессии:
        return []

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        последний = storage.get_last_parser_run(only_successful=True)
    finally:
        storage.close()

    ключ = (len(df), (последний or {}).get("completed_at"))
    if _счёт_профессий_кэш["ключ"] != ключ:
        _счёт_профессий_кэш["значения"] = _счёт_вакансий_по_профессиям(df, профессии)
        _счёт_профессий_кэш["ключ"] = ключ

    счёт = _счёт_профессий_кэш["значения"]

    # Число из справочника сохраняется отдельным полем: оно говорит,
    # сколько вакансий было у профессии при составлении справочника, и
    # его исчезновение выглядело бы как потеря данных.
    return [
        {**профессия,
         "vacancies_count": счёт.get(профессия["key"], 0),
         "catalog_count": профессия.get("vacancies_count", 0)}
        for профессия in профессии
    ]


def _load_professions_catalog():
    """Загрузить каталог профессий из файла."""
    global _professions_catalog_cache

    if _professions_catalog_cache is not None:
        return _professions_catalog_cache

    catalog_path = PROJECT_ROOT / "data" / "professions_catalog.json"

    if catalog_path.exists():
        import json
        with open(catalog_path, "r", encoding="utf-8") as f:
            _professions_catalog_cache = json.load(f)
    else:
        _professions_catalog_cache = {"professions": {}, "total": 0}

    return _professions_catalog_cache

@app.get("/api/professions/list")
@запомнить
def get_professions_list(
    domain: Optional[str] = None,
    sphere: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100
):
    """
    Список профессий справочника.

    Список остаётся полным: раздел нужен и тому, кто ещё не знает, в
    какую сторону смотреть, — прятать от него профессии значило бы
    прятать сами направления. Но число рядом с профессией берётся из
    текущей базы, а не из файла, и профессия без вакансий это честно
    показывает вместо обещания, которого не выполнит.
    """
    catalog = _load_professions_catalog()

    professions = _профессии_с_числами()

    # Фильтр по домену
    if domain:
        professions = [p for p in professions if p.get("domain") == domain]

    # Фильтр по сфере
    if sphere:
        professions = [p for p in professions if p.get("sphere") == sphere]

    # Поиск по названию
    if search:
        search_lower = search.lower()
        professions = [p for p in professions if search_lower in p.get("name", "").lower()]

    # Сначала профессии, по которым есть данные, — от больших выборок к
    # малым; следом остальные по алфавиту. Иначе тысяча пустых строк
    # ложится сверху и до собранного никто не долистает.
    professions.sort(key=lambda p: (-p.get("vacancies_count", 0), p.get("name", "")))

    с_данными = sum(1 for p in professions if p.get("vacancies_count", 0) > 0)
    всего_подходит = len(professions)

    professions = professions[:limit]

    return {
        "professions": professions,
        "total": всего_подходит,
        # Сколько из них не обещают пустоты — фильтры на экране считают
        # по этому числу, а не по длине показанной страницы.
        "with_data": с_данными,
        "domains": catalog.get("domains", {}),
        "areas": catalog.get("areas", {})
    }

@app.get("/api/professions/detail/{profession_key:path}")
def get_profession_detail(profession_key: str):
    """Получить детальную информацию о профессии."""
    catalog = _load_professions_catalog()

    profession = catalog.get("professions", {}).get(profession_key)

    if not profession:
        raise HTTPException(status_code=404, detail="Профессия не найдена")

    return profession

@app.get("/api/autocomplete/vacancies")
def autocomplete_vacancies(q: str = Query(..., min_length=2)):
    """
    Автодополнение названий вакансий.

    Args:
        q: Поисковый запрос (минимум 2 символа)

    Returns:
        Список подходящих названий вакансий
    """
    from src.storage import VacancyStorage
    import pandas as pd

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        if df.empty:
            return {"suggestions": []}

        # Фильтрация по запросу (case-insensitive)
        mask = df['vacancy_name'].str.contains(q, case=False, na=False)
        matches = df[mask]

        # Уникальные названия + сортировка по частоте + топ-10
        unique = matches['vacancy_name'].value_counts().head(10).index.tolist()

        return {
            "suggestions": [
                {"label": name, "value": name, "count": int(count)}
                for name, count in zip(unique, matches['vacancy_name'].value_counts().head(10).values)
            ],
            "total": len(unique)
        }
    finally:
        storage.close()

@app.get("/api/autocomplete/areas")
def autocomplete_areas(q: str = Query(..., min_length=2)):
    """
    Автодополнение регионов.

    Args:
        q: Поисковый запрос (минимум 2 символа)

    Returns:
        Список подходящих регионов
    """
    from src.storage import VacancyStorage

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        if df.empty:
            return {"suggestions": []}

        # Фильтрация
        mask = df['area'].str.contains(q, case=False, na=False)
        matches = df[mask]

        # Уникальные регионы + сортировка по частоте
        unique = matches['area'].value_counts().head(10).index.tolist()

        return {
            "suggestions": [
                {"label": area, "value": area, "count": int(count)}
                for area, count in zip(unique, matches['area'].value_counts().head(10).values)
            ],
            "total": len(unique)
        }
    finally:
        storage.close()

@app.get("/api/autocomplete/skills")
def autocomplete_skills(q: str = Query(..., min_length=2)):
    """
    Автодополнение навыков (hard/soft skills, tools).

    Args:
        q: Поисковый запрос (минимум 2 символа)

    Returns:
        Список подходящих навыков
    """
    from src.storage import VacancyStorage
    from collections import Counter

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()
        if df.empty:
            return {"suggestions": []}

        # Собираем все навыки
        all_skills = []

        for col in ['hard_skills', 'soft_skills', 'tools']:
            if col in df.columns:
                for skills_str in df[col].dropna():
                    if isinstance(skills_str, str):
                        skills = [s.strip() for s in skills_str.split(',')]
                        all_skills.extend([s for s in skills if s])

        # Фильтруем по запросу
        q_lower = q.lower()
        matches = [s for s in all_skills if q_lower in s.lower()]

        # Подсчёт частоты + топ-15
        counter = Counter(matches)
        top_skills = counter.most_common(15)

        return {
            "suggestions": [
                {"label": skill, "value": skill, "count": count}
                for skill, count in top_skills
            ],
            "total": len(counter)
        }
    finally:
        storage.close()

# Кэш для autocomplete (в памяти)
_autocomplete_cache = {}
_cache_ttl = 300  # 5 минут

@app.get("/api/analytics/kpi")
@запомнить
def get_kpi_metrics(
    period: Optional[str] = Query("all_time", description="Период: today|week|month|quarter|year|all_time"),
    domain: Optional[str] = Query(None, description="Домен профессии"),
    regions: Optional[str] = Query(None, description="Регионы через запятую"),
    experience: Optional[str] = Query(None, description="Опыт работы"),
    salary_only: bool = Query(False, description="Только вакансии с зарплатой")
):
    """
    KPI метрики с трендами для дашборда с поддержкой фильтров.

    Возвращает 8 ключевых метрик с процентами роста/падения.
    """
    from src.storage import VacancyStorage
    from datetime import datetime, timedelta
    import pandas as pd

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()

        if df.empty:
            return {
                "metrics": {},
                "period": period,
                "last_updated": datetime.now().isoformat()
            }

        # === Фильтры среза ===
        # Период применяется отдельно от прочих фильтров: предыдущее окно
        # должно отбираться теми же условиями, но другими датами.
        if "published_at" in df.columns:
            df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")

        df = apply_vacancy_filters(df, domain, regions, experience, salary_only)

        windows = period_windows(df, period)
        previous = None
        trend_blocked = None

        if windows:
            current_start, current_end, previous_start = windows
            trend_blocked = trend_reliability(df, previous_start)
            if trend_blocked is None:
                previous = slice_period(df, previous_start, current_start)
            df = slice_period(df, current_start, current_end)

        if df.empty:
            return {
                "metrics": {},
                "period": period,
                "filters": {
                    "period": period,
                    "domain": domain,
                    "regions": regions,
                    "experience": experience,
                    "salary_only": salary_only
                },
                "last_updated": datetime.now().isoformat()
            }

        # === Метрики и тренды ===
        now_values = collect_kpi_values(df)
        prev_values = collect_kpi_values(previous) if previous is not None and not previous.empty else {}

        # Тренды по снимкам — если они есть.
        #
        # Сравнение периодов внутри одного среза базы завышает свежие дни:
        # источник отдаёт только открытые вакансии, и старые дни к моменту
        # сбора успевают опустеть. Два снимка, снятых в разные дни,
        # сравнивать можно — каждый зафиксировал состояние на свою дату.
        снимки = _тренды_по_снимкам()
        if снимки:
            # Объяснение снимается только по тем метрикам, которые
            # снимки действительно покрыли. Прочерк без объяснения хуже
            # прочерка с объяснением: человек видит пустоту и не знает,
            # это поломка или свойство данных.
            покрыты = set(снимки)
            все_нужные = {"total_vacancies", "unique_companies", "unique_regions", "median_salary"}
            непокрытые = все_нужные - покрыты

            if not непокрытые:
                trend_blocked = None
            elif непокрытые == {"median_salary"}:
                trend_blocked = (
                    "зарплатные тренды появятся после второго сбора: "
                    "восстановленные точки истории хранят только счётные метрики"
                )
            else:
                trend_blocked = (
                    "часть трендов появится после второго сбора: "
                    "восстановленные точки истории знают, сколько было вакансий, "
                    "но не сколько из них оставались открытыми"
                )

        # Тренд считается по дате публикации вакансии, а не по дате сбора:
        # база знает только те вакансии, которые мы успели собрать, и это
        # ограничение названо в ответе, чтобы интерфейс мог его показать.
        if not windows:
            trend_basis = None
        elif trend_blocked:
            trend_basis = None
        else:
            trend_basis = f"к предыдущим {PERIOD_DAYS[period]} дням по дате публикации"

        def metric(key, extra=None):
            value = now_values.get(key)

            # Снимок точнее среза: если по метрике есть две точки
            # истории, тренд берётся оттуда.
            если_из_снимков = снимки.get(key) if снимки else None
            if если_из_снимков:
                payload = {"value": value, **если_из_снимков}
            else:
                payload = {"value": value, **trend_of(value, prev_values.get(key))}

            if extra:
                payload.update(extra)
            return payload

        # Объём выборки идёт рядом с зарплатными метриками: медиана по трём
        # вакансиям и по восьмидесяти — разные по надёжности числа.
        salary_extra = {"currency": "RUB", "sample": now_values["salary_sample"]}

        # У медианы по эквиваленту тренда нет и не будет, пока снимки не
        # начнут хранить курс своего дня (К4‑4a): сравнивать сегодняшний
        # эквивалент с прошлогодним по сегодняшнему курсу — значит
        # выдавать падение рубля за рост зарплат. Прочерк с объяснением
        # честнее числа, посчитанного не тем способом.
        курсы_для_подписи = _курс_для_ответа()
        эквивалент_extra = {
            "currency": "RUB",
            "basis": "equivalent",
            "sample": now_values["salary_sample_rub"],
            "rate_date": курсы_для_подписи,
            "trend_unavailable": "Тренд появится, когда снимки начнут хранить курс своего дня",
        }

        return {
            "metrics": {
                "median_salary": metric("median_salary", salary_extra),
                "median_salary_rub": {
                    "value": now_values["median_salary_rub"],
                    **эквивалент_extra,
                },
                "total_vacancies": metric("total_vacancies"),
                "total_skills": metric("total_skills"),
                "unique_companies": metric("unique_companies"),
                "unique_regions": metric("unique_regions"),
                "hard_skills_count": metric("hard_skills_count"),
                "soft_skills_count": metric("soft_skills_count")
            },
            "period": period,
            "trend_basis": trend_basis,
            "trend_unavailable": trend_blocked,
            "sample": {
                "vacancies": now_values["total_vacancies"],
                "with_salary": now_values["salary_sample"],
                "min_required": MIN_SAMPLE
            },
            "filters": {
                "period": period,
                "domain": domain,
                "regions": regions,
                "experience": experience,
                "salary_only": salary_only
            },
            "last_updated": datetime.now().isoformat()
        }

    finally:
        storage.close()

@app.get("/api/analytics/new-by-month")
@запомнить
def new_vacancies_by_month(months: int = 12):
    """
    Сколько новых вакансий приносил каждый месяц.

    Считается по `first_seen_at` — дате, когда вакансия впервые попала в
    базу, а не по дате публикации. Источник отдаёт только открытые
    вакансии: те, что закрылись, из выдачи исчезают. Ряд по дате
    публикации поэтому показывал бы вымирающий рынок — в старых месяцах
    остались бы только долгоживущие вакансии, — хотя дело лишь в том, что
    остальные успели закрыться.

    Это ряд о том, что видел сбор, а не о том, что происходило на рынке:
    месяцы до первого сбора пусты не потому, что вакансий не было.
    """
    from src.storage import VacancyStorage

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies(include_inactive=True)
    finally:
        storage.close()

    months = max(1, min(months, 60))
    сейчас = pd.Timestamp.now()
    текущий = сейчас.to_period("M")
    сетка = pd.period_range(end=текущий, periods=months, freq="M")

    ряд = []
    known = pd.Series(dtype="int64")
    без_даты = 0

    if not df.empty and "first_seen_at" in df.columns:
        даты = pd.to_datetime(df["first_seen_at"], errors="coerce", format="mixed")
        без_даты = int(даты.isna().sum())
        known = даты.dropna().dt.to_period("M").value_counts()

    for месяц in сетка:
        # Месяц без данных отдаётся нулём, а не пропускается: пропуск
        # сжимает ось, и на графике два соседних столбца оказываются
        # рядом, хотя между ними полгода.
        ряд.append({
            "month": str(месяц),
            "label": месяц.strftime("%m.%Y"),
            "count": int(known.get(месяц, 0)),
            # Текущий месяц ещё не кончился, и его столбец всегда ниже
            # соседних. Без пометки это читается как обвал.
            "partial": месяц == текущий,
        })

    первый = min(known.index) if len(known) else None

    return {
        "series": ряд,
        "basis": "first_seen_at",
        "total": int(known.sum()) if len(known) else 0,
        # Месяцы до первого сбора пусты по построению — об этом должна
        # сказать подпись, иначе ноль читается как «рынок стоял».
        "collected_since": str(первый) if первый is not None else None,
        "without_date": без_даты,
        "current_month": str(текущий),
    }


@app.get("/api/analytics/top-skills")
@запомнить
def get_top_skills(
    type: str = Query("hard", pattern="^(hard|soft|tools|employer)$"),
    limit: int = Query(20, ge=1, le=100),
    period: Optional[str] = Query("all_time", description="Период: today|week|month|quarter|year|all_time"),
    domain: Optional[str] = Query(None, description="Домен профессии"),
    regions: Optional[str] = Query(None, description="Регионы через запятую"),
    experience: Optional[str] = Query(None, description="Опыт работы")
):
    """
    Топ навыков по типу с поддержкой фильтров.

    Args:
        type: hard|soft|tools
        limit: 1-100 (default 20)
        period: Период фильтрации
        domain: Домен профессии
        regions: Регионы через запятую
        experience: Опыт работы

    Returns:
        Список навыков с количеством и процентами
    """
    from src.storage import VacancyStorage
    from datetime import timedelta
    from collections import Counter
    import pandas as pd

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()

        if df.empty:
            return {
                "type": type,
                "total_unique": 0,
                "skills": [],
                "filters": {
                    "type": type,
                    "limit": limit,
                    "period": period,
                    "domain": domain,
                    "regions": regions,
                    "experience": experience
                }
            }

        # === Применяем фильтры ===

        # Фильтр по периоду
        if period and period != "all_time":
            if 'published_at' in df.columns:
                df['published_at'] = pd.to_datetime(df['published_at'], errors='coerce')
                # Получаем часовой пояс из колонки published_at
                tz = df['published_at'].dt.tz
                now = pd.Timestamp.now(tz=tz) if tz else datetime.now()
                if period == "today":
                    df = df[df['published_at'] >= now.replace(hour=0, minute=0, second=0, microsecond=0)]
                elif period == "week":
                    df = df[df['published_at'] >= now - timedelta(days=7)]
                elif period == "month":
                    df = df[df['published_at'] >= now - timedelta(days=30)]
                elif period == "quarter":
                    df = df[df['published_at'] >= now - timedelta(days=90)]
                elif period == "year":
                    df = df[df['published_at'] >= now - timedelta(days=365)]

        # Фильтр по домену
        if domain:
            if 'domain' in df.columns:
                df = df[df['domain'].str.contains(domain, case=False, na=False)]
            elif 'profession' in df.columns:
                df = df[df['profession'].str.contains(domain, case=False, na=False)]

        # Фильтр по регионам
        if regions:
            region_list = [r.strip() for r in regions.split(',')]
            if 'area' in df.columns:
                mask = df['area'].str.contains('|'.join(region_list), case=False, na=False)
                df = df[mask]

        # Фильтр по опыту
        if experience:
            if 'experience' in df.columns:
                df = df[df['experience'] == experience]

        if df.empty:
            return {
                "type": type,
                "total_unique": 0,
                "skills": [],
                "filters": {
                    "type": type,
                    "limit": limit,
                    "period": period,
                    "domain": domain,
                    "regions": regions,
                    "experience": experience
                }
            }

        # Собираем все навыки
        all_skills = []
        # Четвёртая категория — не наша: это то, что работодатель назвал
        # сам в поле вакансии. Разложить её по hard/soft/tools не по
        # чему — три четверти таких навыков нет в наших словарях, и
        # категорию мы для них не знаем. Поэтому они считаются отдельно,
        # а не растворяются в остальных.
        column_map = {
            "hard": "hard_skills",
            "soft": "soft_skills",
            "tools": "tools",
            "employer": "employer_skills"
        }

        column_name = column_map.get(type)
        if column_name and column_name in df.columns:
            for skills_str in df[column_name].dropna():
                if isinstance(skills_str, str):
                    skills = [s.strip() for s in skills_str.split(',')]
                    all_skills.extend([s for s in skills if s])

        # Подсчёт частоты
        counter = Counter(all_skills)
        total_unique = len(counter)

        # Топ-N с процентами
        total_vacancies = len(df)
        top_skills = counter.most_common(limit)

        return {
            "type": type,
            "total_unique": total_unique,
            "skills": [
                {
                    "name": skill,
                    "count": count,
                    "percentage": round((count / total_vacancies) * 100, 1) if total_vacancies > 0 else 0
                }
                for skill, count in top_skills
            ],
            "filters": {
                "type": type,
                "limit": limit,
                "period": period,
                "domain": domain,
                "regions": regions,
                "experience": experience
            }
        }

    finally:
        storage.close()

# Кэш для autocomplete (в памяти)
_autocomplete_cache = {}
_cache_ttl = 300  # 5 минут

@app.get("/api/autocomplete/cached")
def autocomplete_cached(
    type: str = Query(..., pattern="^(vacancies|areas|skills)$"),
    q: str = Query(..., min_length=2)
):
    """
    Универсальный endpoint с кэшированием.

    Args:
        type: Тип autocomplete (vacancies|areas|skills)
        q: Поисковый запрос

    Returns:
        Кэшированный результат или новый запрос
    """
    import time
    from datetime import datetime

    cache_key = f"{type}:{q}"

    # Проверка кэша
    if cache_key in _autocomplete_cache:
        cached_data, cached_time = _autocomplete_cache[cache_key]
        if time.time() - cached_time < _cache_ttl:
            return {**cached_data, "cached": True}

    # Новый запрос
    if type == "vacancies":
        result = autocomplete_vacancies(q)
    elif type == "areas":
        result = autocomplete_areas(q)
    else:
        result = autocomplete_skills(q)

    # Сохранение в кэш
    _autocomplete_cache[cache_key] = (result, time.time())

    # Очистка старого кэша (раз в 100 запросов).
    #
    # Устаревшее удаляется из того же словаря, а не заменяется новым.
    # Присваивание имени внутри функции делало кэш её локальной
    # переменной, и проверка «есть ли ключ» выше падала с
    # UnboundLocalError раньше, чем доходила до любой работы: эндпоинт
    # отвечал ошибкой на каждый вызов.
    if len(_autocomplete_cache) > 100:
        now = time.time()
        for устаревший in [k for k, v in _autocomplete_cache.items() if now - v[1] >= _cache_ttl]:
            del _autocomplete_cache[устаревший]

    return {**result, "cached": False}

@app.get("/api/professions/vacancies")
def get_profession_vacancies(name: str):
    """Получить вакансии для профессии."""
    catalog = _load_professions_catalog()

    # Ищем профессию по названию
    profession = None
    for prof in catalog.get("professions", {}).values():
        if name.lower() in prof.get("name", "").lower():
            profession = prof
            break

    if not profession:
        return {"vacancies": []}

    # Возвращаем примеры вакансий
    return {
        "vacancies": profession.get("sample_vacancies", [])[:10]
    }

# =============================================================================
# Экспорт аналитики (PDF, Excel, CSV)
# =============================================================================

@app.post("/api/export/analytics")
def export_analytics(
    format: str = Query("xlsx", pattern="^(pdf|xlsx|csv)$"),
    period: Optional[str] = Query("all_time"),
    domain: Optional[str] = Query(None),
    regions: Optional[str] = Query(None),
    experience: Optional[str] = Query(None),
    salary_only: bool = Query(False)
):
    """
    Экспорт аналитического отчёта в формате PDF, Excel или CSV.

    Args:
        format: Формат экспорта (pdf|xlsx|csv)
        period: Период фильтрации
        domain: Домен профессии
        regions: Регионы через запятую
        experience: Опыт работы
        salary_only: Только вакансии с зарплатой

    Returns:
        Файл отчёта
    """
    from src.storage import VacancyStorage
    from src.config import settings
    from datetime import datetime
    import pandas as pd
    from io import BytesIO
    from fastapi.responses import StreamingResponse

    storage = VacancyStorage()
    try:
        df = storage.get_all_vacancies()

        if df.empty:
            raise HTTPException(status_code=404, detail="Нет данных для экспорта")

        # Применяем фильтры
        if period and period != "all_time":
            if 'published_at' in df.columns:
                df['published_at'] = pd.to_datetime(df['published_at'], errors='coerce')
                # Получаем часовой пояс из колонки published_at
                tz = df['published_at'].dt.tz
                now = pd.Timestamp.now(tz=tz) if tz else datetime.now()
                if period == "today":
                    df = df[df['published_at'] >= now.replace(hour=0, minute=0, second=0, microsecond=0)]
                elif period == "week":
                    df = df[df['published_at'] >= now - timedelta(days=7)]
                elif period == "month":
                    df = df[df['published_at'] >= now - timedelta(days=30)]
                elif period == "quarter":
                    df = df[df['published_at'] >= now - timedelta(days=90)]
                elif period == "year":
                    df = df[df['published_at'] >= now - timedelta(days=365)]

        if domain:
            if 'domain' in df.columns:
                df = df[df['domain'].str.contains(domain, case=False, na=False)]
            elif 'profession' in df.columns:
                df = df[df['profession'].str.contains(domain, case=False, na=False)]

        if regions:
            region_list = [r.strip() for r in regions.split(',')]
            if 'area' in df.columns:
                mask = df['area'].str.contains('|'.join(region_list), case=False, na=False)
                df = df[mask]

        if experience:
            if 'experience' in df.columns:
                df = df[df['experience'] == experience]

        if salary_only:
            if 'salary_from' in df.columns:
                df = df[df['salary_from'].notna()]

        if df.empty:
            raise HTTPException(status_code=404, detail="Нет данных после применения фильтров")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"hh_analytics_{timestamp}"

        if format == "csv":
            # CSV экспорт
            output = BytesIO()
            df.to_csv(output, index=False, encoding="utf-8-sig")
            output.seek(0)

            return StreamingResponse(
                output,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}.csv"}
            )

        elif format == "xlsx":
            # Excel экспорт с несколькими листами
            output = BytesIO()

            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # Лист 1: KPI метрики
                kpi_data = {
                    'Метрика': [
                        'Всего вакансий',
                        'Средняя зарплата',
                        'Медианная зарплата',
                        'Уникальных компаний',
                        'Уникальных регионов',
                        'Всего навыков',
                        'Hard Skills (уникальных)',
                        'Soft Skills (уникальных)'
                    ],
                    'Значение': [
                        len(df),
                        round(df[df['salary_from'].notna()]['salary_from'].mean(), 2) if not df[df['salary_from'].notna()].empty else 0,
                        round(df[df['salary_from'].notna()]['salary_from'].median(), 2) if not df[df['salary_from'].notna()].empty else 0,
                        df['employer_name'].nunique() if 'employer_name' in df.columns else 0,
                        df['area'].nunique() if 'area' in df.columns else 0,
                        int(df['skill_count'].sum()) if 'skill_count' in df.columns else 0,
                        len(set(s for skills_str in df['hard_skills'].dropna() if isinstance(skills_str, str) for s in skills_str.split(','))),
                        len(set(s for skills_str in df['soft_skills'].dropna() if isinstance(skills_str, str) for s in skills_str.split(',')))
                    ]
                }
                kpi_df = pd.DataFrame(kpi_data)
                kpi_df.to_excel(writer, sheet_name='KPI', index=False)

                # Лист 2: Hard Skills топ
                if 'hard_skills' in df.columns:
                    hard_skills = []
                    for skills_str in df['hard_skills'].dropna():
                        if isinstance(skills_str, str):
                            hard_skills.extend([s.strip() for s in skills_str.split(',') if s.strip()])
                    from collections import Counter
                    hard_counts = Counter(hard_skills)
                    hard_df = pd.DataFrame([
                        {'Навык': skill, 'Количество': count}
                        for skill, count in hard_counts.most_common(50)
                    ])
                    hard_df.to_excel(writer, sheet_name='Hard Skills', index=False)

                # Лист 3: Soft Skills топ
                if 'soft_skills' in df.columns:
                    soft_skills = []
                    for skills_str in df['soft_skills'].dropna():
                        if isinstance(skills_str, str):
                            soft_skills.extend([s.strip() for s in skills_str.split(',') if s.strip()])
                    soft_counts = Counter(soft_skills)
                    soft_df = pd.DataFrame([
                        {'Навык': skill, 'Количество': count}
                        for skill, count in soft_counts.most_common(50)
                    ])
                    soft_df.to_excel(writer, sheet_name='Soft Skills', index=False)

                # Лист 4: Tools топ
                if 'tools' in df.columns:
                    tools = []
                    for skills_str in df['tools'].dropna():
                        if isinstance(skills_str, str):
                            tools.extend([s.strip() for s in skills_str.split(',') if s.strip()])
                    tools_counts = Counter(tools)
                    tools_df = pd.DataFrame([
                        {'Инструмент': skill, 'Количество': count}
                        for skill, count in tools_counts.most_common(50)
                    ])
                    tools_df.to_excel(writer, sheet_name='Tools', index=False)

                # Лист 5: Сырые данные (первые 1000 записей)
                raw_df = df.head(1000).copy()
                raw_df.to_excel(writer, sheet_name='Данные', index=False)

                # Форматирование
                workbook = writer.book
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#4472C4',
                    'font_color': 'white',
                    'border': 1
                })

                for worksheet in writer.sheets.values():
                    for col_num in range(len(raw_df.columns) if worksheet.name == 'Данные' else 2):
                        worksheet.set_column(col_num, col_num, 20)

            output.seek(0)

            return StreamingResponse(
                output,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"}
            )

        elif format == "pdf":
            # PDF экспорт
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.lib.enums import TA_CENTER, TA_LEFT
            from collections import Counter

            output = BytesIO()
            doc = SimpleDocTemplate(
                output,
                pagesize=landscape(A4),
                rightMargin=0.5*inch,
                leftMargin=0.5*inch,
                topMargin=0.5*inch,
                bottomMargin=0.5*inch
            )

            elements = []
            styles = getSampleStyleSheet()

            # Заголовок
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                textColor=colors.HexColor('#1e40af'),
                spaceAfter=12,
                alignment=TA_CENTER
            )

            elements.append(Paragraph("HH.ru Analytics — Отчёт", title_style))

            # Информация о фильтрах
            filter_info = f"Период: {period} | Вакансий: {len(df)} | Дата генерации: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            elements.append(Paragraph(filter_info, styles['Normal']))
            elements.append(Spacer(1, 0.3*inch))

            # KPI таблица
            kpi_data = [
                ['Метрика', 'Значение'],
                ['Всего вакансий', str(len(df))],
                ['Средняя зарплата', f"{round(df[df['salary_from'].notna()]['salary_from'].mean(), 2) if not df[df['salary_from'].notna()].empty else 'N/A'} ₽"],
                ['Медианная зарплата', f"{round(df[df['salary_from'].notna()]['salary_from'].median(), 2) if not df[df['salary_from'].notna()].empty else 'N/A'} ₽"],
                ['Hard Skills (уникальных)', str(len(set(s for skills_str in df['hard_skills'].dropna() if isinstance(skills_str, str) for s in skills_str.split(','))))],
                ['Soft Skills (уникальных)', str(len(set(s for skills_str in df['soft_skills'].dropna() if isinstance(skills_str, str) for s in skills_str.split(','))))]
            ]

            kpi_table = Table(kpi_data, colWidths=[3*inch, 2*inch])
            kpi_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f9ff')])
            ]))
            elements.append(kpi_table)
            elements.append(Spacer(1, 0.3*inch))

            # Топ Hard Skills
            elements.append(Paragraph("Топ-20 Hard Skills", styles['Heading2']))
            elements.append(Spacer(1, 0.2*inch))

            if 'hard_skills' in df.columns:
                hard_skills = []
                for skills_str in df['hard_skills'].dropna():
                    if isinstance(skills_str, str):
                        hard_skills.extend([s.strip() for s in skills_str.split(',') if s.strip()])
                hard_counts = Counter(hard_skills)

                hard_data = [['Навык', 'Количество', '%']]
                total = len(df)
                for skill, count in hard_counts.most_common(20):
                    hard_data.append([skill, str(count), f"{round(count/total*100, 1)}%"])

                hard_table = Table(hard_data, colWidths=[2.5*inch, 1.5*inch, 1*inch])
                hard_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#ecfdf5')])
                ]))
                elements.append(hard_table)

            # Топ Soft Skills
            elements.append(Spacer(1, 0.3*inch))
            elements.append(Paragraph("Топ-20 Soft Skills", styles['Heading2']))
            elements.append(Spacer(1, 0.2*inch))

            if 'soft_skills' in df.columns:
                soft_skills = []
                for skills_str in df['soft_skills'].dropna():
                    if isinstance(skills_str, str):
                        soft_skills.extend([s.strip() for s in skills_str.split(',') if s.strip()])
                soft_counts = Counter(soft_skills)

                soft_data = [['Навык', 'Количество', '%']]
                total = len(df)
                for skill, count in soft_counts.most_common(20):
                    soft_data.append([skill, str(count), f"{round(count/total*100, 1)}%"])

                soft_table = Table(soft_data, colWidths=[2.5*inch, 1.5*inch, 1*inch])
                soft_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7c3aed')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f3ff')])
                ]))
                elements.append(soft_table)

            doc.build(elements)
            output.seek(0)

            return StreamingResponse(
                output,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename}.pdf"}
            )

    finally:
        storage.close()

# =============================================================================
# Маршруты интерфейса
#
# Интерфейс — одностраничное приложение: адреса вроде /vacancies или
# /reports существуют только в браузере, на сервере им ничего не
# соответствует. Поэтому всё, что не начинается с /api, отдаёт точку
# входа, а дальше маршрут разбирает сам интерфейс.
#
# Обработчик стоит последним: FastAPI проверяет маршруты по порядку
# объявления, и объявленный раньше он перехватывал бы вызовы API.
# =============================================================================

@app.get("/{full_path:path}")
def spa_routes(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "Неизвестный метод API")
    return index_response()


# =============================================================================
# Запуск
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("🚀 HH.ru Analytics — Веб-приложение")
    print("=" * 60)
    print(f"📁 Project: {PROJECT_ROOT}")
    print(f"📁 Интерфейс: {FRONTEND_DIST}")
    print(f"✅ Сборка на месте: {FRONTEND_DIST.exists()}")
    print()
    print("🌐 Откройте в браузере:")
    print("   http://localhost:8000")
    print("   http://localhost:8000/docs")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
