"""
Что делается после сбора по расписанию: тексты новых вакансий и их разбор.

Решение 15.10.2026 (S10‑11h): новые вакансии сбора разбираются без
человека. До него разбор запускали руками, и новые вакансии копились
без навыков модели; текст получали не все — внутри срезов глубокого
сбора карточки не запрашиваются.

Два шага, и ни один не меняет исход сбора — сбор уже прошёл:
1. докачка текстов: новых вакансий за сбор сотня-другая, это минуты;
2. разбор моделью — отдельным процессом в фоне: он идёт часами, а
   задание планировщика должно завершиться. Видеокарту или процессор
   прогон выбирает сам перед каждой порцией; второй прогон поверх
   идущего не запускается — его держит замок `data/разбор.pid`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, Optional

from src.config import PROJECT_ROOT
from src.utils import get_logger

logger = get_logger(__name__)

СКРИПТ_ТЕКСТОВ = PROJECT_ROOT / "scripts" / "maintenance" / "тексты_описаний.py"
СКРИПТ_РАЗБОРА = PROJECT_ROOT / "scripts" / "maintenance" / "обогащение_моделью.py"
ЖУРНАЛ_РАЗБОРА = PROJECT_ROOT / "logs" / "разбор_моделью.log"
# Свой журнал, а не общий журнал докачки: ручной запуск держит тот файл
# открытым, и Windows не даёт второму процессу в него писать.
ЖУРНАЛ_ТЕКСТОВ = PROJECT_ROOT / "logs" / "тексты_после_сбора.log"

# Докачка текстов после сбора — минуты; час — с запасом на медленный источник.
ТЕКСТЫ_НЕ_ДОЛЬШЕ_С = 3600

# Отдельный процесс без окна, который переживает завершение задания.
_ОТДЕЛЬНО = (
    subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    if sys.platform == "win32" else 0
)


def тексты(запуск: Callable = subprocess.run) -> int:
    """
    Докачать тексты вакансиям без них. Копию базы сбор уже снял.

    Returns:
        Код выхода докачки; при отказе — не ноль, но без исключения.
    """
    ЖУРНАЛ_ТЕКСТОВ.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(ЖУРНАЛ_ТЕКСТОВ, "a", encoding="utf-8") as журнал:
            исход = запуск(
                [sys.executable, "-u", str(СКРИПТ_ТЕКСТОВ), "--yes", "--сеть", "--без-копии"],
                cwd=str(PROJECT_ROOT), stdout=журнал, stderr=subprocess.STDOUT,
                timeout=ТЕКСТЫ_НЕ_ДОЛЬШЕ_С, env=_окружение(),
            )
        return исход.returncode
    except Exception:
        logger.exception("Тексты новых вакансий после сбора не докачаны")
        return 1


def разбор(запуск: Callable = subprocess.Popen) -> Optional[int]:
    """
    Запустить разбор моделью в фоне.

    Returns:
        Номер запущенного процесса либо None, если разбор уже идёт или не
        запустился. Идёт ли он, решает сам прогон по замку: здесь
        достаточно не плодить процессы, когда замок держит живой.
    """
    from src import process_lock
    from src.config import settings

    держит = process_lock.кто_держит(Path(settings.db_path).parent / "разбор.pid")
    if держит is not None:
        logger.info(f"Разбор после сбора не запущен: уже идёт (процесс {держит})")
        return None
    ЖУРНАЛ_РАЗБОРА.parent.mkdir(parents=True, exist_ok=True)
    try:
        журнал = open(ЖУРНАЛ_РАЗБОРА, "a", encoding="utf-8")
        процесс = запуск(
            [sys.executable, "-u", str(СКРИПТ_РАЗБОРА), "--сам", "--навыков-меньше", "1000"],
            cwd=str(PROJECT_ROOT), stdout=журнал, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=_ОТДЕЛЬНО, env=_окружение(),
        )
        logger.info(f"Разбор новых вакансий запущен в фоне, процесс {процесс.pid}")
        return процесс.pid
    except Exception:
        logger.exception("Разбор после сбора не запущен")
        return None


def после_сбора() -> Dict[str, object]:
    """
    Оба шага по порядку: сначала тексты — разбору нужен текст.

    Под тестами шаги не выполняются. Тесты сбора по расписанию проводят
    `собрать.py` до успеха, а шаги запускают настоящие процессы, которые
    берут рабочую базу из настроек, а не тестовую: 15.10.2026 прогон
    тестов так запустил докачку и разбор моделью на рабочей базе.
    """
    import os

    if "PYTEST_CURRENT_TEST" in os.environ:
        return {"тексты": None, "разбор": None, "пропущено": "под тестами"}
    return {"тексты": тексты(), "разбор": разбор()}


def _окружение() -> Dict[str, str]:
    import os

    окружение = dict(os.environ)
    окружение["PYTHONIOENCODING"] = "utf-8"
    return окружение
