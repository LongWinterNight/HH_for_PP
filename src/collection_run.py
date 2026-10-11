"""
Проведение одного сбора: от записи о запуске до снимка метрик.

Зачем отдельный модуль. Всё, что делает сбор сбором, — запись хода в
базу, разбивка по запросам, качество, снимок метрик, оповещение об
отказе — жило во вложенной функции веб-обработчика. Запустить сбор
иначе, чем с экрана, значило повторить её: `main.py --collect` этого не
делал, и его сборы не попадали в историю. С появлением сбора по
расписанию вторая копия стала бы вторым путём сбора — с собственными
ошибками и расхождениями.

Здесь один путь на оба способа запуска. Экран передаёт сюда словарь
состояния, который опрашивает интерфейс; команда по расписанию —
ничего, и получает исход.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional

from src.utils import get_logger

logger = get_logger(__name__)

# Кто запустил сбор. Значения лежат в базе (`parser_runs.source`).
ЭКРАН = "screen"
РАСПИСАНИЕ = "schedule"

# Исходы сбора — те же слова, что в `parser_runs.status`.
ЗАВЕРШЁН = "completed"
ОСТАНОВЛЕН = "stopped"
ОТКАЗ = "error"

# Через сколько минут молчания сбор считается оборвавшимся. Отметка
# живости обновляется на каждом событии сбора; дольше всего сбор молчит,
# пережидая отказ источника «слишком часто», — это минуты, не десятки.
МОЛЧАНИЕ_ЧУЖОГО_СБОРА_МИН = 15

# Как часто сбор проверяет просьбу об остановке, пришедшую через базу.
ПРОВЕРКА_ОСТАНОВКИ_СЕК = 3.0

# Сколько последних вакансий держит лента на экране сбора.
ЛЕНТА_ВАКАНСИЙ = 6


@dataclass
class Исход:
    """Чем кончился сбор — для кода выхода команды и для журнала."""

    статус: str
    запуск: Optional[int] = None
    собрано: int = 0
    новых: int = 0
    обновлено: int = 0
    причина: Optional[str] = None
    сообщение: str = ""

    @property
    def удался(self) -> bool:
        return self.статус == ЗАВЕРШЁН


def новое_состояние(
    keywords: List[str],
    *,
    запуск: Optional[int],
    max_pages: Optional[int],
    incremental: bool,
    use_cache: bool,
    глубоко: bool,
    пропустить: Iterable[str] = (),
) -> Dict[str, Any]:
    """Состояние только что начатого сбора — то, что опрашивает экран."""
    пропущенные = list(пропустить)
    return {
        "is_running": True,
        "status": "running",
        "progress": 0,
        "current_keyword": keywords[0] if keywords else "",
        "current_page": 0,
        "total_pages": max_pages or 10,
        "vacancies_collected": 0,
        "keywords": keywords,
        "incremental": incremental,
        "use_cache": use_cache,
        "глубоко": глубоко,
        "parser_run_id": запуск,
        # Что пропущено как уже собранное оборванной попыткой. Число
        # уходит в ответ о состоянии: человек должен понимать, почему
        # сбор из семи запросов прошёл за минуту.
        "пропущено_пройденных": len(пропущенные),
        "error_message": None,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        # Ход по запросам. Сбор идёт десятки минут, и всё это время он
        # приносит то, на что можно смотреть: что дал каждый запрос и
        # какие вакансии только что найдены.
        "keyword_index": 0,
        "keywords_total": len(keywords),
        "keyword_done": 0,
        "keyword_total": 0,
        "pages_expected": 0,
        "eta_seconds": None,
        "queries": [
            {
                "keyword": запрос,
                # Пройденные прерванной попыткой помечены сразу: иначе
                # они висели бы «в очереди» до конца сбора.
                "status": "skipped" if запрос in пропущенные else "waiting",
                "found": None, "new": None, "updated": None,
            }
            for запрос in keywords
        ],
        "recent": [],
    }


def учесть_ход(состояние: dict, event, страниц: int) -> None:
    """
    Перенести событие сбора в состояние, которое опрашивает экран.

    Считать здесь есть что: процент, ожидаемые страницы, оставшееся
    время, разбивку по запросам.
    """
    from src.progress import осталось_секунд, процент, страниц_ожидается

    if event.keywords_total:
        состояние["keywords_total"] = event.keywords_total
    if event.keyword_index:
        состояние["keyword_index"] = event.keyword_index

    пройден = event.stage == "keyword_saved"
    if event.stage == "keyword_started":
        # Новый запрос: счётчики прежнего к нему не относятся.
        состояние["keyword_done"] = 0
        состояние["keyword_total"] = 0
        состояние["pages_expected"] = 0
    if event.keyword_total:
        состояние["keyword_done"] = event.keyword_done
        состояние["keyword_total"] = event.keyword_total
        состояние["pages_expected"] = страниц_ожидается(event.found, страниц)

    if event.stage != "finished":
        новый = процент(
            состояние.get("keyword_index", 0),
            состояние.get("keywords_total", 0),
            состояние.get("keyword_done", 0),
            состояние.get("keyword_total", 0),
            запрос_пройден=пройден,
        )
        # Назад полоса не ходит: при резке на срезы доля внутри запроса
        # считается по срезу и бывает меньше уже показанной.
        состояние["progress"] = max(состояние.get("progress", 0), новый)

    начат = состояние.get("started_at")
    if начат:
        прошло = (datetime.now() - datetime.fromisoformat(начат)).total_seconds()
        состояние["eta_seconds"] = осталось_секунд(прошло, состояние["progress"])

    for строка in состояние.get("queries", []):
        if строка["keyword"] != event.keyword:
            continue
        if event.found:
            строка["found"] = event.found
        if пройден:
            строка.update(status="done", new=event.new, updated=event.updated)
        elif строка["status"] != "done":
            строка["status"] = "running"

    if event.vacancy and event.vacancy.get("name"):
        лента = состояние.setdefault("recent", [])
        if not лента or лента[0] != event.vacancy:
            лента.insert(0, event.vacancy)
            del лента[ЛЕНТА_ВАКАНСИЙ:]


def причина_отказа(ошибка: BaseException) -> str:
    """
    Код причины отказа — по нему интерфейс выбирает объяснение и
    следующий шаг. Текст исключения для этого не годится.
    """
    import requests

    from src.api_client import ПричинаОтказа, TooManyRequests

    причина = getattr(ошибка, "причина", None)
    if причина is not None:
        return причина
    if isinstance(ошибка, TooManyRequests):
        return ПричинаОтказа.СЛИШКОМ_ЧАСТО
    if isinstance(ошибка, requests.RequestException):
        return ПричинаОтказа.СЕТЬ
    return ПричинаОтказа.НЕИЗВЕСТНО


def идёт_другой_сбор(storage) -> Optional[Dict[str, Any]]:
    """
    Идущий сейчас сбор, если он действительно идёт.

    Запись «running», чей процесс давно молчит, сначала помечается
    оборванной: иначе сбор, умерший вместе с компьютером, блокировал бы
    все следующие навсегда.
    """
    storage.mark_interrupted_runs(
        stale_after_minutes=МОЛЧАНИЕ_ЧУЖОГО_СБОРА_МИН,
        foreign_stale_minutes=МОЛЧАНИЕ_ЧУЖОГО_СБОРА_МИН,
    )
    return storage.get_active_run()


def провести(
    keywords: List[str],
    *,
    email: str,
    пауза: float,
    max_pages: Optional[int] = None,
    days_back: Optional[int] = None,
    incremental: bool = True,
    use_cache: bool = True,
    глубоко: bool = True,
    источник: str = ЭКРАН,
    запуск: Optional[int] = None,
    состояние: Optional[Dict[str, Any]] = None,
    пропустить: Iterable[str] = (),
    на_сборщик: Optional[Callable[[Any], None]] = None,
) -> Исход:
    """
    Провести сбор от начала до записи итога.

    Args:
        keywords: Запросы. Приходят от человека и ничем не подменяются
        email: Почта для заголовка запросов к источнику
        пауза: Пауза между запросами, секунды
        источник: Кто запустил — `ЭКРАН` или `РАСПИСАНИЕ`
        запуск: Номер уже созданной записи о запуске. Экран создаёт её до
            начала работы, чтобы сразу отдать номер; без него запись
            создаётся здесь
        состояние: Словарь, который опрашивает экран. Обновляется по
            ходу сбора. Без него заводится свой — процент нужен и базе
        пропустить: Запросы, пройденные оборванной попыткой
        на_сборщик: Вызывается с созданным сборщиком — экран запоминает
            его, чтобы остановка дошла напрямую

    Returns:
        Исход сбора. Исключения наружу не выходят: отказ — это исход, о
        котором уже сообщено и который уже записан.
    """
    from src.alerts import Отказ, сообщить
    from src.api_client import HHAPIClient
    from src.collector import VacancyCollector
    from src.storage import VacancyStorage

    пропущенные = list(пропустить)

    if запуск is None:
        storage = VacancyStorage()
        try:
            запуск = storage.create_parser_run(
                keywords=keywords,
                max_pages=max_pages or 10,
                days_back=days_back or 30,
                is_incremental=incremental,
                use_cache=use_cache,
                source=источник,
            )
        finally:
            storage.close()

    if состояние is None:
        состояние = новое_состояние(
            keywords, запуск=запуск, max_pages=max_pages, incremental=incremental,
            use_cache=use_cache, глубоко=глубоко, пропустить=пропущенные,
        )

    # Одно соединение на весь сбор: открывать его на каждое событие
    # значило бы платить за отчёт дороже, чем за работу.
    ход = VacancyStorage()
    collector = None

    try:
        # Пауза берётся из настроек, а не остаётся значением по
        # умолчанию: настройка, которая ни на что не влияет, хуже
        # отсутствующей — она обещает управление, которого нет.
        api_client = HHAPIClient(email=email, delay=пауза)

        # Что уже обойдено. Список начинается с унаследованного от
        # оборванной попытки: иначе продолжение, оборвавшись снова,
        # забыло бы про её работу и третий запуск начал бы всё заново.
        пройденные_запросы = list(пропущенные)
        проверено = {"когда": 0.0}

        def on_progress(event):
            """Ход сбора приходит событиями, а не подменой методов сборщика."""
            if event.keyword:
                состояние["current_keyword"] = event.keyword
            состояние["current_page"] = event.page
            состояние["vacancies_collected"] = event.collected

            # Запрос обойдён целиком и записан в базу. Запоминаем это,
            # чтобы оборванный сбор не собирал его заново: с резкой на
            # срезы один запрос — это уже не минута, а десятки.
            if event.stage == "keyword_saved" and event.keyword:
                пройденные_запросы.append(event.keyword)
                ход.save_run_progress(запуск, {
                    "пройденные_запросы": пройденные_запросы,
                    "текущий_запрос": event.keyword,
                    "всего_запросов": len(keywords),
                })

            if event.found:
                состояние["found_estimate"] = event.found

            учесть_ход(состояние, event, max_pages or 10)

            # В базу уходит тот же процент, что показан из памяти: экран
            # после перезапуска приложения читает его оттуда, и двух
            # разных чисел у одного сбора быть не должно.
            ход.update_run_progress(
                run_id=запуск,
                collected=event.collected,
                current_keyword=event.keyword,
                current_page=event.page,
                found_estimate=event.found,
                percent=состояние["progress"],
            )

            # Просьба об остановке, записанная в базу: так до сбора
            # дотягивается экран, когда сбор идёт в другом процессе.
            сейчас = time.monotonic()
            if collector is not None and сейчас - проверено["когда"] >= ПРОВЕРКА_ОСТАНОВКИ_СЕК:
                проверено["когда"] = сейчас
                if not collector.stop_requested and ход.is_run_stop_requested(запуск):
                    collector.request_stop()

        # Один сборщик на все режимы: кэш и дописывание — его флаги.
        collector = VacancyCollector(
            client=api_client,
            max_pages=max_pages,
            days_back=days_back,
            use_cache=use_cache,
            incremental=incremental,
            резать_упёршиеся=глубоко,
            on_progress=on_progress,
        )
        if на_сборщик is not None:
            на_сборщик(collector)

        result = collector.collect_all(keywords=keywords, save_raw=True, пройденные=пропущенные)

        # Сбор, который попросили остановить, — не удачный сбор: в
        # историю он раньше ложился как «завершён», и недобор по нему
        # выглядел как падение рынка.
        остановлен = bool(collector.stop_requested)
        статус = ОСТАНОВЛЕН if остановлен else ЗАВЕРШЁН

        if not остановлен:
            состояние["progress"] = 100
        состояние["status"] = статус
        состояние["completed_at"] = datetime.now().isoformat()
        состояние["vacancies_collected"] = result.get("unique", 0)
        collector.close()

        сообщение = (
            f"Вакансии сохранены, тексты описаний — нет: {result['отказ_текстов']}"
            if result.get("отказ_текстов") else ""
        )
        _записать_итог(запуск, статус, result, сообщение)

        # Сбор удался, но не целиком — об этом тоже сообщается: иначе о
        # потере узнают, когда тексты понадобятся.
        if result.get("отказ_текстов"):
            сообщить(Отказ(
                причина="partial",
                подробности=f"тексты описаний не записаны: {result['отказ_текстов']}",
                запуск=запуск,
                запросы=list(keywords),
            ))

        return Исход(
            статус=статус, запуск=запуск,
            собрано=result.get("unique", 0), новых=result.get("new", 0), обновлено=result.get("updated", 0),
            сообщение=сообщение,
        )

    except Exception as e:
        причина = причина_отказа(e)

        состояние["status"] = "error"
        состояние["error_message"] = str(e)
        состояние["error_type"] = причина
        состояние["completed_at"] = datetime.now().isoformat()

        # Трассировка — в журнал: по тексту исключения место сбоя не
        # найти, а окно консоли к утру закрыто. И оповещение: отказ, о
        # котором знает только экран, пролежал месяц.
        logger.exception(f"Сбор №{запуск} не удался")
        сообщить(Отказ(причина=причина, подробности=str(e), запуск=запуск, запросы=list(keywords)))

        try:
            storage = VacancyStorage()
            storage.complete_parser_run(run_id=запуск, status=ОТКАЗ, error_message=str(e), error_type=причина)
            storage.close()
        except Exception as db_err:
            logger.error(f"Ошибка записи ошибки парсинга в БД: {db_err}")

        return Исход(статус=ОТКАЗ, запуск=запуск, причина=причина, сообщение=str(e))

    finally:
        try:
            ход.close()
        except Exception:
            pass
        состояние["is_running"] = False
        состояние["stop_requested"] = False


def _записать_итог(запуск: int, статус: str, result: Dict[str, Any], сообщение: str) -> None:
    """Итог сбора в базу: запись о запуске, разбивка, качество, снимок."""
    from src.storage import VacancyStorage

    try:
        storage = VacancyStorage()
        storage.complete_parser_run(
            run_id=запуск,
            status=статус,
            vacancies_collected=result.get("unique", 0),
            vacancies_new=result.get("new", 0),
            vacancies_updated=result.get("updated", 0),
            # Сбор удался, но тексты описаний не записались: статус
            # остаётся «завершён», а причина названа.
            error_message=сообщение or None,
        )
        # Разбивка по запросам: из общего числа не видно, какой запрос
        # упал, какой прочитан не до конца, а какой просто не принёс
        # нового.
        storage.save_run_queries(запуск, result.get("by_keyword", {}))
        # Годится ли собранное для аналитики. Считается по записям этого
        # запуска: качество базы меняется медленно и прячет ухудшение
        # сегодняшнего сбора.
        storage.save_run_quality(запуск, result.get("качество", {}))
        # Точка истории: тренды считаются разницей между двумя снимками.
        # Курс обновляем здесь же: рублёвый эквивалент считается по
        # курсу на дату сбора. Отказ ЦБ сбор не роняет — остаются
        # прежние курсы с честной датой.
        storage.refresh_currency_rates()
        storage.save_metrics_snapshot(run_id=запуск)
        storage.close()
    except Exception as db_err:
        logger.error(f"Ошибка записи завершения парсинга в БД: {db_err}")
