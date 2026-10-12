"""
Кандидаты в словарь: главный продукт слоя понимания текста.

Модель находит в вакансии навык, которого словарь не знает. Такой навык
не уходит в аналитику и не теряется — он копится кандидатом. Когда он
встретился у трёх разных работодателей, его показывают человеку вместе
с цитатами, из которых он получен. Подтверждённый кандидат становится
обычной позицией словаря, и дальше его находит детерминированный код:
бесплатно и одинаково при каждом прогоне. Со временем модель работает
только по краю нового.

Порог «три работодателя», а не «три вакансии»: одна компания, разместив
вакансию в тридцати городах, тридцать раз повторяет одну свою опечатку.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from src import skills_store
from src.ai_contract import ИзвлечённыйНавык
from src.utils import get_logger

logger = get_logger(__name__)

# Сколько разных работодателей должны назвать навык, прежде чем он
# показывается человеку.
ПОРОГ_РАБОТОДАТЕЛЕЙ = 3

# Сколько цитат показывается у кандидата.
ЦИТАТ = 5

НОВЫЙ, ПОДТВЕРЖДЁН, ОТКЛОНЁН = "new", "confirmed", "rejected"

# В какой раздел словаря идёт навык каждого вида. Раздел можно
# переопределить при подтверждении: вид назвала модель, а решает человек.
РАЗДЕЛ_ПО_ВИДУ = {
    "инструмент": "tools",
    "технология": "hard",
    "метод": "hard",
    "язык": "hard",
    "компетенция": "soft",
}


def ключ(название: str) -> str:
    """По чему кандидат узнаётся: «Figma» и «figma » — один кандидат."""
    return " ".join((название or "").lower().split())


def известные(словарь: Optional[Dict[str, Any]] = None) -> set:
    """Всё, что словарь уже знает: каноны и варианты написания."""
    словарь = словарь or skills_store.загрузить()
    знает = {ключ(имя) for имя in skills_store.известные_названия(словарь)}
    знает |= {ключ(вариант) for вариант in skills_store.таблица_синонимов(словарь)}
    return знает


def учесть(
    conn: sqlite3.Connection,
    вакансия: str,
    работодатель: str,
    навыки: Iterable[ИзвлечённыйНавык],
    знает: Optional[set] = None,
) -> int:
    """
    Запомнить, что навыки встречены в вакансии.

    Навык, который словарь уже знает, кандидатом не становится. Отклонённый
    кандидат продолжает копить встречи, но человеку больше не показывается:
    так видно, что отклонённое продолжает встречаться, и решение можно
    пересмотреть.

    Returns:
        Сколько навыков учтено как кандидаты
    """
    знает = известные() if знает is None else знает
    сейчас = datetime.now().isoformat(sep=" ")
    учтено = 0
    for навык in навыки:
        имя = ключ(навык.название)
        if not имя or имя in знает:
            continue
        conn.execute(
            "INSERT INTO skill_candidates (name_key, name, kind, status, created_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (name_key) DO NOTHING",
            (имя, навык.название.strip(), навык.вид, НОВЫЙ, сейчас),
        )
        # Пара «кандидат — вакансия» одна: повторный прогон по той же
        # вакансии счётчик не увеличивает.
        conn.execute(
            "INSERT INTO skill_candidate_hits (name_key, vacancy_id, employer, quote, created_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (name_key, vacancy_id) DO UPDATE SET quote = excluded.quote, employer = excluded.employer",
            (имя, str(вакансия), (работодатель or "").strip(), навык.как_в_тексте.strip()[:300], сейчас),
        )
        учтено += 1
    return учтено


def забыть_вакансию(conn: sqlite3.Connection, вакансия: str) -> None:
    """Убрать встречи вакансии: её разбирают заново, и прежние находки могут не повториться."""
    conn.execute("DELETE FROM skill_candidate_hits WHERE vacancy_id = ?", (str(вакансия),))


def список(
    conn: sqlite3.Connection,
    статус: str = НОВЫЙ,
    порог: int = ПОРОГ_РАБОТОДАТЕЛЕЙ,
    предел: int = 200,
) -> List[Dict[str, Any]]:
    """
    Кандидаты с числом встреч, числом работодателей и цитатами.

    Для новых применяется порог: опечатка одного объявления до человека
    не доходит. Для решённых порога нет — решение уже принято.
    """
    строки = conn.execute(
        """
        SELECT c.name_key, c.name, c.kind, c.status, c.section, c.decided_at,
               COUNT(h.vacancy_id) AS встреч,
               COUNT(DISTINCT NULLIF(LOWER(TRIM(h.employer)), '')) AS работодателей
        FROM skill_candidates c LEFT JOIN skill_candidate_hits h ON h.name_key = c.name_key
        WHERE c.status = ?
        GROUP BY c.name_key
        HAVING ? = 0 OR работодателей >= ?
        ORDER BY работодателей DESC, встреч DESC, c.name
        LIMIT ?
        """,
        (статус, порог if статус == НОВЫЙ else 0, порог, предел),
    ).fetchall()

    итог = []
    for имя, название, вид, состояние, раздел, решён, встреч, работодателей in строки:
        цитаты = [
            {"цитата": цитата, "работодатель": работодатель, "вакансия": вакансия}
            for цитата, работодатель, вакансия in conn.execute(
                "SELECT quote, employer, vacancy_id FROM skill_candidate_hits WHERE name_key = ? "
                "GROUP BY LOWER(TRIM(employer)) ORDER BY created_at DESC LIMIT ?",
                (имя, ЦИТАТ),
            )
        ]
        итог.append({
            "ключ": имя, "название": название, "вид": вид, "статус": состояние,
            "раздел": раздел or РАЗДЕЛ_ПО_ВИДУ.get(вид or "", "hard"),
            "встреч": встреч, "работодателей": работодателей, "цитаты": цитаты, "решён": решён,
        })
    return итог


def сводка(conn: sqlite3.Connection, порог: int = ПОРОГ_РАБОТОДАТЕЛЕЙ) -> Dict[str, int]:
    """Сколько кандидатов всего, сколько ждут решения и сколько решено."""
    по_статусам = dict(conn.execute("SELECT status, COUNT(*) FROM skill_candidates GROUP BY status"))
    ждут = conn.execute(
        "SELECT COUNT(*) FROM (SELECT c.name_key FROM skill_candidates c JOIN skill_candidate_hits h "
        "ON h.name_key = c.name_key WHERE c.status = ? GROUP BY c.name_key "
        "HAVING COUNT(DISTINCT NULLIF(LOWER(TRIM(h.employer)), '')) >= ?)",
        (НОВЫЙ, порог),
    ).fetchone()[0]
    return {
        "новых": по_статусам.get(НОВЫЙ, 0), "ждут_решения": ждут,
        "подтверждено": по_статусам.get(ПОДТВЕРЖДЁН, 0), "отклонено": по_статусам.get(ОТКЛОНЁН, 0),
    }


def отклонить(conn: sqlite3.Connection, имя: str) -> bool:
    """Отклонить кандидата: он запоминается и больше не предлагается."""
    return _решить(conn, имя, ОТКЛОНЁН, None)


def подтвердить(
    conn: sqlite3.Connection,
    имя: str,
    раздел: Optional[str] = None,
    название: Optional[str] = None,
    файл_словаря: Optional[Path] = None,
) -> bool:
    """
    Подтвердить кандидата: навык уходит в словарь.

    Сначала словарь, потом отметка в базе: кандидат, помеченный
    подтверждённым, но не попавший в словарь, исчез бы из очереди и не
    стал бы находиться — худший из двух возможных обрывов.

    Args:
        раздел: hard / soft / tools; по умолчанию — по виду навыка
        название: как записать в словарь, если человек поправил написание
    """
    строка = conn.execute("SELECT name, kind FROM skill_candidates WHERE name_key = ?", (ключ(имя),)).fetchone()
    if not строка:
        return False
    раздел = раздел or РАЗДЕЛ_ПО_ВИДУ.get(строка[1] or "", "hard")
    if раздел not in skills_store.РАЗДЕЛЫ:
        raise ValueError(f"Раздела «{раздел}» в словаре нет")

    в_словарь(название or строка[0], раздел, файл_словаря)
    return _решить(conn, имя, ПОДТВЕРЖДЁН, раздел)


def _решить(conn: sqlite3.Connection, имя: str, статус: str, раздел: Optional[str]) -> bool:
    курсор = conn.execute(
        "UPDATE skill_candidates SET status = ?, section = ?, decided_at = ? WHERE name_key = ?",
        (статус, раздел, datetime.now().isoformat(sep=" "), ключ(имя)),
    )
    return курсор.rowcount > 0


def в_словарь(название: str, раздел: str, файл: Optional[Path] = None) -> bool:
    """
    Дописать навык в раздел словаря.

    Строка вставляется в конец раздела, а файл не переписывается целиком:
    словарь правят и руками, и перезапись через сериализатор поменяла бы
    в нём всё оформление разом — в истории изменений одна новая строка
    утонула бы в тысяче переформатированных.

    Returns:
        Добавлен ли навык (False — он там уже есть)
    """
    файл = файл or skills_store.ПУТЬ_СЛОВАРЯ
    запись = ключ(название)
    if not запись:
        raise ValueError("У навыка пустое название")

    словарь = skills_store.загрузить(файл)
    if запись in {ключ(имя) for имя in словарь.get(раздел) or []}:
        return False

    строки = файл.read_text(encoding="utf-8").split("\n")
    начало = next((i for i, строка in enumerate(строки) if строка.rstrip() == f"{раздел}:"), None)
    if начало is None:
        raise ValueError(f"В файле словаря нет раздела «{раздел}»")
    # Раздел кончается там, где начинается следующий ключ верхнего уровня.
    конец = next(
        (i for i in range(начало + 1, len(строки)) if строки[i] and not строки[i].startswith((" ", "-", "#"))),
        len(строки),
    )
    while конец > начало + 1 and not строки[конец - 1].strip():
        конец -= 1

    # Сериализатор нужен ради кавычек: «c#» и «1с: бухгалтерия» без них
    # читаются не как строка.
    новая = yaml.safe_dump([запись], allow_unicode=True, default_flow_style=False).rstrip("\n")
    строки.insert(конец, новая)
    файл.write_text("\n".join(строки), encoding="utf-8")

    сбросить_память_словаря()
    logger.info(f"Словарь навыков: в раздел {раздел} добавлено «{запись}»")
    return True


def сбросить_память_словаря() -> None:
    """Словарь изменился — подготовленные по нему структуры устарели."""
    try:
        from src import system_story

        system_story._навыки_словаря.cache_clear()
    except Exception:
        pass
