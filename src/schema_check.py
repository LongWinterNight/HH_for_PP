"""
Сверка базы с тем, чего ждёт код.

Зачем. Новая колонка попадает в рабочую базу только миграцией, которую
запускают руками: `create_all` создаёт недостающие таблицы, но колонок
в существующие не добавляет. Если код обновился, а миграцию не
применили, приложение поднимается как ни в чём не бывало и падает на
первом запросе к таблице — с сообщением `no such column`, из которого
не следует, что делать. Так случилось 11.10.2026 с миграцией 021:
между правкой модели и её применением приложение успело
перезапуститься.

Здесь расхождение находится при старте и называется словами: какой
колонки нет и какой командой её добавить.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from src.utils import get_logger

logger = get_logger(__name__)


def недостающие(путь_к_базе: Path) -> Dict[str, List[str]]:
    """
    Колонки, которые есть в моделях и которых нет в базе.

    Таблицы, которых в базе нет вовсе, не считаются расхождением: их
    создаст хранилище при первом обращении. Лишние колонки базы тоже —
    код, который о них не знает, они не ломают.

    Returns:
        {таблица: [колонки]} — пусто, если база соответствует коду
    """
    from src.storage import Base

    if not Path(путь_к_базе).exists():
        return {}

    conn = sqlite3.connect(f"file:{путь_к_базе}?mode=ro", uri=True)
    try:
        итог: Dict[str, List[str]] = {}
        for таблица in Base.metadata.sorted_tables:
            в_базе = {строка[1] for строка in conn.execute(f'PRAGMA table_info("{таблица.name}")')}
            if not в_базе:
                continue
            нет = [колонка.name for колонка in таблица.columns if колонка.name not in в_базе]
            if нет:
                итог[таблица.name] = нет
        return итог
    except sqlite3.Error as e:
        # Сверка — подсказка, а не условие запуска: база, которую не
        # удалось прочитать, скажет о себе сама на первом запросе.
        logger.warning(f"Сверка базы с моделями не выполнена: {e}")
        return {}
    finally:
        conn.close()


def папка_миграций() -> Path:
    from src.config import PROJECT_ROOT

    return PROJECT_ROOT / "scripts" / "migrations"


def миграция_для(таблица: str, колонка: str, папка: Optional[Path] = None) -> Optional[str]:
    """
    Файл миграции, который добавляет колонку.

    Ищется по тексту: миграция называет и таблицу, и колонку в кавычках.
    Берётся последняя по номеру — одноимённую колонку в разных таблицах
    добавляли разные миграции, и таблица должна совпасть.
    """
    папка = папка or папка_миграций()
    if not папка.exists():
        return None
    имя = re.compile(rf"""["']{re.escape(колонка)}["']""")
    стол = re.compile(rf"""["']{re.escape(таблица)}["']|\b{re.escape(таблица)}\b""")
    подходящие = []
    for файл in sorted(папка.glob("[0-9]*.py")):
        try:
            текст = файл.read_text(encoding="utf-8")
        except OSError:
            continue
        if "ADD COLUMN" in текст and имя.search(текст) and стол.search(текст):
            подходящие.append(файл.name)
    return подходящие[-1] if подходящие else None


def объяснение(расхождения: Dict[str, List[str]], путь_к_базе: Path, папка: Optional[Path] = None) -> str:
    """Что не так и что сделать — текстом для журнала и оповещения."""
    if not расхождения:
        return ""
    строки = ["База отстала от кода: в ней нет колонок, которых ждёт приложение."]
    команды: List[str] = []
    for таблица, колонки in расхождения.items():
        строки.append(f"  {таблица}: {', '.join(колонки)}")
        for колонка in колонки:
            файл = миграция_для(таблица, колонка, папка)
            if файл:
                команда = f"python scripts/migrations/{файл} --db {путь_к_базе} --yes"
                if команда not in команды:
                    команды.append(команда)
    if команды:
        строки.append("Примените:")
        строки += [f"  {команда}" for команда in команды]
    else:
        строки.append("Миграция для них в scripts/migrations не найдена.")
    return "\n".join(строки)


def проверить(путь_к_базе: Optional[Path] = None) -> Dict[str, List[str]]:
    """Сверить рабочую базу с моделями и сказать о расхождении в журнал."""
    from src.config import settings

    путь = Path(путь_к_базе or settings.db_path)
    расхождения = недостающие(путь)
    if расхождения:
        logger.error(объяснение(расхождения, путь))
    return расхождения
