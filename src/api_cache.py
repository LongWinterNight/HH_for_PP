"""
Кэш ответов источника.

Повторный запуск сбора по тем же запросам не ходит в сеть заново: ответы
поиска лежат в отдельной базе data/api_cache.db со сроком годности.

Кэш ускоряет повторы, но он же способен выдать вчерашние данные за
сегодняшний сбор — поэтому включение кэша решает тот, кто запускает
сбор, а не сам кэш.

**Выдача и карточка живут по-разному, и сроки у них разные.** Страница
выдачи меняется быстро: работодатель публикует вакансию утром, и
вечерний сбор по вчерашнему кэшу её не увидит. Карточка почти не
меняется — текст правят редко, а зарплата и статус приходят из выдачи.
Один срок на двоих означал выбор между несвежей выдачей и лишними
тысячами обращений за карточками; теперь их два, и оба живут в
настройках, а не в теле вызова.
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import settings
from src.utils import get_logger, ensure_dir

logger = get_logger(__name__)


class APICache:
    """
    Кэширование ответов HH API в SQLite.
    
    Ускоряет повторные запуски — не делает запросы для тех же параметров.
    """
    
    def __init__(self, cache_db: Path = None):
        self.cache_db = cache_db or settings.db_path.parent / "api_cache.db"
        ensure_dir(self.cache_db.parent)
        self._init_db()
    
    def _init_db(self):
        """Инициализация таблицы кэша."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_cache (
                    cache_key TEXT PRIMARY KEY,
                    response TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON api_cache(expires_at)")
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Контекстный менеджер для подключения."""
        conn = sqlite3.connect(str(self.cache_db))
        try:
            yield conn
        finally:
            conn.close()
    
    def _generate_key(
        self,
        keyword: str,
        page: int,
        per_page: int,
        area: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> str:
        """
        Уникальный ключ запроса.

        В ключ входит всё, что меняет ответ источника. Раньше это были
        только запрос, страница и размер страницы — а регион и нижняя
        граница даты в него не попадали. Один и тот же «Рекрутер»,
        запрошенный по Москве и по всей стране, читался из одной ячейки
        кэша: срез отдавал чужой ответ, и резка запроса на срезы (S4‑2)
        молча возвращала бы одни и те же вакансии.

        Значения по умолчанию оставлены пустыми, чтобы ключи запросов
        без среза не менялись: накопленный кэш остаётся годным.
        """
        key_string = f"search:{keyword}:{page}:{per_page}"
        if area:
            key_string += f":area={area}"
        if date_from:
            key_string += f":from={date_from}"
        if date_to:
            key_string += f":to={date_to}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def получить_карточку(self, идентификатор: str) -> Optional[Dict]:
        """
        Карточка вакансии из кэша.

        Карточка запрашивается на каждую новую вакансию — это тысячи
        обращений на сбор и почти всё его время. Кэшировать её выгоднее
        всего, и срок ей нужен свой: неделя против шести часов у выдачи.
        """
        return self._прочитать(f"card:{идентификатор}")

    def сохранить_карточку(self, идентификатор: str, ответ: Dict) -> None:
        self._записать(f"card:{идентификатор}", ответ, settings.кэш_карточек_часов)

    def _прочитать(self, ключ: str) -> Optional[Dict]:
        """Запись кэша по готовому ключу, если она ещё не протухла."""
        ключ_хэш = hashlib.md5(ключ.encode()).hexdigest()
        with self._get_connection() as conn:
            строка = conn.execute(
                "SELECT response, expires_at FROM api_cache WHERE cache_key = ?",
                (ключ_хэш,),
            ).fetchone()
        if not строка:
            return None
        ответ, годен_до = строка
        if годен_до and datetime.fromisoformat(годен_до) < datetime.now():
            return None
        return json.loads(ответ)

    def _записать(self, ключ: str, ответ: Dict, часов: int) -> None:
        ключ_хэш = hashlib.md5(ключ.encode()).hexdigest()
        годен_до = (datetime.now() + timedelta(hours=часов)).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO api_cache (cache_key, response, expires_at) "
                "VALUES (?, ?, ?)",
                (ключ_хэш, json.dumps(ответ, ensure_ascii=False), годен_до),
            )
            conn.commit()

    def get(
        self,
        keyword: str,
        page: int,
        per_page: int = 100,
        area: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Optional[Dict]:
        """Получение ответа из кэша."""
        cache_key = self._generate_key(keyword, page, per_page, area, date_from, date_to)
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT response, expires_at FROM api_cache WHERE cache_key = ?",
                (cache_key,)
            )
            row = cursor.fetchone()
            
            if row:
                response, expires_at = row
                # Протухшая запись — как отсутствующая: срок у выдачи
                # и карточки разный, и записан он в самой записи.
                if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
                    return None
                return json.loads(response)
        
        return None
    
    def set(
        self,
        keyword: str,
        page: int,
        response: Dict,
        ttl_hours: Optional[int] = None,
        area: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ):
        """
        Сохранение страницы выдачи в кэш.

        Срок берётся из настроек, а не из вызова: раньше здесь стояло
        `ttl_hours=24`, и поменять его можно было только правкой кода.
        Явный аргумент оставлен для тех, кто знает, чего хочет.
        """
        cache_key = self._generate_key(keyword, page, 100, area, date_from, date_to)
        часов = ttl_hours if ttl_hours is not None else settings.кэш_выдачи_часов
        expires_at = (datetime.now() + timedelta(hours=часов)).isoformat()
        
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO api_cache 
                   (cache_key, response, expires_at) VALUES (?, ?, ?)""",
                (cache_key, json.dumps(response, ensure_ascii=False), expires_at)
            )
            conn.commit()
    
    def clear_old(self, days: int = 7):
        """
        Очистка кэша по возрасту записи.

        Оставлена для ручной уборки «всё, что старше недели». Обычная
        же уборка идёт по сроку годности — `убрать_протухшие`: запись,
        которую всё равно никто не прочитает, незачем держать до
        семидневного возраста.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM api_cache WHERE created_at < ?",
                (cutoff,)
            )
            conn.commit()
            logger.info(f"Очищено {cursor.rowcount} старых записей кэша")

    def убрать_протухшие(self) -> int:
        """
        Удалить записи, срок годности которых вышел.

        Зачем отдельно от `clear_old`. Протухшая запись уже бесполезна:
        `get` её не отдаёт, а место она занимает. Файл кэша рос
        бесконечно, потому что уборка была только ручная и по возрасту —
        а срок годности у выдачи шесть часов, и запись становится
        мусором задолго до семи дней.

        Returns:
            Сколько записей удалено.
        """
        сейчас = datetime.now().isoformat()
        with self._get_connection() as conn:
            курсор = conn.execute(
                "DELETE FROM api_cache WHERE expires_at IS NOT NULL AND expires_at < ?",
                (сейчас,),
            )
            conn.commit()
            удалено = курсор.rowcount
        if удалено:
            logger.info(f"Кэш: убрано протухших записей — {удалено}")
        return удалено
    
    def get_stats(self) -> Dict[str, Any]:
        """Статистика кэша."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM api_cache")
            count = cursor.fetchone()[0]
            
            cursor = conn.execute(
                "SELECT SUM(length(response)) FROM api_cache"
            )
            size = cursor.fetchone()[0] or 0
            
            return {
                "entries": count,
                "size_bytes": size,
                "size_mb": round(size / 1024 / 1024, 2)
            }
