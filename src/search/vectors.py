"""
Поиск по смыслу: векторы локальной модели.

Модель превращает текст в набор чисел так, что близкие по смыслу тексты
оказываются рядом. Запрос «удалёнка, интерьеры, рендер» находит
вакансию визуализатора, в которой нет ни одного из этих слов буквально.

**Всё локально.** Модель работает на видеокарте этой машины; тексты
вакансий никуда не уходят и ничего не стоят.

**Слой необязателен.** Модель — это два гигабайта, PyTorch и
видеокарта. На машине без них, в тестах и в проверке на GitHub
векторов нет, и поиск идёт по словам. Поэтому тяжёлые библиотеки
подключаются при первом обращении, а не при импорте модуля, а их
отсутствие — обычный исход, не ошибка.

**Версия модели хранится рядом с вектором.** Векторы разных моделей
несравнимы: числа те же по форме и бессмысленны вместе. Смена модели
пересчитывает векторы, а не смешивает их.

Отдельной векторной базы нет намеренно: десять тысяч векторов — это
двадцать мегабайт, и перемножить их с запросом быстрее, чем сходить в
другой сервис.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from src.search.документ import Документ
from src.utils import get_logger

logger = get_logger(__name__)

# Модель по умолчанию. Выбрана замером на эталоне (см. data-issues.md),
# а не по обзорам; меняется переменной SEARCH_MODEL.
МОДЕЛЬ_ПО_УМОЛЧАНИЮ = "BAAI/bge-m3"

# Как модель ждёт текст и как из её ответа получается вектор. У каждой
# семьи свои правила, и перепутать их — значит получить векторы, которые
# выглядят как настоящие и ищут хуже.
ПРАВИЛА_МОДЕЛЕЙ: Dict[str, Dict[str, object]] = {
    "BAAI/bge-m3": {"свёртка": "первый", "запрос": "", "документ": "", "порог": 0.50},
    "intfloat/multilingual-e5-base": {"свёртка": "среднее", "запрос": "query: ", "документ": "passage: ", "порог": 0.80},
    "intfloat/multilingual-e5-large": {"свёртка": "среднее", "запрос": "query: ", "документ": "passage: ", "порог": 0.80},
}


def порог_близости(модель: str) -> float:
    """
    Наименьшая близость, с которой вакансия считается найденной по смыслу.

    Модель всегда возвращает «ближайшие», даже на бессмыслицу. У BGE-M3
    порог откалиброван по эталону: бессмысленный запрос даёт близость до
    0,46, у подходящих вакансий девять из десяти выше 0,54 — граница
    0,50 отсекает первое и почти не трогает второе. У E5 числа лежат в
    другом, узком диапазоне, и её порог выставлен по тому же принципу,
    но на эталоне не проверялся.

    Чего порог не умеет: отличить «в базе этого нет» от «это есть».
    Запрос «сантехник» при полном отсутствии сантехников даёт близость
    0,58 — как у настоящих находок.
    """
    return float(ПРАВИЛА_МОДЕЛЕЙ.get(модель, {}).get("порог", 0.0))


# Сколько частей слова читает модель. Больше — дольше и почти без
# пользы: суть вакансии в названии, навыках и первых абзацах.
ДЛИНА_ТЕКСТА = 512

СХЕМА = """
CREATE TABLE IF NOT EXISTS search_vectors (
    vacancy_id   TEXT NOT NULL,
    model        TEXT NOT NULL,
    fingerprint  TEXT NOT NULL,
    vec          BLOB NOT NULL,
    PRIMARY KEY (vacancy_id, model)
);
"""

# Что кодирует тексты: (тексты, это запрос?) -> матрица векторов.
Кодировщик = Callable[[Sequence[str], bool], np.ndarray]


def имя_модели() -> str:
    return os.getenv("SEARCH_MODEL", МОДЕЛЬ_ПО_УМОЛЧАНИЮ)


class МодельНедоступна(RuntimeError):
    """Модель векторов не удалось поднять: нет библиотек, файлов или памяти."""


class ЛокальнаяМодель:
    """
    Модель векторов на этой машине.

    Поднимается при первом вызове: загрузка — секунды и гигабайты
    памяти видеокарты, и платить их при старте приложения ради экранов,
    где поиска нет, незачем.
    """

    def __init__(self, имя: Optional[str] = None, пачка: int = 32) -> None:
        self.имя = имя or имя_модели()
        self.пачка = пачка
        self._модель = None
        self._разбор = None
        self._устройство = "cpu"

    def _поднять(self) -> None:
        if self._модель is not None:
            return
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as ошибка:
            raise МодельНедоступна(f"нет библиотек для модели векторов: {ошибка}") from ошибка

        try:
            # Только с диска: поиск не должен ходить в сеть за моделью
            # посреди запроса. Скачивание — отдельная команда.
            self._разбор = AutoTokenizer.from_pretrained(self.имя, local_files_only=True)
            модель = AutoModel.from_pretrained(self.имя, local_files_only=True)
        except Exception as ошибка:
            raise МодельНедоступна(
                f"модель {self.имя} не найдена на диске: {type(ошибка).__name__}"
            ) from ошибка

        self._устройство = "cuda" if torch.cuda.is_available() else "cpu"
        if self._устройство == "cuda":
            # Половинная точность: вдвое меньше памяти видеокарты и
            # быстрее, на порядке выдачи это не сказывается.
            модель = модель.half()
        self._модель = модель.to(self._устройство).eval()
        logger.info(f"Модель векторов поднята: {self.имя} на {self._устройство}")

    def __call__(self, тексты: Sequence[str], запрос: bool = False) -> np.ndarray:
        self._поднять()
        import torch

        правила = ПРАВИЛА_МОДЕЛЕЙ.get(self.имя, {"свёртка": "среднее", "запрос": "", "документ": ""})
        приставка = правила["запрос"] if запрос else правила["документ"]

        части: List[np.ndarray] = []
        for начало in range(0, len(тексты), self.пачка):
            пачка = [приставка + текст for текст in тексты[начало:начало + self.пачка]]
            вход = self._разбор(
                пачка, padding=True, truncation=True, max_length=ДЛИНА_ТЕКСТА, return_tensors="pt"
            ).to(self._устройство)
            with torch.inference_mode():
                слой = self._модель(**вход).last_hidden_state
            if правила["свёртка"] == "первый":
                свёрнутое = слой[:, 0]
            else:
                маска = вход["attention_mask"].unsqueeze(-1).to(слой.dtype)
                свёрнутое = (слой * маска).sum(1) / маска.sum(1).clamp(min=1)
            свёрнутое = torch.nn.functional.normalize(свёрнутое.float(), dim=-1)
            части.append(свёрнутое.cpu().numpy())

        return np.vstack(части) if части else np.zeros((0, 0), dtype=np.float32)


# ---------------------------------------------------------------------------
# Хранение
# ---------------------------------------------------------------------------

def создать(conn: sqlite3.Connection) -> None:
    conn.executescript(СХЕМА)


def досчитать(
    conn: sqlite3.Connection,
    документы: Iterable[Документ],
    кодировщик: Кодировщик,
    модель: str,
    пачка: int = 256,
) -> Dict[str, int]:
    """
    Посчитать векторы тем документам, у которых их нет или текст изменился.

    Returns:
        `{"посчитано": n, "без_изменений": n}`. Второе число — то, ради
        чего у вектора хранится отпечаток текста: повторный запуск после
        сбора считает сотню новых вакансий, а не всю базу.
    """
    создать(conn)
    известные = dict(conn.execute(
        "SELECT vacancy_id, fingerprint FROM search_vectors WHERE model = ?", (модель,)
    ))

    очередь = [д for д in документы if известные.get(д.ид) != д.отпечаток()]
    всего = None
    for начало in range(0, len(очередь), пачка):
        часть = очередь[начало:начало + пачка]
        векторы = кодировщик([д.для_смысла() for д in часть], False)
        conn.executemany(
            "INSERT OR REPLACE INTO search_vectors (vacancy_id, model, fingerprint, vec) VALUES (?, ?, ?, ?)",
            [
                (д.ид, модель, д.отпечаток(), np.asarray(вектор, dtype=np.float16).tobytes())
                for д, вектор in zip(часть, векторы)
            ],
        )
        conn.commit()
        всего = (всего or 0) + len(часть)

    _индексы.pop((_база(conn), модель), None)
    return {"посчитано": len(очередь), "без_изменений": len(известные) - sum(1 for д in очередь if д.ид in известные)}


def убрать(conn: sqlite3.Connection, идентификаторы: Iterable[str]) -> None:
    try:
        conn.executemany("DELETE FROM search_vectors WHERE vacancy_id = ?", [(str(ид),) for ид in идентификаторы])
    except sqlite3.OperationalError:
        return
    for ключ in [ключ for ключ in _индексы if ключ[0] == _база(conn)]:
        _индексы.pop(ключ, None)


# ---------------------------------------------------------------------------
# Индекс в памяти
# ---------------------------------------------------------------------------

@dataclass
class Индекс:
    """Векторы одной модели в памяти: идентификаторы и матрица."""

    идентификаторы: List[str]
    матрица: np.ndarray

    def __len__(self) -> int:
        return len(self.идентификаторы)

    def ближайшие(
        self, вектор: np.ndarray, сколько: int = 200, допустимые: Optional[set] = None
    ) -> List[Tuple[str, float]]:
        """Вакансии, ближайшие к вектору запроса, с мерой близости."""
        if not len(self):
            return []
        близость = self.матрица @ np.asarray(вектор, dtype=np.float32).ravel()
        if допустимые is not None:
            маска = np.fromiter((ид in допустимые for ид in self.идентификаторы), dtype=bool, count=len(self))
            близость = np.where(маска, близость, -np.inf)

        сколько = min(сколько, len(self))
        лучшие = np.argpartition(-близость, сколько - 1)[:сколько]
        лучшие = лучшие[np.argsort(-близость[лучшие])]
        return [(self.идентификаторы[i], float(близость[i])) for i in лучшие if np.isfinite(близость[i])]


_индексы: Dict[Tuple[str, str], Tuple[tuple, Индекс]] = {}


def _база(conn: sqlite3.Connection) -> str:
    строка = conn.execute("PRAGMA database_list").fetchone()
    return строка[2] or f"память:{id(conn)}"


def индекс(conn: sqlite3.Connection, модель: str) -> Индекс:
    """
    Индекс модели; читается один раз на состояние таблицы.

    Состояние узнаётся по числу строк и наибольшему номеру: векторы
    досчитывает и сбор, и отдельная команда, и индекс, поднятый до них,
    не знал бы новых вакансий.
    """
    try:
        штамп = tuple(conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(rowid), 0) FROM search_vectors WHERE model = ?", (модель,)
        ).fetchone())
    except sqlite3.OperationalError:
        return Индекс([], np.zeros((0, 0), dtype=np.float32))

    ключ = (_база(conn), модель)
    запомненное = _индексы.get(ключ)
    if запомненное is None or запомненное[0] != штамп:
        строки = conn.execute(
            "SELECT vacancy_id, vec FROM search_vectors WHERE model = ? ORDER BY rowid", (модель,)
        ).fetchall()
        if строки:
            матрица = np.vstack([np.frombuffer(тело, dtype=np.float16) for _, тело in строки]).astype(np.float32)
        else:
            матрица = np.zeros((0, 0), dtype=np.float32)
        _индексы[ключ] = (штамп, Индекс([ид for ид, _ in строки], матрица))
    return _индексы[ключ][1]
