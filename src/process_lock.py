"""
Замок «этот прогон уже идёт» на файле с номером процесса.

Зачем. Разбор моделью теперь запускается сам после сбора по расписанию,
а его же запускают руками. Два прогона на одной модели разбирали бы одни
и те же вакансии и делили бы видеокарту. Файл с номером процесса —
простейший замок, который переживает падение: если процесса с этим
номером уже нет, замок считается брошенным и забирается.

Без сторонних библиотек: живость процесса на Windows проверяется через
OpenProcess и код завершения, на прочих системах — сигналом 0.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Код завершения процесса, который ещё работает (Windows, STILL_ACTIVE).
_ЕЩЁ_РАБОТАЕТ = 259


def жив(pid: int) -> bool:
    """Работает ли процесс с этим номером."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        ядро = ctypes.WinDLL("kernel32", use_last_error=True)
        ядро.OpenProcess.restype = wintypes.HANDLE
        # PROCESS_QUERY_LIMITED_INFORMATION — хватает и для чужих процессов.
        ручка = ядро.OpenProcess(0x1000, False, pid)
        if not ручка:
            return False
        try:
            код = wintypes.DWORD()
            if not ядро.GetExitCodeProcess(ручка, ctypes.byref(код)):
                return False
            return код.value == _ЕЩЁ_РАБОТАЕТ
        finally:
            ядро.CloseHandle(ручка)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def кто_держит(путь: Path) -> int | None:
    """Номер живого процесса, держащего замок, либо None."""
    try:
        pid = int(путь.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if жив(pid) else None


def захватить(путь: Path) -> bool:
    """
    Взять замок для текущего процесса.

    Returns:
        False — замок держит другой живой процесс; True — замок наш
        (свободный или брошенный упавшим прогоном).
    """
    держит = кто_держит(путь)
    if держит is not None and держит != os.getpid():
        return False
    путь.parent.mkdir(parents=True, exist_ok=True)
    путь.write_text(str(os.getpid()), encoding="utf-8")
    return True


def освободить(путь: Path) -> None:
    """Отдать замок, если он наш."""
    if кто_держит(путь) == os.getpid():
        try:
            путь.unlink()
        except OSError:
            pass
