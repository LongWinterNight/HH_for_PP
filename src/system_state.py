"""
Состояние систем продукта одним ответом — для экрана «Как устроено».

Экран показывает путь вакансии от источника до списка и числа на
каждом шаге. Числа — живые: сколько собрано, сколько из этого с
текстом, сколько в индексах поиска, поднята ли модель, дошло ли
последнее оповещение. Нарисованная схема с выдуманными цифрами
объясняла бы устройство, которого нет.

Всё читается счётчиками прямо из базы, без загрузки таблицы в память:
экран опрашивает состояние, пока идёт сбор, и тяжёлый запрос здесь
превратился бы в нагрузку, сравнимую с самим сбором.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from src.utils import get_logger

logger = get_logger(__name__)


def _одно(conn: sqlite3.Connection, запрос: str, по_умолчанию: Any = 0) -> Any:
    """Одно число из базы. Нет таблицы — значение по умолчанию, а не сбой."""
    try:
        строка = conn.execute(запрос).fetchone()
        return строка[0] if строка and строка[0] is not None else по_умолчанию
    except sqlite3.OperationalError:
        return по_умолчанию


def _база(conn: sqlite3.Connection, путь: Path) -> Dict[str, Any]:
    видимые = "COALESCE(off_query, 0) = 0"
    return {
        "вакансий": _одно(conn, f"SELECT COUNT(*) FROM vacancies WHERE {видимые}"),
        "активных": _одно(conn, f"SELECT COUNT(*) FROM vacancies WHERE {видимые} AND COALESCE(is_active, 1) = 1"),
        "не_по_запросу": _одно(conn, "SELECT COUNT(*) FROM vacancies WHERE COALESCE(off_query, 0) = 1"),
        "с_описанием": _одно(conn, "SELECT COUNT(*) FROM vacancies WHERE text_hash IS NOT NULL AND text_hash != ''"),
        "текстов": _одно(conn, "SELECT COUNT(*) FROM vacancy_texts"),
        "работодателей": _одно(conn, f"SELECT COUNT(DISTINCT employer_name) FROM vacancies WHERE {видимые}"),
        "размер_мб": round(путь.stat().st_size / 1e6, 1) if путь.exists() else 0,
    }


def _разбор(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Что разбор достаёт из вакансии: навыки, зарплата, занятость."""
    всего = _одно(conn, "SELECT COUNT(*) FROM vacancies") or 1
    try:
        from src.skills_store import загрузить, таблица_синонимов

        словарь = загрузить()
        канонов = sum(len(словарь.get(раздел) or []) for раздел in ("hard", "soft", "tools"))
        синонимов = len(таблица_синонимов(словарь))
    except Exception:
        # Словарь — файл, который правит человек; его поломка не должна
        # гасить весь экран.
        logger.exception("Словарь навыков не прочитан")
        канонов = синонимов = 0

    return {
        "навыков_в_словаре": канонов,
        "написаний": синонимов,
        "навыков_на_вакансию": round(_одно(conn, "SELECT AVG(skill_count) FROM vacancies WHERE skill_count > 0", 0.0), 1),
        "с_навыками": _одно(conn, "SELECT COUNT(*) FROM vacancies WHERE COALESCE(skill_count, 0) > 0"),
        "с_зарплатой": _одно(conn, "SELECT COUNT(*) FROM vacancies WHERE salary_from IS NOT NULL OR salary_to IS NOT NULL"),
        "с_рублёвым_эквивалентом": _одно(conn, "SELECT COUNT(*) FROM vacancies WHERE salary_from_rub IS NOT NULL"),
        "всего": всего,
    }


def _сбор(conn: sqlite3.Connection) -> Dict[str, Any]:
    запусков = _одно(conn, "SELECT COUNT(*) FROM parser_runs")
    удачных = _одно(conn, "SELECT COUNT(*) FROM parser_runs WHERE status = 'completed'")
    try:
        последний = conn.execute(
            "SELECT id, status, started_at, completed_at, keywords, vacancies_collected, vacancies_new, "
            "current_keyword, progress_percent FROM parser_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        последний = None

    сведения: Optional[Dict[str, Any]] = None
    if последний:
        try:
            запросы = json.loads(последний[4]) if последний[4] else []
        except (TypeError, ValueError):
            запросы = []
        сведения = {
            "номер": последний[0], "исход": последний[1], "начат": последний[2], "завершён": последний[3],
            "запросы": запросы, "собрано": последний[5] or 0, "новых": последний[6] or 0,
            "текущий_запрос": последний[7] or "", "процент": последний[8] or 0,
        }

    from src.api_client import ПОЛЯ_ПОИСКА

    return {
        "идёт": bool(последний and последний[1] == "running"),
        "запусков": запусков,
        "удачных": удачных,
        "последний": сведения,
        "источник": "hh.ru",
        "поля_поиска": list(ПОЛЯ_ПОИСКА),
    }


def _поиск(conn: sqlite3.Connection) -> Dict[str, Any]:
    from src.search import vectors, служба

    модель = vectors.имя_модели()
    состояние = служба.состояние()
    try:
        векторов = conn.execute("SELECT COUNT(*) FROM search_vectors WHERE model = ?", (модель,)).fetchone()[0]
    except sqlite3.OperationalError:
        векторов = 0

    return {
        "документов": _одно(conn, "SELECT COUNT(*) FROM search_docs"),
        "слов_в_словаре": _одно(conn, "SELECT COUNT(*) FROM search_vocab"),
        "векторов": векторов,
        "модель": модель.split("/")[-1],
        "смысл_включён": состояние["смысл_включён"],
        "модель_поднята": состояние["модель_поднята"],
        "отказ_модели": состояние["отказ_модели"],
        "порог_близости": vectors.порог_близости(модель),
    }


def _надзор() -> Dict[str, Any]:
    """Журнал и оповещения: пишется ли журнал и доходят ли сообщения."""
    from src import alerts, journal

    файл = journal.текущий_файл()
    последние = []
    for запись in alerts.последние(5):
        событие = запись.get("событие", {})
        # Подробности ошибки сюда не идут: экран открыт каждому, кто
        # вошёл, а текст исключения — для администратора (группа E4).
        последние.append({
            "заголовок": событие.get("заголовок", ""),
            "когда": событие.get("когда", ""),
            "доставлено": bool(запись.get("доставлено")),
            "проба": bool(событие.get("проба")),
        })

    return {
        "журнал_пишется": файл is not None,
        "журнал_размер_кб": round(файл.stat().st_size / 1024) if файл and файл.exists() else 0,
        "хранить_дней": journal.ХРАНИТЬ_ДНЕЙ,
        "телеграм_настроен": bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),
        "оповещения": последние,
    }


def _пример(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    """
    Одна настоящая вакансия, чей путь экран проигрывает по схеме.

    Настоящая, а не придуманная: «вакансия прошла разбор, найдено три
    навыка» убеждает, когда рядом название, компания и сами навыки.
    Берётся свежая вакансия с текстом и навыками — на ней видны все шаги.
    """
    try:
        строка = conn.execute(
            "SELECT vacancy_name, employer_name, area, source_keyword, all_skills, skill_count, "
            "salary_from, salary_currency, salary_from_rub, employment, schedule "
            "FROM vacancies WHERE COALESCE(is_active, 1) = 1 AND COALESCE(off_query, 0) = 0 "
            "AND text_hash IS NOT NULL AND skill_count >= 3 "
            "ORDER BY (salary_from IS NULL), first_seen_at DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not строка:
        return None

    навыки = [часть.strip() for часть in (строка[4] or "").split(",") if часть.strip()]
    return {
        "название": строка[0] or "", "компания": строка[1] or "", "регион": строка[2] or "",
        "запрос": (строка[3] or "").split(",")[0].strip(),
        "навыки": навыки[:4], "навыков": строка[5] or len(навыки),
        "зарплата": строка[6], "валюта": строка[7], "в_рублях": строка[8],
        "занятость": строка[9] or "", "график": строка[10] or "",
    }


def файл_замера() -> Path:
    from src.config import PROJECT_ROOT

    return PROJECT_ROOT / "data" / "замер_поиска.json"


def _замер() -> Optional[Dict[str, Any]]:
    """
    Последний замер поиска на эталоне.

    Числа читаются из файла, который пишет сам замер, а не переписаны в
    разметку экрана: переписанное число перестаёт быть правдой при
    первой же смене модели, и никто этого не замечает.
    """
    путь = файл_замера()
    if not путь.exists():
        return None
    try:
        return json.loads(путь.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def собрать() -> Dict[str, Any]:
    """Состояние всех систем. Отказ одной части не гасит остальные."""
    from src.config import settings

    итог: Dict[str, Any] = {}
    conn = sqlite3.connect(f"file:{settings.db_path}?mode=ro", uri=True) if settings.db_path.exists() else None
    try:
        части = {
            "сбор": lambda: _сбор(conn), "разбор": lambda: _разбор(conn),
            "база": lambda: _база(conn, settings.db_path), "поиск": lambda: _поиск(conn),
            "надзор": _надзор, "замер": _замер, "пример": lambda: _пример(conn),
        }
        for имя, получить in части.items():
            if conn is None and имя in ("сбор", "разбор", "база", "поиск", "пример"):
                итог[имя] = None
                continue
            try:
                итог[имя] = получить()
            except Exception:
                logger.exception(f"Состояние системы «{имя}» не получено")
                итог[имя] = None
    finally:
        if conn is not None:
            conn.close()
    return итог
