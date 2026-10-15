"""
Докачка текстов описаний для вакансий, у которых их нет (S10‑13).

Зачем. Текст описания — единственное, что читает модель слоя понимания,
и главный источник навыков словаря. На 15.10.2026 он был у 2 333 из
8 001 активной вакансии. Причин две: до 10.09.2026 тексты в базе не
хранились вовсе, а внутри срезов глубокого сбора карточки не
запрашиваются, и известная вакансия карточку не запрашивает никогда.

Откуда берётся текст — по порядку, от бесплатного к платному:
1. сырые файлы прошлых сборов (`data/raw`): там лежат карточки, скачанные
   до того, как тексты стали храниться в базе;
2. кэш карточек;
3. запрос к источнику — с той же паузой, что у сбора.

Что меняется у вакансии. Текст ложится в `vacancy_texts` тем же путём,
что у сбора, а у вакансии появляются ссылка на него, отметка карточки и
навыки словаря, пересчитанные по тексту. Зарплата, даты, название и
пометки запроса не трогаются: карточка из файла бывает полугодовой
давности, и её зарплата старше той, что лежит в базе.

Навыки работодателя не теряются. В сырых файлах `key_skills` есть не у
всех записей — часть база получила позже, — поэтому названное
работодателем берётся из базы и из карточки вместе. Скрипт пересчёта
навыков однажды стёр так почти десять тысяч упоминаний; здесь это
исключено построением.

Повторный запуск ничего не меняет: пишется только вакансия, у которой
текста всё ещё нет.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from src.normalize import SkillDictionaries, normalize_vacancy
from src.utils import get_logger

logger = get_logger(__name__)

# Поля вакансии, которые докачка переписывает. Всё остальное — как было.
ПОЛЯ_НАВЫКОВ = (
    "all_skills", "hard_skills", "soft_skills", "tools", "employer_skills",
    "skill_count", "hard_skill_count", "soft_skill_count", "tools_count",
)

УСЛОВИЕ = (
    "(v.text_hash IS NULL OR v.text_hash = '') AND COALESCE(v.off_query, 0) = 0 "
    "AND COALESCE(v.source, 'hh.ru') IN ('hh.ru', 'hh')"
)


def без_текста(conn: sqlite3.Connection, только_активные: bool = True,
               предел: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Вакансии, которым нужен текст: свежие — первыми.

    Вакансии не по запросу пропускаются: в аналитику они не входят, и
    тратить на них запросы к источнику незачем.
    """
    запрос = (
        "SELECT v.id, v.vacancy_id, v.vacancy_name, v.employer_name, v.published_at, "
        "v.area, v.employer_skills, v.skill_count FROM vacancies v WHERE " + УСЛОВИЕ
        + (" AND COALESCE(v.is_active, 1) = 1" if только_активные else "")
        + " ORDER BY COALESCE(v.is_active, 1) DESC, v.first_seen_at DESC, v.id DESC"
    )
    параметры: tuple = ()
    if предел:
        запрос += " LIMIT ?"
        параметры = (предел,)
    имена = ("id", "vacancy_id", "vacancy_name", "employer_name", "published_at", "area", "employer_skills", "skill_count")
    return [dict(zip(имена, строка)) for строка in conn.execute(запрос, параметры)]


def _вакансии_файла(путь: Path) -> list:
    try:
        данные = json.loads(путь.read_text(encoding="utf-8"))
    except Exception as ошибка:
        logger.warning(f"Файл сбора не прочитан, пропущен: {путь.name}: {ошибка}")
        return []
    if isinstance(данные, dict):
        данные = данные.get("vacancies") or данные.get("items") or []
    return данные if isinstance(данные, list) else []


def из_сырых(папка: Path, нужные: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """
    {ид: карточка из файла} для нужных вакансий, у которых в файлах есть описание.

    Из нескольких версий одной вакансии берётся та, где описание длиннее:
    в ранних сборах вакансия могла прийти из поиска, без карточки.
    """
    нужные = {str(ид) for ид in нужные}
    лучшее: Dict[str, Dict[str, Any]] = {}
    if not нужные or not папка.exists():
        return лучшее
    for файл in sorted(папка.glob("*.json")):
        for вакансия in _вакансии_файла(файл):
            if not isinstance(вакансия, dict):
                continue
            ид = str(вакансия.get("id") or "")
            описание = (вакансия.get("description") or "").strip()
            if ид not in нужные or not описание:
                continue
            было = лучшее.get(ид)
            if было is None or len(описание) > len((было.get("description") or "").strip()):
                лучшее[ид] = вакансия
    return лучшее


def _навыки_карточки(карточка: Dict[str, Any]) -> List[str]:
    return [н.get("name", "") for н in карточка.get("key_skills") or [] if isinstance(н, dict) and н.get("name")]


def слить(строка: Dict[str, Any], карточка: Dict[str, Any]) -> Dict[str, Any]:
    """
    Вакансия для разбора: описание — из карточки, остальное — из базы.

    Навыки работодателя — из базы и из карточки вместе, без повторов, с
    порядком базы впереди: в файле их может не быть, а стереть названное
    работодателем значило бы обменять пробел в тексте на пробел в навыках.
    """
    навыки = [н.strip() for н in (строка.get("employer_skills") or "").split(",") if н.strip()]
    видели = {н.lower() for н in навыки}
    for н in _навыки_карточки(карточка):
        if н.lower() not in видели:
            видели.add(н.lower())
            навыки.append(н)
    return {
        "id": строка["vacancy_id"],
        "name": строка.get("vacancy_name") or карточка.get("name") or "",
        "description": карточка.get("description") or "",
        "employer": {"name": строка.get("employer_name") or ""},
        "published_at": строка.get("published_at"),
        "area": {"name": строка.get("area") or ""},
        "key_skills": [{"name": н} for н in навыки],
        "_has_details": True,
    }


def записать(хранилище, пары: List[Tuple[Dict[str, Any], Dict[str, Any]]],
             словари: Optional[SkillDictionaries] = None) -> Dict[str, int]:
    """
    Записать тексты и пересчитанные навыки. Вакансия, у которой текст уже
    появился, не трогается — повторный запуск ничего не меняет.

    Returns:
        {"вакансий": записано, "текстов_новых": n, "навыков_было": n, "навыков_стало": n}
    """
    if not пары:
        return {"вакансий": 0, "текстов_новых": 0, "навыков_было": 0, "навыков_стало": 0}
    словари = словари or SkillDictionaries.from_config()
    разобранные = [(строка, normalize_vacancy(слить(строка, карточка), словари)) for строка, карточка in пары]
    разобранные = [(с, з) for с, з in разобранные if з.get("text_hash")]

    тексты = хранилище.сохранить_тексты(pd.DataFrame([{"_описание": з["_описание"]} for _, з in разобранные]))

    было = стало = записано = 0
    with хранилище.engine.begin() as conn:
        for строка, запись in разобранные:
            прежнее = conn.exec_driver_sql(
                "SELECT skill_count FROM vacancies WHERE id = ? AND (text_hash IS NULL OR text_hash = '')",
                (строка["id"],),
            ).fetchone()
            if прежнее is None:
                continue
            conn.exec_driver_sql(
                "UPDATE vacancies SET text_hash = ?, has_details = 1, "
                + ", ".join(f"{поле} = ?" for поле in ПОЛЯ_НАВЫКОВ)
                + " WHERE id = ? AND (text_hash IS NULL OR text_hash = '')",
                (запись["text_hash"], *(запись[поле] for поле in ПОЛЯ_НАВЫКОВ), строка["id"]),
            )
            было += прежнее[0] or 0
            стало += запись["skill_count"]
            записано += 1
    return {"вакансий": записано, "текстов_новых": тексты["новых"], "навыков_было": было, "навыков_стало": стало}


def карточка_источника(ид: str, клиент, кэш=None) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Карточка из кэша, а если её там нет — из источника.

    Returns:
        (карточка или None, был ли запрос к источнику) — по второму числу
        вызывающий решает, нужна ли пауза.
    """
    if кэш is not None:
        карточка = кэш.получить_карточку(ид)
        if карточка:
            return карточка, False
    карточка = клиент.get_vacancy_details(ид)
    if карточка and кэш is not None:
        кэш.сохранить_карточку(ид, карточка)
    return карточка, True
