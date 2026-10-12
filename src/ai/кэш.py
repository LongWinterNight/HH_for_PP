"""
Кэш разборов: один текст — один вызов модели.

Кэш здесь обязателен, а не желателен. Без него повторный прогон стоит
столько же, сколько первый, правка проверок требует заново гонять
модель, а прерванный прогон начинается с начала.

Ключ — хэш текста вместе с версиями модели и промпта: смена промпта или
модели пересчитывает, повторный запуск того же — нет. Старые разборы при
этом остаются: по ним видно, что говорила прежняя модель.

Хранится ответ модели как он пришёл, а не результат наших проверок.
Проверки проходят заново при каждом чтении — кэш не должен сохранять
доверие, которое мы оказали ответу вчера.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional

from src.texts import хэш


def ключ_текста(текст: str) -> str:
    """Хэш того текста, который видит модель."""
    return хэш(текст)


def найти(conn: sqlite3.Connection, текст: str, версия_модели: str, версия_промпта: str) -> Optional[str]:
    """Ответ модели на этот текст, если она его уже разбирала этой версией."""
    строка = conn.execute(
        "SELECT response FROM ai_extractions WHERE text_hash = ? AND model_version = ? AND prompt_version = ?",
        (ключ_текста(текст), версия_модели, версия_промпта),
    ).fetchone()
    return строка[0] if строка else None


def записать(
    conn: sqlite3.Connection,
    текст: str,
    версия_модели: str,
    версия_промпта: str,
    ответ: str,
    *,
    токенов_вход: int = 0,
    токенов_выход: int = 0,
    мс: int = 0,
    навыков: int = 0,
    отброшено: int = 0,
    прогон: str = "",
) -> None:
    """
    Запомнить разбор. Повтор того же ключа заменяет запись: так бывает,
    когда разбор прерван между записью в кэш и записью в вакансию.
    """
    conn.execute(
        "INSERT INTO ai_extractions (text_hash, model_version, prompt_version, response, tokens_in, tokens_out, "
        "duration_ms, skills_count, rejected_count, run_tag, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (text_hash, model_version, prompt_version) DO UPDATE SET response = excluded.response, "
        "tokens_in = excluded.tokens_in, tokens_out = excluded.tokens_out, duration_ms = excluded.duration_ms, "
        "skills_count = excluded.skills_count, rejected_count = excluded.rejected_count, run_tag = excluded.run_tag",
        (ключ_текста(текст), версия_модели, версия_промпта, ответ, токенов_вход, токенов_выход, мс,
         навыков, отброшено, прогон, datetime.now().isoformat(sep=" ")),
    )


def траты(conn: sqlite3.Connection, прогон: Optional[str] = None) -> Dict[str, Any]:
    """Во что обошлись разборы — по одному прогону или по всем."""
    условие, параметры = ("WHERE run_tag = ?", (прогон,)) if прогон else ("", ())
    строка = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(tokens_in), 0), COALESCE(SUM(tokens_out), 0), COALESCE(SUM(duration_ms), 0), "
        f"COALESCE(SUM(skills_count), 0), COALESCE(SUM(rejected_count), 0) FROM ai_extractions {условие}",
        параметры,
    ).fetchone()
    return {
        "вызовов": строка[0], "токенов_вход": строка[1], "токенов_выход": строка[2],
        "секунд": round(строка[3] / 1000, 1), "навыков": строка[4], "отброшено": строка[5],
    }
