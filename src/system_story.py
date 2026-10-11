"""
Данные для глав экрана «Как устроено».

Экран рассказывает, что система делает с вакансией, на одной настоящей
вакансии из базы: каким запросом она найдена, какие навыки и где в
тексте прочитаны, как зарплата приведена к рублям, во что вакансия
превратилась при хранении. Рядом — то, что видно только на всей базе:
что принёс каждый запрос последнего сбора, сколько строк убирает каждое
правило очистки и почему в зарплатах стоит медиана.

Здесь нет ни одного придуманного примера. Сцена с нарисованной
вакансией объясняла бы устройство вообще, а не этот продукт, и первое
же расхождение с настоящим экраном лишало бы её доверия.

Состояние систем (`system_state`) опрашивается, пока идёт сбор, и
потому считается одними счётчиками. Этот ответ запрашивается один раз
на открытие экрана и может позволить себе чтение текста и зарплат; от
повторных открытий его закрывает память по состоянию файла базы.
"""

from __future__ import annotations

import json
import re
import sqlite3
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)

# Сколько знаков текста показывает сцена разбора. Столько читается за
# время сцены; описание целиком превратило бы её в простыню.
ЗНАКОВ_ОТРЫВКА = 640
# Вакансии с длинным описанием и десятками навыков героем не берутся:
# сцена должна помещаться в экран и дочитываться до конца.
ПРЕДЕЛ_ТЕКСТА_ГЕРОЯ = 5000
# Сколько чисел вектора и слов индекса отдаётся для показа.
ЧИСЕЛ_ВЕКТОРА = 64
СЛОВ_ИНДЕКСА = 14
# Корзин в распределении зарплат и доля верхних значений, которую сцена
# сначала убирает, а потом возвращает.
КОРЗИН = 14
ДОЛЯ_ВЕРХА = 0.01

СЛОВО_ТЕКСТА = re.compile(r"[a-zа-яё0-9]+")

ВИДИМЫЕ = "COALESCE(is_active, 1) = 1 AND COALESCE(off_query, 0) = 0"


def _список(значение: Optional[str]) -> List[str]:
    return [часть.strip() for часть in (значение or "").split(",") if часть.strip()]


# ---------------------------------------------------------------------------
# Герой: одна вакансия, которую экран ведёт по всем главам
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _навыки_словаря() -> Dict[str, Any]:
    """Навыки словаря по тому названию, под которым они лежат в базе."""
    from src.normalize import SkillDictionaries

    словари = SkillDictionaries.from_config()
    return {навык.title: навык for навык in (*словари.hard, *словари.soft, *словари.tools)}


def _места_навыка(название: str, текст: str) -> Tuple[List[Tuple[int, int]], str]:
    """
    Где в тексте написан навык и каким способом он там найден.

    Ищется так же, как при разборе: целое слово, варианты написания,
    затем начальная форма — «визуализаций» это «визуализация». Навык,
    засчитанный по двум словам составного названия, места не получает:
    подсветка там, где буквально написано другое, рисовала бы поиск,
    которого не было.
    """
    готовый = _навыки_словаря().get(название)
    if готовый is not None:
        выражения = [готовый.word, *(выражение for _, выражение in готовый.variants)]
    else:
        # Навык назвал работодатель, в словаре его нет: ищем как написан.
        выражения = [re.compile(rf"(?<![\w]){re.escape(название.lower())}(?![\w])")]

    for выражение in выражения:
        места = [(совпадение.start(), совпадение.end()) for совпадение in выражение.finditer(текст)]
        if места:
            return места, "как написано"

    леммы = (getattr(готовый, "lemma", None) or "").split()
    if not леммы:
        return [], ""

    from src.morphology import начальная_форма

    слова = [(с.start(), с.end(), начальная_форма(с.group())) for с in СЛОВО_ТЕКСТА.finditer(текст)]
    места = []
    for i in range(len(слова) - len(леммы) + 1):
        if [слово[2] for слово in слова[i:i + len(леммы)]] == леммы:
            места.append((слова[i][0], слова[i + len(леммы) - 1][1]))
    return места, "форма слова" if места else ""


def _отрывок(текст: str, места: Dict[str, List[Tuple[int, int]]]) -> Tuple[int, int]:
    """
    Кусок текста, в котором названо больше всего навыков.

    Описание обычно начинается с рассказа о компании, а навыки стоят в
    требованиях. Первые шестьсот знаков показывали бы чтение, в котором
    ничего не находится.
    """
    if len(текст) <= ЗНАКОВ_ОТРЫВКА:
        return 0, len(текст)

    # Начинать отрывок можно с начала текста или с начала предложения.
    начала = [0] + [совпадение.end() for совпадение in re.finditer(r"[.!?:;]\s+", текст)]
    лучшее, счёт = 0, -1
    for начало in начала:
        конец = начало + ЗНАКОВ_ОТРЫВКА
        найдено = sum(
            1 for отрезки in места.values() if any(начало <= от and до <= конец for от, до in отрезки)
        )
        if найдено > счёт:
            лучшее, счёт = начало, найдено

    конец = min(len(текст), лучшее + ЗНАКОВ_ОТРЫВКА)
    if конец < len(текст):
        # Обрываем по слову, а не посреди него.
        пробел = текст.rfind(" ", лучшее, конец)
        if пробел > лучшее:
            конец = пробел
    return лучшее, конец


def _курс(conn: sqlite3.Connection, валюта: Optional[str], дата: Optional[str]) -> Optional[float]:
    if not валюта or валюта.upper() in ("RUB", "RUR"):
        return None
    try:
        строка = conn.execute(
            "SELECT value FROM currency_rates WHERE currency = ? AND rate_date <= COALESCE(?, rate_date) "
            "ORDER BY rate_date DESC LIMIT 1",
            (валюта.upper(), дата),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return float(строка[0]) if строка else None


def _хранение(conn: sqlite3.Connection, ид: str, название: str, описание: str, байт: Tuple[int, int]) -> Dict[str, Any]:
    """Во что вакансия превратилась в базе: поля, сжатый текст, слова, вектор."""
    from src.search import vectors
    from src.search.документ import привести

    слова = list(dict.fromkeys(привести(f"{название} {описание}").split()))
    полей = len(conn.execute("PRAGMA table_info(vacancies)").fetchall())

    вектор: List[float] = []
    размерность = 0
    try:
        строка = conn.execute(
            "SELECT vec FROM search_vectors WHERE vacancy_id = ? AND model = ?", (ид, vectors.имя_модели())
        ).fetchone()
        if строка and строка[0]:
            числа = np.frombuffer(строка[0], dtype=np.float16)
            размерность = int(числа.size)
            вектор = [round(float(число), 3) for число in числа[:ЧИСЕЛ_ВЕКТОРА]]
    except sqlite3.OperationalError:
        pass

    return {
        "полей": полей,
        "байт_текста": байт[0], "байт_сжато": байт[1],
        "слов": len(слова), "слова": слова[:СЛОВ_ИНДЕКСА],
        "вектор": вектор, "размерность": размерность,
        "модель": vectors.имя_модели().split("/")[-1],
    }


def _герой(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    """
    Вакансия, на которой видны все шаги.

    Берётся свежая, с коротким текстом и умеренным числом навыков.
    Вперёд идут вакансии с зарплатой в валюте: только на них виден
    перевод в рубли по курсу — шаг, который у рублёвых не происходит.
    """
    from src.search.документ import чистый_текст
    from src.texts import разжать

    try:
        строка = conn.execute(
            f"""
            SELECT v.vacancy_id, v.vacancy_name, v.employer_name, v.area, v.source_keyword,
                   v.all_skills, v.hard_skills, v.soft_skills, v.tools, v.employer_skills,
                   v.salary_from, v.salary_to, v.salary_currency, v.salary_from_rub, v.salary_to_rub,
                   v.rate_date, v.salary_mode, v.salary_gross, v.employment, v.schedule, v.experience,
                   v.salary_doubt,
                   t.body, t.bytes_raw, LENGTH(t.body)
            FROM vacancies v JOIN vacancy_texts t ON t.text_hash = v.text_hash
            WHERE {ВИДИМЫЕ.replace('is_active', 'v.is_active').replace('off_query', 'v.off_query')}
              AND v.skill_count BETWEEN 4 AND 14 AND t.bytes_raw <= ?
            ORDER BY (v.salary_from_rub IS NULL),
                     (v.salary_currency IS NULL OR UPPER(v.salary_currency) IN ('RUB', 'RUR')),
                     v.first_seen_at DESC, v.vacancy_id
            LIMIT 1
            """,
            (ПРЕДЕЛ_ТЕКСТА_ГЕРОЯ,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not строка:
        return None

    (ид, название, компания, регион, запросы, все, жёсткие, мягкие, инструменты, от_работодателя,
     от, до, валюта, от_руб, до_руб, дата_курса, период, до_налога, занятость, график, опыт,
     сомнение, тело, байт_текста, байт_сжато) = строка

    полный = чистый_текст(разжать(тело))
    # Гомоглифы чинятся и здесь: разбор искал навыки в починенном тексте,
    # и место, найденное в исходном, могло бы не найтись.
    from src.normalize import без_гомоглифов

    для_поиска = без_гомоглифов(полный.lower())
    сдвиг_возможен = len(для_поиска) == len(полный)

    виды = {
        **{имя: "инструмент" for имя in _список(инструменты)},
        **{имя: "мягкий" for имя in _список(мягкие)},
        **{имя: "профессиональный" for имя in _список(жёсткие)},
    }
    назвал_работодатель = set(_список(от_работодателя))
    места: Dict[str, List[Tuple[int, int]]] = {}
    способы: Dict[str, str] = {}
    for имя in _список(все):
        места[имя], способы[имя] = _места_навыка(имя, для_поиска) if сдвиг_возможен else ([], "")
    начало, конец = _отрывок(полный, места)

    навыки, отрезки = [], []
    for имя in _список(все):
        в_отрывке = [(от_ - начало, до_ - начало) for от_, до_ in места[имя] if начало <= от_ and до_ <= конец]
        отрезки += [{"от": от_, "до": до_, "навык": имя, "как": способы[имя]} for от_, до_ in в_отрывке]
        if в_отрывке:
            откуда = "отрывок"
        elif места[имя]:
            откуда = "текст"
        elif имя in назвал_работодатель:
            откуда = "работодатель"
        else:
            # Засчитан по словам составного названия: места в тексте нет.
            откуда = "по частям"
        навыки.append({"название": имя, "вид": виды.get(имя, "профессиональный"), "откуда": откуда})

    # Пересекающиеся отрезки («Revit» внутри «Autodesk Revit») сцена
    # нарисовать не может: остаётся более длинный.
    отрезки.sort(key=lambda о: (о["от"], -(о["до"] - о["от"])))
    без_пересечений: List[Dict[str, Any]] = []
    for отрезок in отрезки:
        if not без_пересечений or отрезок["от"] >= без_пересечений[-1]["до"]:
            без_пересечений.append(отрезок)

    return {
        "ид": str(ид), "название": название or "", "компания": компания or "", "регион": регион or "",
        "запрос": (_список(запросы) or [""])[0],
        "отрывок": {
            "текст": полный[начало:конец], "с_начала": начало == 0, "до_конца": конец >= len(полный),
            "знаков_всего": len(полный), "навыки": без_пересечений,
        },
        "навыки": навыки,
        "зарплата": {
            "от": от, "до": до, "валюта": валюта, "от_руб": от_руб, "до_руб": до_руб,
            "курс": _курс(conn, валюта, дата_курса), "дата_курса": (дата_курса or "")[:10],
            "период": период, "до_налога": None if до_налога is None else bool(до_налога),
            # Входит ли эта зарплата в распределение главы «Аналитика» —
            # по тем же условиям, по которым оно собирается.
            "в_распределении": bool(от_руб and not сомнение and период in (None, "MONTH")),
        },
        "занятость": занятость or "", "график": график or "", "опыт": опыт or "",
        "хранение": _хранение(conn, str(ид), название or "", полный, (байт_текста or 0, байт_сжато or 0)),
    }


# ---------------------------------------------------------------------------
# Сбор: что принёс каждый запрос последнего запуска
# ---------------------------------------------------------------------------

def _сбор(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    try:
        запуск = conn.execute(
            "SELECT r.id, r.status, r.started_at, r.completed_at FROM parser_runs r "
            "WHERE EXISTS (SELECT 1 FROM run_queries q WHERE q.run_id = r.id) ORDER BY r.id DESC LIMIT 1"
        ).fetchone()
        if not запуск:
            return None
        строки = conn.execute(
            "SELECT keyword, status, found, taken, pages, vacancies_new, vacancies_updated, from_cache, duration_ms "
            "FROM run_queries WHERE run_id = ? ORDER BY id",
            (запуск[0],),
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    from src.api_client import ПОЛЯ_ПОИСКА

    запросы = [
        {
            "запрос": слово, "исход": исход, "найдено": найдено or 0, "взято": взято or 0,
            "страниц": страниц or 0, "новых": новых or 0, "обновлено": обновлено or 0,
            "из_памяти": bool(из_памяти), "мс": мс or 0,
        }
        for слово, исход, найдено, взято, страниц, новых, обновлено, из_памяти, мс in строки
    ]
    return {
        "номер": запуск[0], "исход": запуск[1], "начат": запуск[2], "завершён": запуск[3],
        "запросы": запросы, "поля_поиска": list(ПОЛЯ_ПОИСКА),
        "взято": sum(з["взято"] for з in запросы), "новых": sum(з["новых"] for з in запросы),
        "обновлено": sum(з["обновлено"] for з in запросы), "страниц": sum(з["страниц"] for з in запросы),
        "мс": sum(з["мс"] for з in запросы),
    }


# ---------------------------------------------------------------------------
# Очистка: четыре правила, у каждого — число и настоящий пример
# ---------------------------------------------------------------------------

def _очистка(conn: sqlite3.Connection) -> Dict[str, Any]:
    def одно(запрос: str, параметры: tuple = ()) -> Any:
        строка = conn.execute(запрос, параметры).fetchone()
        return строка[0] if строка and строка[0] is not None else 0

    # Копии: одна вакансия, размещённая в нескольких городах.
    группы = conn.execute(
        f"SELECT vacancy_name, employer_name, COUNT(*) AS n FROM vacancies WHERE {ВИДИМЫЕ} "
        "AND vacancy_name IS NOT NULL AND employer_name IS NOT NULL "
        "GROUP BY vacancy_name, employer_name HAVING n > 1 ORDER BY n DESC, vacancy_name"
    ).fetchall()
    копии: Dict[str, Any] = {
        "вакансий": len(группы), "строк": sum(г[2] for г in группы), "пример": None,
    }
    if группы:
        название, компания, число = группы[0]
        города = [
            г[0] for г in conn.execute(
                "SELECT DISTINCT area FROM vacancies WHERE vacancy_name = ? AND employer_name = ? "
                f"AND {ВИДИМЫЕ} AND area IS NOT NULL ORDER BY area LIMIT 9",
                (название, компания),
            )
        ]
        копии["пример"] = {"название": название, "компания": компания, "строк": число, "города": города}

    # Не по запросу: слово запроса есть только в названии компании.
    не_по_запросу: Dict[str, Any] = {
        "скрыто": одно("SELECT COUNT(*) FROM vacancies WHERE COALESCE(off_query, 0) = 1"), "пример": None,
    }
    for название, компания, запросы in conn.execute(
        "SELECT vacancy_name, employer_name, source_keyword FROM vacancies WHERE COALESCE(off_query, 0) = 1 "
        "AND employer_name IS NOT NULL AND source_keyword IS NOT NULL ORDER BY LENGTH(vacancy_name), vacancy_id LIMIT 60"
    ):
        # Пример годится, когда слово запроса видно в названии компании
        # глазами: подсветку ставит экран, и ей должно быть что подсветить.
        слово = next((з for з in _список(запросы) if з.lower() in компания.lower()), None)
        if слово:
            не_по_запросу["пример"] = {"название": название, "компания": компания, "запрос": слово}
            break

    сомнительные = [
        {"название": н, "от": от, "до": до, "валюта": в, "причина": п, "период": м}
        for н, от, до, в, п, м in conn.execute(
            "SELECT vacancy_name, salary_from, salary_to, salary_currency, salary_doubt, salary_mode FROM vacancies "
            "WHERE salary_doubt IS NOT NULL AND salary_doubt != '' ORDER BY salary_doubt, vacancy_id LIMIT 40"
        )
    ]
    # По одному примеру на причину: две одинаковые причины ничего не добавляют.
    по_причинам = list({пример["причина"]: пример for пример in reversed(сомнительные)}.values())

    return {
        "копии": копии,
        "не_по_запросу": не_по_запросу,
        "сомнительные": {
            "число": одно("SELECT COUNT(*) FROM vacancies WHERE salary_doubt IS NOT NULL AND salary_doubt != ''"),
            "примеры": по_причинам[:2],
        },
        "снятые": {
            "в_архиве": одно("SELECT COUNT(*) FROM vacancies WHERE COALESCE(is_active, 1) = 0"),
            "активных": одно("SELECT COUNT(*) FROM vacancies WHERE COALESCE(is_active, 1) = 1"),
        },
    }


# ---------------------------------------------------------------------------
# Зарплаты: почему медиана, а не средняя
# ---------------------------------------------------------------------------

def _зарплаты(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    """
    Распределение зарплат и то, как на нём ведут себя средняя и медиана.

    Считается на тех же строках, что зарплатные числа аналитики:
    активные, по запросу, в рублях по курсу, без сомнительных и без
    ставок за час и смену.
    """
    import pandas as pd

    from src import copies

    df = pd.read_sql_query(
        f"SELECT vacancy_name, employer_name, salary_from_rub AS сумма FROM vacancies WHERE {ВИДИМЫЕ} "
        "AND salary_from_rub IS NOT NULL AND salary_from_rub > 0 "
        "AND (salary_doubt IS NULL OR salary_doubt = '') "
        "AND (salary_mode IS NULL OR salary_mode = 'MONTH')",
        conn,
    )
    if len(df) < 20:
        # На двух десятках строк распределение — случайность, а не картина.
        return None

    суммы = np.sort(df["сумма"].to_numpy(dtype=float))
    сколько_верхних = max(1, int(round(len(суммы) * ДОЛЯ_ВЕРХА)))
    без_верха = суммы[:-сколько_верхних]

    # Ось кончается там, где кончаются почти все зарплаты: растянутая до
    # самой большой, она сжала бы всё распределение в первые две корзины.
    предел = float(np.percentile(суммы, 97))
    шаг = предел / КОРЗИН
    корзины, _ = np.histogram(суммы[суммы < предел], bins=КОРЗИН, range=(0.0, предел))

    по_вакансиям = copies.без_копий(df, "сумма")["сумма"].median() if copies.ключ_доступен(df) else None

    return {
        "вакансий": int(len(суммы)),
        "корзины": [int(число) for число in корзины], "шаг": шаг, "предел": предел,
        "за_пределом": int((суммы >= предел).sum()),
        "медиана": float(np.median(суммы)), "средняя": float(суммы.mean()),
        "медиана_без_верха": float(np.median(без_верха)), "средняя_без_верха": float(без_верха.mean()),
        "верхних": int(сколько_верхних), "наименьшая_из_верхних": float(суммы[-сколько_верхних]),
        "наибольшая": float(суммы[-1]),
        "медиана_по_вакансиям": None if по_вакансиям is None else float(по_вакансиям),
    }


# ---------------------------------------------------------------------------

_память: Dict[str, Any] = {"ключ": None, "ответ": None}


def собрать() -> Dict[str, Any]:
    """Данные всех глав. Отказ одной главы не гасит остальные."""
    from src.config import settings

    путь = settings.db_path
    if not путь.exists():
        return {"герой": None, "сбор": None, "очистка": None, "зарплаты": None}

    # База меняется сбором и редкими командами; между ними ответ тот же.
    сведения = путь.stat()
    ключ = (str(путь), сведения.st_mtime_ns, сведения.st_size)
    if _память["ключ"] == ключ:
        return _память["ответ"]

    итог: Dict[str, Any] = {}
    conn = sqlite3.connect(f"file:{путь}?mode=ro", uri=True)
    try:
        части = {
            "герой": lambda: _герой(conn), "сбор": lambda: _сбор(conn),
            "очистка": lambda: _очистка(conn), "зарплаты": lambda: _зарплаты(conn),
        }
        for имя, получить in части.items():
            try:
                итог[имя] = получить()
            except Exception:
                logger.exception(f"Глава «{имя}» экрана «Как устроено» не собрана")
                итог[имя] = None
    finally:
        conn.close()

    # Проверка, что ответ уходит как есть: число NaN в нём сломало бы
    # разбор на стороне экрана, и узнать об этом лучше здесь.
    json.dumps(итог, ensure_ascii=False, allow_nan=False)
    _память.update(ключ=ключ, ответ=итог)
    return итог
