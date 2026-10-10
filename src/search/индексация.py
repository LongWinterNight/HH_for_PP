"""
Наполнение индексов поиска из базы вакансий.

Одна точка для обоих случаев: первая постройка по всей базе и
дозапись после сбора. Сбор вызывает её сам — новая вакансия должна
находиться сразу, а не после команды, о которой вспомнят через неделю.

Индексируются все вакансии, включая снятые с публикации и найденные
не по запросу. Что из них показывать, решает экран: он передаёт поиску
список допустимых. Иначе вакансию, с которой сняли пометку, пришлось
бы отдельно возвращать в индекс.
"""

from __future__ import annotations

import sqlite3
import zlib
from typing import Dict, Iterable, List, Optional

from src.search import lexical, vectors
from src.search.документ import Документ, собрать_документ
from src.utils import get_logger

logger = get_logger(__name__)

_ВЫБОРКА = """
SELECT v.vacancy_id, v.vacancy_name, v.all_skills, v.employer_skills, t.body, v.employer_name
FROM vacancies v LEFT JOIN vacancy_texts t ON t.text_hash = v.text_hash
"""


def документы(conn: sqlite3.Connection, идентификаторы: Optional[Iterable[str]] = None) -> List[Документ]:
    """Документы поиска по вакансиям базы — всем либо перечисленным."""
    if идентификаторы is None:
        строки = conn.execute(_ВЫБОРКА).fetchall()
    else:
        строки = []
        список = [str(ид) for ид in идентификаторы]
        # Частями: у SQLite предел на число подстановок в одном запросе.
        for начало in range(0, len(список), 500):
            часть = список[начало:начало + 500]
            строки += conn.execute(
                _ВЫБОРКА + f" WHERE v.vacancy_id IN ({','.join('?' * len(часть))})", часть
            ).fetchall()

    return [
        собрать_документ(
            ид, название, навыки, навыки_работодателя,
            zlib.decompress(тело).decode("utf-8") if тело else "", компания,
        )
        for ид, название, навыки, навыки_работодателя, тело, компания in строки
    ]


def обновить(
    conn: sqlite3.Connection,
    идентификаторы: Optional[Iterable[str]] = None,
    кодировщик: Optional[vectors.Кодировщик] = None,
    модель: Optional[str] = None,
) -> Dict[str, int]:
    """
    Записать вакансии в индексы поиска.

    Args:
        идентификаторы: Какие вакансии. None — вся база
        кодировщик: Модель векторов. Без неё обновляется только поиск
            по словам; векторы досчитаются при следующем вызове с моделью

    Returns:
        Сколько документов записано по словам и сколько векторов посчитано.
    """
    набор = документы(conn, идентификаторы)
    итог = {"по_словам": lexical.записать(conn, набор), "векторов": 0}
    conn.commit()

    if кодировщик is not None and набор:
        try:
            исход = vectors.досчитать(conn, набор, кодировщик, модель or vectors.имя_модели())
            итог["векторов"] = исход["посчитано"]
        except vectors.МодельНедоступна as ошибка:
            logger.info(f"Векторы не посчитаны: {ошибка}")
        except Exception:
            # Векторы — второй способ поиска, а не условие сбора: их
            # отказ не должен стоить ни сбора, ни поиска по словам.
            logger.exception("Векторы не посчитаны, поиск по словам обновлён")
    return итог
