"""
Модуль для хранения данных в SQLite (ETL Load).

Содержит класс VacancyStorage, который:
- Создаёт схему базы данных
- Сохраняет обработанные вакансии
- Реализует историю изменений (upsert логика)
- Предоставляет методы для выборки данных
- Управляет журналом парсингов и настройками приложения

Важно: SQLite подходит для локальной разработки и небольших объёмов.
Для продакшена рассмотрите PostgreSQL или ClickHouse.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    # Только для подсказок типов: при обычном импорте вышел бы круг.
    from src.cbr_rates import Курсы
import json

import pandas as pd
from sqlalchemy import (
    create_engine,
    Column,
    LargeBinary,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import declarative_base, Session
from sqlalchemy.exc import SQLAlchemyError

from src.config import settings
from src.salary_sanity import причина_сомнения, только_правдоподобные
from src.utils import get_logger, ensure_dir

# Инициализируем логгер для модуля
logger = get_logger(__name__)

# Базовый класс для ORM моделей
Base = declarative_base()


# =============================================================================
# Модели БД
# =============================================================================

class VacancyTextModel(Base):
    """
    Описание вакансии: тело, отпечаток, дата получения.

    Отдельная таблица, а не колонка вакансии. Три причины, и все три
    проявляются на масштабе: аналитика текст не читает никогда, и шесть
    килобайт в строке замедляли бы каждое сканирование; дедупликация по
    хэшу возможна только при отдельной таблице — тридцать одна копия
    объявления по городам хранит один текст; при переезде на Postgres
    такую таблицу можно вынести первой, не трогая аналитику.

    Ключ — хэш текста, а не идентификатор вакансии. Тот же хэш служит
    ключом кэша разбора моделью (S10‑5a): одна сущность вместо двух.
    """

    __tablename__ = "vacancy_texts"

    text_hash = Column(String(64), primary_key=True)
    # Тело, сжатое zlib. Замер: вчетверо, 5,8 КБ → 1,45 КБ.
    body = Column(LargeBinary, nullable=False)
    # Что лежит в теле. HTML, а не очищенный текст: по тегам разбираются
    # секции описания, и без них переразобрать их будет нечем.
    format = Column(String(10), nullable=False, default="html")
    # Отпечаток для сравнения похожих описаний между площадками (S12).
    simhash = Column(Integer)
    # Размер до сжатия: по нему видно, растёт ли хранилище.
    bytes_raw = Column(Integer)
    # Текст объявления — снимок на момент сбора: работодатель правит
    # вакансию, и наш экземпляр стареет.
    fetched_at = Column(DateTime, nullable=False, default=datetime.now, index=True)

    def __repr__(self) -> str:
        return f"<VacancyText {self.text_hash[:12]}… {self.bytes_raw} байт>"


class VacancyModel(Base):
    """
    ORM модель для таблицы вакансий.

    Соответствует таблице 'vacancies' в SQLite.
    Содержит все основные поля для анализа.
    """

    __tablename__ = "vacancies"

    # Первичный ключ
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Откуда запись. Часть ключа: идентификаторы у разных источников
    # свои, и «137176862» с hh.ru не имеет отношения к «137176862» с
    # другого сайта. Уникальность стоит на паре (source, vacancy_id) —
    # см. миграцию 017.
    source = Column(String(50), nullable=False, default="hh.ru", index=True)

    # Идентификатор вакансии у источника. Уникален внутри источника, но
    # не сам по себе.
    vacancy_id = Column(String(50), nullable=False, index=True)

    # Основная информация
    vacancy_name = Column(String(500), nullable=False)
    published_at = Column(DateTime)
    applied_at = Column(DateTime)

    # Навыки (хранятся как строки через запятую)
    all_skills = Column(Text)
    hard_skills = Column(Text)
    soft_skills = Column(Text)
    tools = Column(Text)

    # Навыки, которые работодатель назвал сам, в отдельном поле вакансии.
    #
    # Это не догадка по тексту, а прямое утверждение, и хранится оно
    # отдельно по двум причинам. Первая: по нему видно, что пришло от
    # источника, а что нашли мы, — без этого нельзя объяснить, откуда
    # взялся навык. Вторая: 77 % таких навыков нет в наших словарях, и
    # раскладывать их по hard/soft/tools не по чему — категорию мы
    # знаем только для знакомых.
    employer_skills = Column(Text)

    # Ссылка на описание. Сам текст лежит в отдельной таблице: аналитика
    # его не читает никогда, а шесть килобайт в каждой строке замедляли
    # бы любое сканирование ради того, что нужно только переразбору.
    text_hash = Column(String(64), index=True)

    # Счётчики навыков
    skill_count = Column(Integer, default=0)
    hard_skill_count = Column(Integer, default=0)
    soft_skill_count = Column(Integer, default=0)
    tools_count = Column(Integer, default=0)

    # Зарплата
    salary_from = Column(Float)
    salary_to = Column(Float)
    salary_currency = Column(String(10), default="RUB")
    salary_gross = Column(Boolean, default=False)

    # Период выплаты по справочнику hh.ru: MONTH, HOUR, SHIFT,
    # FLY_IN_FLY_OUT, SERVICE. Пусто — источник периода не назвал, и
    # выдумывать месяц вместо него нельзя: на этой выдумке считались бы
    # медианы (`src/salary_mode.py`).
    salary_mode = Column(String(20), nullable=True)
    # Причина, по которой числу нельзя верить: «18 EUR», «400 UZS»,
    # «от 50 до 100 000 ₽». Пусто — с зарплатой всё в порядке. Запись не
    # удаляется, но в минимум, медиану и среднюю не попадает
    # (`src/salary_sanity.py`, docs/data-issues.md, запись 13).
    salary_doubt = Column(String(60), nullable=True)

    # Рублёвый эквивалент нижней и верхней границы: 19 000 000 сум и
    # 300 000 рублей человеку не сравнить, пока они в своих валютах.
    # Пусто — валюты нет в котировках ЦБ; ноль здесь был бы враньём,
    # потому что выглядит как настоящее число.
    salary_from_rub = Column(Float, nullable=True)
    salary_to_rub = Column(Float, nullable=True)

    # Дата курса, по которому считан эквивалент. Хранится рядом с числом,
    # потому что подпись на экране обязана её называть: без даты «≈ 139 000 ₽»
    # ничем не подтверждено.
    rate_date = Column(DateTime, nullable=True)

    # Работодатель
    employer_name = Column(String(300))
    employer_id = Column(String(50))
    employer_url = Column(String(500))

    # Ссылка на вакансию
    vacancy_url = Column(String(500))

    # Опыт работы и занятость
    experience = Column(String(100))
    employment = Column(String(100))
    schedule = Column(String(100))

    # Регион
    area = Column(String(200))

    # Метаданные загрузки
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Жизненный цикл вакансии (миграция 002).
    #
    # Дата публикации и дата первой встречи — разные величины: вакансия
    # могла быть опубликована в марте, а попасть в базу в сентябре.
    # Динамика строится по first_seen_at, иначе прирост базы выдаёт себя
    # за появление вакансий на рынке.
    first_seen_at = Column(DateTime)
    last_seen_at = Column(DateTime)

    # Источник перестал отдавать вакансию — она не удаляется, а гаснет:
    # архив нужен для истории, но в текущих числах ему делать нечего.
    is_active = Column(Boolean, default=True)

    # Найдена не по запросу: слов запроса нет ни в названии, ни в
    # описании, ни в навыках — источник нашёл их в названии компании.
    # Такая вакансия не удаляется, а пропускается аналитикой и списком:
    # правило, по которому она узнаётся, приближённое (src/relevance.py).
    off_query = Column(Integer, default=0, index=True)

    # Каким запросом найдена. Запросов может быть несколько: одна
    # вакансия попадает и в «Python», и в «Backend developer».
    source_keyword = Column(String(500))

    # Собрано ли описание вакансии. Навыки ищутся по описанию, поэтому
    # без этого признака непонятно, по какой доле выборки посчитана
    # статистика навыков.
    has_details = Column(Boolean, default=False)

    # Индексы для ускорения поиска.
    #
    # Отдельного индекса по vacancy_id здесь нет: колонка объявлена как
    # unique=True, index=True, и SQLAlchemy сама создаёт по ней уникальный
    # ix_vacancies_vacancy_id. Второй индекс по тому же полю добавлял бы
    # работу на каждой записи, ничего не ускоряя. Тот же набор создаёт
    # миграция 001 — списки должны совпадать.
    __table_args__ = (
        Index("idx_employer", "employer_name"),
        Index("idx_area", "area"),
        Index("idx_published_at", "published_at"),
        Index("idx_experience", "experience"),
        Index("idx_salary_from", "salary_from"),
        Index("idx_created_at", "created_at"),
        Index("idx_salary_currency", "salary_currency"),
        Index("idx_is_active", "is_active"),
        Index("idx_first_seen_at", "first_seen_at"),
        # Вакансия узнаётся по паре: у разных источников идентификаторы
        # свои и совпадают между собой (миграция 017).
        UniqueConstraint("source", "vacancy_id", name="ux_vacancies_source_vacancy"),
    )

    def __repr__(self) -> str:
        """Строковое представление для отладки."""
        return f"<Vacancy(id={self.vacancy_id}, name='{self.vacancy_name[:50]}...')>"


# Колонки, которые повторная встреча вакансии не трогает.
# Чем помечаются записи, у которых источник не назван. Все такие
# записи собраны с hh.ru: другого источника у продукта не было, и это
# факт, а не догадка. Значение то же, что в миграции 017.
ИСТОЧНИК_ПО_УМОЛЧАНИЮ = "hh.ru"

SKIP_ON_UPDATE = {"created_at"}

# Даты жизненного цикла в базе записаны в двух видах: с микросекундами и
# без. Так вышло само — datetime.now() их даёт, а разобранная дата из
# файла сбора нет, — и обе строки лежат в одной колонке.
#
# Для pandas это ловушка. `to_datetime` выводит единый формат по первым
# строкам и на остальных возвращает NaT, а с errors="coerce" делает это
# молча: на живой базе так терялось 352 записи из 1891 — девятнадцать
# процентов, которые просто не доезжали до расчётов. Разбор поэтому
# делается здесь, один раз на чтении, а не в каждом месте, где нужна
# дата: место для такой ошибки должно быть одно.
ДАТЫ_ЗАПИСИ = ("created_at", "updated_at", "first_seen_at", "last_seen_at")


def _разобрать_даты(df: pd.DataFrame) -> pd.DataFrame:
    """Даты жизненного цикла — настоящими датами, без молчаливых потерь."""
    for колонка in ДАТЫ_ЗАПИСИ:
        if колонка in df.columns:
            df[колонка] = pd.to_datetime(df[колонка], errors="coerce", format="mixed")
    return df

# Колонки, которые при повторной встрече сливаются, а не замещаются.
# Ключ — имя колонки, значение — выражение для ON CONFLICT DO UPDATE SET.
#
# Правила устроены так, чтобы порядок записи не имел значения: живой сбор
# приносит свежие даты, восстановление истории — старые, и ни один из них
# не должен испортить работу другого.
MERGE_RULES = {
    # Первая встреча — самая ранняя из известных. При обычном сборе это
    # оставляет прежнюю дату (она раньше сегодняшней), при разборе старых
    # файлов — сдвигает её назад, к настоящему первому появлению.
    "first_seen_at": (
        "first_seen_at = MIN("
        "COALESCE(vacancies.first_seen_at, excluded.first_seen_at),"
        " COALESCE(excluded.first_seen_at, vacancies.first_seen_at))"
    ),

    # Последняя встреча — самая поздняя. Запись из архива не должна
    # объявить, что вакансию давно не видели.
    "last_seen_at": (
        "last_seen_at = MAX("
        "COALESCE(vacancies.last_seen_at, excluded.last_seen_at),"
        " COALESCE(excluded.last_seen_at, vacancies.last_seen_at))"
    ),

    # Собранное однажды описание не исчезает оттого, что в этот раз
    # страницу не детализировали: иначе доля выборки с навыками скакала
    # бы от сбора к сбору без всякой связи с данными.
    "has_details": "has_details = MAX(COALESCE(vacancies.has_details, 0), COALESCE(excluded.has_details, 0))",

    # Раз источник снова отдал вакансию, она жива — но только если эта
    # запись свежее той, что уже лежит в базе. Разбор архива приносит
    # вакансии, закрытые полгода назад: воскрешать их нельзя.
    "is_active": (
        "is_active = CASE WHEN COALESCE(excluded.last_seen_at, '')"
        " >= COALESCE(vacancies.last_seen_at, '')"
        " THEN excluded.is_active ELSE vacancies.is_active END"
    ),

    # Запросы накапливаются: одна вакансия находится и по «Python», и по
    # «Backend developer», и знать нужно оба. Повтор не дублируется,
    # переполнение поля не наращивается — лучше потерять редкий третий
    # запрос, чем обрезать строку посреди слова.
    "source_keyword": (
        "source_keyword = CASE"
        " WHEN excluded.source_keyword IS NULL OR excluded.source_keyword = ''"
        " THEN vacancies.source_keyword"
        " WHEN vacancies.source_keyword IS NULL OR vacancies.source_keyword = ''"
        " THEN excluded.source_keyword"
        " WHEN instr(', ' || vacancies.source_keyword || ', ',"
        " ', ' || excluded.source_keyword || ', ') > 0"
        " THEN vacancies.source_keyword"
        " WHEN length(vacancies.source_keyword) + length(excluded.source_keyword) + 2 > 500"
        " THEN vacancies.source_keyword"
        " ELSE vacancies.source_keyword || ', ' || excluded.source_keyword"
        " END"
    ),
}


class ParserRunModel(Base):
    """
    ORM модель для таблицы журнала парсингов.

    Хранит историю всех запусков парсера с параметрами и результатами.
    """

    __tablename__ = "parser_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Время запуска и завершения
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)

    # Статус: running, completed, error, stopped
    status = Column(String(20), default="running")

    # Параметры парсера
    keywords = Column(Text)  # JSON массив ключевых слов
    max_pages = Column(Integer, default=10)
    days_back = Column(Integer, default=30)
    is_incremental = Column(Boolean, default=True)
    use_cache = Column(Boolean, default=True)

    # Результаты
    vacancies_collected = Column(Integer, default=0)
    vacancies_new = Column(Integer, default=0)
    vacancies_updated = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    error_message = Column(Text)

    # Причина отказа отдельным полем (миграция 005): по типу интерфейс
    # выбирает, что показать и что предложить сделать. Текст исключения
    # для этого не годится — из него не следует ни причина, ни действие.
    error_type = Column(String(50))

    # Ход работы (миграция 004).
    #
    # Прогресс живёт в базе, а не в памяти процесса: сбор идёт фоновой
    # задачей, и перезапуск сервера уносил состояние с собой — запись
    # оставалась «running» навсегда, а интерфейс показывал «сбора нет».
    progress_percent = Column(Integer, default=0)
    current_keyword = Column(String(500))
    current_page = Column(Integer, default=0)
    found_estimate = Column(Integer)

    # Качество сбора (миграция 015).
    #
    # «Собрано 1 891» не говорит, годятся ли записи для аналитики.
    # Вакансия без карточки несёт 2,4 навыка против 14,7 у той, где
    # карточка есть; неполный обход даёт недобор. Числа хранятся по
    # каждому запуску: по базе задним числом их не восстановить — там
    # записи всех сборов сразу, и ухудшение одного в них тонет.
    q_with_details = Column(Integer)
    q_without_skills = Column(Integer)
    q_incomplete = Column(Integer)

    # Состояние обхода (миграция 016): какие запросы пройдены целиком,
    # какой шёл в момент обрыва. Одним JSON, а не колонками: устройство
    # обхода меняется (срезы по регионам, окна дат), и каждая перемена
    # стоила бы миграции.
    progress_state = Column(Text)

    # Отметка живости: по ней видно, что процесс сбора ещё дышит.
    # Запись со старой отметкой и статусом «running» — это след
    # оборвавшегося сбора, а не идущая работа.
    heartbeat_at = Column(DateTime)

    # Метаданные
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<ParserRun(id={self.id}, status='{self.status}', collected={self.vacancies_collected})>"


class RunQueryModel(Base):
    """
    Что принёс каждый поисковый запрос в рамках одного сбора.

    Итог сбора отвечает на вопрос «сколько собрали», но не на вопрос
    «почему так мало». Разбивка по запросам показывает, какой из них упал
    на отказе источника, какой прочитан не до конца, а какой не принёс
    ничего нового — и это разные события, которые в общем числе
    неразличимы.
    """

    __tablename__ = "run_queries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False, index=True)

    keyword = Column(String(500), nullable=False)

    # complete — выдача прочитана до конца; partial — упёрлись в предел
    # страниц, остановку или ошибку.
    status = Column(String(20), default="partial")

    # Сколько вакансий источник обещал по этому запросу. Заполняется,
    # когда сбор начнёт читать поле `found` из ответа (задача 2.4.4).
    found = Column(Integer)

    # Сколько записей выдачи мы по этому запросу реально прочитали.
    # Сравнимо с `found`, в отличие от vacancies_new и vacancies_updated:
    # те считают изменения в базе, и вакансия, уже встреченная по другому
    # запросу, в них не попадает. Разрыв found − taken — это то, чего мы
    # не увидели из-за предела глубины выдачи.
    taken = Column(Integer)

    pages = Column(Integer, default=0)
    vacancies_new = Column(Integer, default=0)
    vacancies_updated = Column(Integer, default=0)
    from_cache = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<RunQuery(run={self.run_id}, keyword='{self.keyword}', new={self.vacancies_new})>"


class MetricsSnapshotModel(Base):
    """
    Состояние базы на момент сбора.

    Тренды нельзя считать сравнением периодов внутри одного снимка базы:
    источник отдаёт только открытые вакансии, и чем старше день
    публикации, тем меньше его вакансий дожило до сбора. На реальных
    данных это давало «рост в восемьдесят раз» там, где на самом деле
    затухание архива.

    Снимок фиксирует числа на свою дату — два снимка сравнивать уже
    можно, и разница между ними означает ровно то, что написано.
    """

    __tablename__ = "metrics_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Момент, к которому относятся числа.
    taken_at = Column(DateTime, nullable=False, index=True)

    # Сбор, после которого сделан снимок. У восстановленных пусто.
    run_id = Column(Integer)

    # measured — посчитан по живой базе в момент сбора;
    # reconstructed — восстановлен по датам первой встречи задним числом.
    # Различать обязательно: у восстановленных нет зарплатных метрик, и
    # выдавать их за замер значило бы повторить ту самую ошибку, из-за
    # которой тренды и оказались недостоверными.
    source = Column(String(20), default="measured")

    # Счётные метрики — считаются и при реконструкции.
    active_vacancies = Column(Integer, default=0)
    total_vacancies = Column(Integer, default=0)
    unique_companies = Column(Integer, default=0)
    unique_regions = Column(Integer, default=0)

    # Зарплатные метрики — только у замеров. В базе хранится последнее
    # известное значение зарплаты, истории значений нет, поэтому у
    # восстановленных снимков эти поля пустые.
    with_salary = Column(Integer)
    median_salary_rub = Column(Float)
    salary_sample_rub = Column(Integer)

    # Медианы по остальным валютам одной строкой JSON: валют семь, и
    # заводить под каждую по колонке значило бы менять схему при каждой
    # новой валюте источника.
    medians_by_currency = Column(Text)

    # Курс своего дня. Без него тренд по рублёвому эквиваленту посчитать
    # нельзя: пересчёт старого снимка сегодняшним курсом смешал бы два
    # движения — рынок и валюту, — и падение рубля выглядело бы ростом
    # зарплат. Хранится и дата, и сами котировки: медианы по валютам
    # лежат рядом, и, зная курс того дня, их можно привести к рублям
    # того же дня.
    rate_date = Column(DateTime)
    rates = Column(Text)

    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<Snapshot({self.taken_at:%Y-%m-%d}, {self.source}, active={self.active_vacancies})>"


class CurrencyRateModel(Base):
    """
    Официальный курс валюты на дату.

    Курс хранится, а не берётся у ЦБ на каждый запрос: источник чужой и
    бесплатный, курс за день не меняется, а при недоступности ЦБ
    показывать «эквивалента нет» вместо вчерашнего курса — хуже, чем
    честная подпись с датой.

    Значение приведено к одной единице валюты: у ЦБ курс даётся за 100
    тенге и за 10 000 сумов, и номинал снимается при разборе, чтобы о нём
    больше никто не помнил (`src/cbr_rates.py`).
    """

    __tablename__ = "currency_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)

    currency = Column(String(10), nullable=False)

    # Дата, которой курс принадлежит по ответу ЦБ. В выходной это
    # последний рабочий день — именно её и называет подпись на экране.
    rate_date = Column(DateTime, nullable=False)

    # Сколько рублей стоит одна единица валюты.
    value = Column(Float, nullable=False)

    # Когда мы этот курс забрали. Отличается от rate_date и нужна, чтобы
    # понимать, давно ли мы вообще ходили к источнику.
    fetched_at = Column(DateTime, nullable=False)

    __table_args__ = (
        # Курс за день — один. Повторный запрос в тот же день обновляет
        # запись, а не плодит копии.
        UniqueConstraint("currency", "rate_date", name="uq_currency_rate_date"),
        Index("idx_rate_date", "rate_date"),
    )

    def __repr__(self) -> str:
        return f"<CurrencyRate({self.currency} {self.value} на {self.rate_date})>"


def _разобрать_запросы(сырое: Optional[str]) -> Optional[List[str]]:
    """
    Список запросов из JSON-строки настроек.

    None означает «человек ничего не задавал» и отличается от пустого
    списка: в первом случае экран предложит заготовку, во втором
    покажет пустоту, которую человек сделал сам. Испорченная строка
    приравнивается к «не задано» — настройки не то место, где стоит
    падать из-за одного символа.
    """
    if not сырое:
        return None
    try:
        значение = json.loads(сырое)
    except (TypeError, ValueError):
        logger.warning("Список запросов в настройках не читается — считаем незаданным")
        return None
    if not isinstance(значение, list):
        return None
    return [str(з).strip() for з in значение if str(з).strip()]


class AppSettingsModel(Base):
    """
    ORM модель для таблицы настроек приложения.

    Синглтон-таблица (всегда одна запись с id=1).
    Хранит глобальные метаданные приложения.
    """

    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True)  # всегда 1

    # Парсинг
    last_parse_at = Column(DateTime)  # последний запуск (любой статус)
    last_successful_parse_at = Column(DateTime)  # последний успешный
    total_parses = Column(Integer, default=0)
    total_vacancies_collected = Column(Integer, default=0)

    # Настройки сбора (миграция 006).
    #
    # Раньше они жили в словаре в памяти и дублировались в .env, куда
    # почту дописывали заменой по регулярному выражению — способ, при
    # котором строка в комментарии попадает под замену наравне с
    # настоящей. База надёжнее, а окружение остаётся источником
    # первичных значений при первом запуске.
    #
    # Прокси здесь намеренно нет: строка подключения может содержать
    # пароль, а настройки видны всем, у кого есть доступ к сайту.
    hh_user_email = Column(String(200))
    request_delay = Column(Float, default=1.0)

    # Список запросов сбора в JSON (миграция 019). Раньше он правился в
    # конфиге, а на экране жил только в памяти вкладки: обновление
    # страницы стирало набранное. Пусто здесь означает «человек ничего
    # не задал» — это не то же самое, что пустой список.
    search_queries = Column(Text)

    # Версии
    app_version = Column(String(20), default="2.0.0")
    config_version = Column(String(20))

    # Метаданные
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<AppSettings(last_parse={self.last_successful_parse_at})>"


# =============================================================================
# Хранилище вакансий
# =============================================================================


class VacancyStorage:
    """
    Хранилище для вакансий в SQLite.

    Реализует:
    - Создание схемы БД при инициализации
    - Массовую загрузку данных из DataFrame
    - Upsert логику (обновление существующих записей)
    - Методы для выборки данных для аналитики

    Атрибуты:
        db_path (Path): Путь к файлу базы данных
        engine: SQLAlchemy движок
        session: Сессия SQLAlchemy

    Пример использования:
        >>> storage = VacancyStorage()
        >>> storage.replace_all_vacancies(df)
        >>> vacancies = storage.get_all_vacancies()
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """
        Инициализация хранилища.

        Args:
            db_path: Путь к файлу БД. Если None, берётся из конфига

        Note:
            При первом запуске создаётся схема базы данных.
            Директория для БД создаётся автоматически.
        """
        self.db_path = db_path or settings.db_path

        # Когда в последний раз писали ход каждого сбора: по нему
        # прореживается запись прогресса.
        self._last_progress_write: Dict[int, datetime] = {}

        # Причина, по которой тексты описаний не записались в последней
        # записи вакансий. Пусто — записались. Сбор читает её и называет
        # в записи запуска.
        self.отказ_текстов: Optional[str] = None

        # Создаём директорию если её нет
        ensure_dir(self.db_path.parent)

        # Создаём SQLite движок
        # sqlite:/// — префикс для SQLite
        # echo=False — отключить логирование SQL запросов
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            # Оптимизации для SQLite
            connect_args={"check_same_thread": False}
        )

        # Создаём схему БД (таблицы)
        self._create_tables()

        # Инициализируем настройки (создаём запись если нет)
        self.initialize_settings()

        logger.info(f"VacancyStorage инициализирован. БД: {self.db_path}")

    def _create_tables(self) -> None:
        """
        Создание таблиц в базе данных.

        Вызывается один раз при инициализации.
        Если таблицы уже существуют — ничего не делает.
        """
        try:
            # Используем checkfirst=True для проверки существования таблиц
            Base.metadata.create_all(self.engine, checkfirst=True)
            logger.debug("Таблицы созданы или уже существуют")
        except SQLAlchemyError as e:
            # Игнорируем ошибку если таблица уже существует
            if "already exists" not in str(e):
                logger.error(f"Ошибка создания таблиц: {e}")
                raise
            logger.debug("Таблицы уже существуют")

    def сохранить_тексты(self, df: pd.DataFrame) -> Dict[str, int]:
        """
        Записать описания вакансий, по одному экземпляру на текст.

        Ключ — хэш текста, а не идентификатор вакансии: тридцать одна
        копия объявления по городам хранит один текст, а не тридцать
        один. Тот же хэш служит ключом кэша разбора моделью (S10‑5a).

        Текст, который уже лежит в базе, не переписывается: он снимок на
        момент первого получения, и переписать его сегодняшним значило бы
        задним числом изменить то, по чему уже посчитаны навыки.

        Returns:
            `{"новых": n, "повторов": n, "байт": n}` — по этим числам
            видно, сколько занимает хранилище и насколько окупается
            дедупликация.
        """
        from src import texts as тексты_модуль

        if "_описание" not in df.columns:
            return {"новых": 0, "повторов": 0, "байт": 0}

        готовые = {}
        for описание in df["_описание"].dropna():
            подготовленное = тексты_модуль.подготовить(str(описание))
            if подготовленное and подготовленное[0] not in готовые:
                готовые[подготовленное[0]] = подготовленное

        if not готовые:
            return {"новых": 0, "повторов": 0, "байт": 0}

        новых = повторов = байт = 0
        сейчас = datetime.now()
        with self.engine.begin() as conn:
            уже = {
                строка[0]
                for строка in conn.exec_driver_sql(
                    "SELECT text_hash FROM vacancy_texts WHERE text_hash IN "
                    f"({','.join('?' * len(готовые))})",
                    tuple(готовые),
                )
            }
            for хэш_текста, (_, тело, отпечаток_текста, размер) in готовые.items():
                if хэш_текста in уже:
                    повторов += 1
                    continue
                conn.exec_driver_sql(
                    "INSERT INTO vacancy_texts "
                    "(text_hash, body, format, simhash, bytes_raw, fetched_at) "
                    "VALUES (?, ?, 'html', ?, ?, ?)",
                    # Отпечаток беззнаковый, поле знаковое: без перевода
                    # половина текстов роняла запись целиком.
                    (хэш_текста, тело, тексты_модуль.в_поле(отпечаток_текста), размер, сейчас),
                )
                новых += 1
                байт += len(тело)

        logger.info(
            f"Тексты описаний: новых {новых}, уже было {повторов}, "
            f"записано {байт / 1024:.0f} КБ"
        )
        return {"новых": новых, "повторов": повторов, "байт": байт}

    def _тексты_без_права_уронить(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Записать тексты так, чтобы их отказ не стоил собранных вакансий.

        12.09.2026 шесть сборов подряд дошли до 98 % и не сохранили ни
        одной вакансии: отпечаток текста не поместился в поле базы.
        Тексты — запас для слоёв, которых ещё нет; вакансии — то, ради
        чего сбор запускали и за что уже заплачено минутами обхода.
        Отказ вторичного не должен отменять главное.

        Отказ при этом не гасится молча: причина остаётся в
        `отказ_текстов`, сбор называет её в записи запуска. У вакансий
        этой партии ссылка на текст снимается — ссылаться ей не на что,
        и висячий хэш выглядел бы как текст, который есть.
        """
        self.отказ_текстов = None
        try:
            self.сохранить_тексты(df)
        except Exception as e:
            logger.exception(f"Тексты описаний не записаны, вакансии сохраняются без них: {e}")
            self.отказ_текстов = f"{type(e).__name__}: {e}"
            if "text_hash" in df.columns:
                df = df.copy()
                df["text_hash"] = None
        return df

    def читать_текст(self, text_hash: str) -> Optional[str]:
        """Описание по хэшу. Распаковка скрыта: вызывающий о сжатии не знает."""
        from src import texts as тексты_модуль

        if not text_hash:
            return None
        with self.engine.begin() as conn:
            строка = conn.exec_driver_sql(
                "SELECT body FROM vacancy_texts WHERE text_hash = ?", (text_hash,)
            ).fetchone()
        return тексты_модуль.разжать(строка[0]) if строка else None

    def _prepare_records(self, df: pd.DataFrame) -> tuple:
        """
        Привести DataFrame к тому, что можно записать в таблицу.

        Returns:
            (записи, список колонок, число пропущенных строк)

        Note:
            Форму данных задаёт таблица, а не то, что пришло из сбора:
            лишние колонки отбрасываются, недостающие остаются пустыми.
            Иначе одно новое поле в ответе источника роняет сохранение.
        """
        table_columns = {c.name for c in VacancyModel.__table__.columns}
        columns = [
            c for c in df.columns
            if c in table_columns and c not in ("id", "created_at", "updated_at")
        ]

        if "vacancy_id" not in columns:
            raise ValueError("В данных нет vacancy_id — записывать нечего")

        # Строки без идентификатора не сохраняем: обновить такую запись в
        # следующий раз будет нечем, и она превратится в вечный дубль.
        prepared = df[columns].copy()
        prepared = prepared[
            prepared["vacancy_id"].notna() & (prepared["vacancy_id"].astype(str) != "")
        ]
        prepared["vacancy_id"] = prepared["vacancy_id"].astype(str)

        # Источник обязателен: он часть ключа. Записи из старых файлов
        # сборов его не несут — они собраны с hh.ru, другого источника у
        # продукта не было, и молчаливая подстановка здесь не догадка, а
        # факт. Ставится до дедупликации: без него пара неполна.
        if "source" not in prepared.columns:
            prepared["source"] = ИСТОЧНИК_ПО_УМОЛЧАНИЮ
        else:
            prepared["source"] = (
                prepared["source"].fillna(ИСТОЧНИК_ПО_УМОЛЧАНИЮ).replace("", ИСТОЧНИК_ПО_УМОЛЧАНИЮ)
            )
        if "source" not in columns:
            columns.append("source")

        # Повтор ключа внутри одной пачки SQLite отвергает: ON CONFLICT
        # не срабатывает дважды в пределах одного запроса.
        prepared = prepared.drop_duplicates(subset=["source", "vacancy_id"], keep="last")

        skipped = len(df) - len(prepared)

        now = datetime.now()

        # Один курс на всю пачку: читаем до цикла, а не по записи. Заодно
        # это единственное обращение к таблице курсов за всё сохранение.
        курсы = self.get_currency_rates()
        момент_курса = (
            datetime.combine(курсы.на_дату, datetime.min.time()) if курсы else None
        )

        # pandas хранит пропуски как NaN/NaT, драйвер SQLite их не понимает.
        records = prepared.astype(object).where(pd.notna(prepared), None).to_dict("records")
        for record in records:
            # pandas хранит даты своим типом Timestamp, а драйвер SQLite
            # принимает только datetime: без приведения запись падает на
            # первой же дате, пришедшей из DataFrame.
            for key, value in record.items():
                if isinstance(value, pd.Timestamp):
                    record[key] = value.to_pydatetime()

            record["created_at"] = now
            record["updated_at"] = now
            # Даты жизненного цикла обычно проставляет тот, кто пишет:
            # время записи знает он. Но разбор старых файлов сборов
            # приносит свои — момент, когда вакансию видели на самом
            # деле, — и они важнее сегодняшнего времени.
            for field in ("first_seen_at", "last_seen_at"):
                if record.get(field) is None:
                    record[field] = now
            if record.get("is_active") is None:
                record["is_active"] = True

            # Правдоподобие зарплаты считается здесь, а не при показе:
            # через это место проходит всё, что попадает в таблицу, — и
            # сбор, и разбор старых файлов. Считать при показе значило бы
            # повторять правило в каждом запросе и однажды забыть его в
            # новом.
            # Период может не прийти вовсе: старые файлы сборов собраны до
            # появления этого поля. Ключ всё равно должен быть — колонка
            # в запросе есть, и без значения запись не сохранится.
            record.setdefault("salary_mode", None)

            record["salary_doubt"] = причина_сомнения(
                record.get("salary_from"),
                record.get("salary_to"),
                record.get("salary_currency"),
                record.get("salary_mode"),
            )

            # Рублёвый эквивалент — здесь же и по одному курсу на всю
            # пачку: курс за день не меняется, а число, посчитанное
            # разными курсами внутри одной выборки, нельзя сравнивать —
            # ради чего пересчёт и затевался.
            курс = курсы.рублей_за(record.get("salary_currency")) if курсы else None
            if курс is not None:
                для_рублей = (
                    ("salary_from", "salary_from_rub"),
                    ("salary_to", "salary_to_rub"),
                )
                for исходное, рублёвое in для_рублей:
                    значение = record.get(исходное)
                    record[рублёвое] = round(значение * курс) if значение is not None else None
                record["rate_date"] = момент_курса
            else:
                # Валюты нет в котировках: эквивалента не будет, и это
                # честнее нуля — ноль выглядит как настоящая зарплата.
                record["salary_from_rub"] = None
                record["salary_to_rub"] = None
                record["rate_date"] = None

        columns = columns + [
            c for c in ("first_seen_at", "last_seen_at", "is_active", "salary_doubt",
                        "salary_from_rub", "salary_to_rub", "rate_date", "salary_mode")
            if c not in columns
        ]

        return records, columns, skipped

    def _write_records(self, conn, records: List[Dict], columns: List[str], update_existing: bool) -> Dict[str, int]:
        """
        Записать подготовленные строки в открытой транзакции.

        Ядро обоих путей записи: и обычного сбора, и полной перезаписи.
        Второй аргумент — соединение, а не движок, чтобы перезапись могла
        выполнить очистку и вставку одной транзакцией: иначе сбой на
        вставке оставил бы базу пустой.
        """
        if not records:
            return {"inserted": 0, "updated": 0}

        ключи = [(r.get("source") or ИСТОЧНИК_ПО_УМОЛЧАНИЮ, r["vacancy_id"]) for r in records]

        # Что из пачки уже в базе — узнаём заранее: SQLite не сообщает,
        # чем закончилась каждая строка upsert, а различать вставку и
        # обновление нужно для истории сборов.
        existing: set = set()
        for start in range(0, len(ключи), 500):
            кусок = ключи[start:start + 500]
            условия = " OR ".join(
                f"(source = :s{i} AND vacancy_id = :v{i})" for i in range(len(кусок))
            )
            params = {}
            for i, (источник, ид) in enumerate(кусок):
                params[f"s{i}"] = источник
                params[f"v{i}"] = ид
            rows = conn.execute(
                text(f"SELECT source, vacancy_id FROM vacancies WHERE {условия}"),
                params
            )
            existing.update((row[0], row[1]) for row in rows)

        insert_columns = columns + ["created_at", "updated_at"]
        column_list = ", ".join(insert_columns)
        value_list = ", ".join(f":{c}" for c in insert_columns)

        if update_existing:
            # created_at и first_seen_at в списке обновляемых нет
            # намеренно: момент появления записи в базе не меняется
            # оттого, что вакансию увидели снова.
            updates = [
                MERGE_RULES.get(c, f"{c} = excluded.{c}")
                for c in columns
                if c not in ("vacancy_id", "source") and c not in SKIP_ON_UPDATE
            ]
            updates.append("updated_at = excluded.updated_at")
            conflict = f"DO UPDATE SET {', '.join(updates)}"
        else:
            conflict = "DO NOTHING"

        conn.execute(
            text(
                f"INSERT INTO vacancies ({column_list}) VALUES ({value_list}) "
                f"ON CONFLICT(source, vacancy_id) {conflict}"
            ),
            records
        )

        # Возвращаются не только счётчики, но и сами идентификаторы:
        # сбор раскладывает их по поисковым запросам, чтобы в истории было
        # видно, что именно принёс каждый запрос, а не только итог.
        # Считаем по парам «источник + идентификатор», а не по одним
        # идентификаторам: одна и та же вакансия, пришедшая с двух
        # источников, — это две записи. Счёт по идентификаторам показывал
        # одну вставку вместо двух.
        новые_ключи = {к for к in ключи} - existing

        # Наружу отдаются идентификаторы без источника: сбор раскладывает
        # их по поисковым запросам, а запрос всегда идёт в пределах
        # одного источника.
        return {
            "inserted": len(новые_ключи),
            "updated": len(existing),
            "inserted_ids": {ид for _, ид in новые_ключи},
            "updated_ids": {ид for _, ид in existing},
        }

    def replace_all_vacancies(self, df: pd.DataFrame) -> int:
        """
        Полная замена содержимого таблицы вакансий.

        ОПАСНО: удаляет всё собранное. Единственный законный вызывающий —
        сбор с выключенным дописыванием, подтверждённый вводом слова
        «перезаписать». Для обычного сбора существует
        save_vacancies_incremental: он добавляет и обновляет, ничего не
        теряя.

        Args:
            df: DataFrame, которым заменяется содержимое таблицы

        Returns:
            Количество записанных строк

        Note:
            Прежняя версия делала to_sql(if_exists="replace") и сносила
            вместе с данными саму таблицу — вместе со схемой, первичным
            ключом и всеми индексами. Здесь удаляются строки, а схема
            остаётся: она описана в модели и в миграциях, а не
            восстанавливается по форме очередного DataFrame.
        """
        if df.empty:
            logger.warning("Пустой DataFrame — перезапись отменена, база не тронута")
            return 0

        # Тексты пишутся до вакансий: у вакансии остаётся ссылка, и
        # ссылаться она должна на то, что уже лежит.
        df = self._тексты_без_права_уронить(df)
        records, columns, skipped = self._prepare_records(df)
        if not records:
            logger.warning("Нет записей с vacancy_id — перезапись отменена")
            return 0

        logger.warning(f"Полная перезапись таблицы вакансий: {len(records)} записей")

        try:
            # Очистка и вставка одной транзакцией: при сбое вставки база
            # останется прежней, а не опустеет.
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM vacancies"))
                self._write_records(conn, records, columns, update_existing=False)

            logger.info(f"Таблица перезаписана: {len(records)} записей, {skipped} пропущено")
            return len(records)

        except SQLAlchemyError as e:
            logger.error(f"Ошибка перезаписи таблицы: {e}")
            raise

    def save_vacancies_incremental(
        self,
        df: pd.DataFrame,
        update_existing: bool = True
    ) -> Dict[str, int]:
        """
        Сохранение вакансий с обновлением существующих (upsert).

        Единственный путь записи для сбора данных: он добавляет новое и
        обновляет известное, ничего не удаляя. Полная замена таблицы живёт
        в replace_all_vacancies и вызывается только при явной перезаписи
        базы, подтверждённой пользователем.

        Args:
            df: DataFrame с вакансиями. Лишние колонки отбрасываются,
                недостающие остаются пустыми — форма данных задаётся
                таблицей, а не тем, что пришло из сбора.
            update_existing: Обновлять ли существующие записи. False —
                новые добавляются, известные остаются нетронутыми.

        Returns:
            {"inserted": …, "updated": …, "skipped": …} и, для тех, кому
            нужна разбивка, множества "inserted_ids" и "updated_ids"

        Note:
            Записывается одним INSERT … ON CONFLICT на всю пачку.
            Прежняя версия делала два запроса на строку, то есть около
            трёх тысяч запросов на обычный сбор.

            created_at ставится только при вставке: момент появления
            записи в базе не должен меняться при каждом обновлении.
        """
        пусто = {"inserted": 0, "updated": 0, "skipped": 0, "inserted_ids": set(), "updated_ids": set()}

        if df.empty:
            return пусто

        # Тексты пишутся до вакансий: у вакансии остаётся ссылка, и
        # ссылаться она должна на то, что уже лежит.
        df = self._тексты_без_права_уронить(df)
        records, columns, skipped = self._prepare_records(df)
        if not records:
            logger.warning(f"Все {skipped} записей пропущены: нет vacancy_id")
            return {**пусто, "skipped": skipped}

        try:
            with self.engine.begin() as conn:
                written = self._write_records(conn, records, columns, update_existing)
        except SQLAlchemyError as e:
            logger.error(f"Ошибка сохранения вакансий: {e}")
            raise

        stats = {
            "inserted_ids": written["inserted_ids"],
            "updated_ids": written["updated_ids"] if update_existing else set(),
            "inserted": written["inserted"],
            # При update_existing=False известные записи не тронуты — они
            # не обновлены, а пропущены, и статистика обязана это
            # различать: иначе история сбора покажет работу, которой не было.
            "updated": written["updated"] if update_existing else 0,
            "skipped": skipped + (0 if update_existing else written["updated"]),
        }

        logger.info(
            f"Сохранено: {stats['inserted']} новых, {stats['updated']} обновлено, "
            f"{stats['skipped']} пропущено"
        )

        return stats

    def deactivate_missing(self, keyword: str, seen_ids: set) -> int:
        """
        Погасить вакансии запроса, которых источник больше не отдаёт.

        Вакансия не удаляется: она нужна истории — по ней считается, что
        рынок предлагал месяц назад. Но в текущих числах закрытой
        вакансии не место, поэтому она помечается неактивной.

        Args:
            keyword: Запрос, по которому шёл сбор
            seen_ids: Идентификаторы, встреченные в этом сборе

        Returns:
            Сколько вакансий погашено

        Note:
            Вызывать можно только после полного прохода по запросу без
            ошибок. Прерванный сбор не видел части выдачи, и гашение по
            нему объявило бы закрытыми живые вакансии.

            Пустой seen_ids не гасит ничего: это признак сбоя, а не
            признак того, что по запросу не осталось вакансий.
        """
        if not keyword or not seen_ids:
            return 0

        with self.engine.begin() as conn:
            # Запросы хранятся списком через запятую, поэтому сравнение
            # идёт по вхождению целого элемента, а не по подстроке:
            # иначе «Python» задел бы «Python разработчик».
            rows = conn.execute(
                text(
                    "SELECT vacancy_id FROM vacancies "
                    "WHERE is_active = 1 "
                    "AND instr(', ' || COALESCE(source_keyword, '') || ', ', ', ' || :kw || ', ') > 0"
                ),
                {"kw": keyword}
            )
            known = {row[0] for row in rows}

            missing = sorted(known - set(seen_ids))
            if not missing:
                return 0

            now = datetime.now()
            for start in range(0, len(missing), 500):
                chunk = missing[start:start + 500]
                placeholders = ", ".join(f":id{i}" for i in range(len(chunk)))
                params = {f"id{i}": value for i, value in enumerate(chunk)}
                params["now"] = now
                conn.execute(
                    text(
                        f"UPDATE vacancies SET is_active = 0, updated_at = :now "
                        f"WHERE vacancy_id IN ({placeholders})"
                    ),
                    params
                )

        logger.info(f"Запрос «{keyword}»: погашено {len(missing)} вакансий, которых больше нет в выдаче")
        return len(missing)

    def get_all_vacancies(
        self, include_inactive: bool = False, include_off_query: bool = False
    ) -> pd.DataFrame:
        """
        Получение вакансий из базы.

        Args:
            include_inactive: Включать ли вакансии, снятые с публикации.
                По умолчанию нет: экраны продукта описывают текущий
                рынок, и закрытая вакансия в медиане зарплат — это
                ответ на вопрос, которого никто не задавал. Архив нужен
                истории и сбору, они просят его явно.
            include_off_query: Включать ли вакансии, найденные не по
                запросу. По умолчанию нет: рестораны «АРТ РЕСТ» в
                медиане арт-директора — та же ошибка, что закрытая
                вакансия в текущем рынке. Нужны они только обслуживанию.

        Returns:
            DataFrame с вакансиями

        Note:
            Для больших баз данных используйте get_vacancies_filtered
            с параметрами фильтрации.
        """
        условия = []
        if not include_inactive:
            # COALESCE, потому что до миграции 002 колонки не было:
            # записи без признака считаются активными.
            условия.append("COALESCE(is_active, 1) = 1")
        if not include_off_query:
            условия.append("COALESCE(off_query, 0) = 0")

        query = "SELECT * FROM vacancies"
        if условия:
            query += " WHERE " + " AND ".join(условия)

        try:
            df = pd.read_sql_query(query, self.engine)
            df = _разобрать_даты(df)
            logger.debug(f"Загружено {len(df)} записей из БД")
            return df
        except SQLAlchemyError as e:
            logger.error(f"Ошибка загрузки из БД: {e}")
            return pd.DataFrame()

    def get_vacancies_filtered(
        self,
        area: Optional[str] = None,
        experience: Optional[str] = None,
        min_salary: Optional[float] = None,
        limit: int = 1000
    ) -> pd.DataFrame:
        """
        Получение вакансий с фильтрами.

        Args:
            area: Регион (например, "Москва")
            experience: Требуемый опыт
            min_salary: Минимальная зарплата
            limit: Максимальное количество записей

        Returns:
            DataFrame с отфильтрованными вакансиями
        """
        conditions = []
        params = {}

        if area:
            conditions.append("area = :area")
            params["area"] = area

        if experience:
            conditions.append("experience = :experience")
            params["experience"] = experience

        if min_salary:
            conditions.append("salary_from >= :min_salary")
            params["min_salary"] = min_salary

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        query = f"SELECT * FROM vacancies{where_clause} LIMIT :limit"
        params["limit"] = limit

        try:
            df = pd.read_sql_query(query, self.engine, params=params)
            logger.debug(f"Загружено {len(df)} записей с фильтрами")
            return df
        except SQLAlchemyError as e:
            logger.error(f"Ошибка загрузки с фильтрами: {e}")
            return pd.DataFrame()

    def get_skills_statistics(self) -> pd.DataFrame:
        """
        Получение статистики по навыкам.

        Returns:
            DataFrame с топ навыками и частотой упоминаний

        Note:
            Анализирует поля hard_skills, soft_skills, tools
        """
        query = """
        SELECT
            hard_skills,
            soft_skills,
            tools
        FROM vacancies
        WHERE hard_skills IS NOT NULL OR soft_skills IS NOT NULL OR tools IS NOT NULL
        """

        try:
            df = pd.read_sql_query(query, self.engine)

            # Подсчёт частоты каждого навыка
            skill_counts: Dict[str, int] = {}

            for column in ["hard_skills", "soft_skills", "tools"]:
                for skills_str in df[column].dropna():
                    if isinstance(skills_str, str):
                        skills = [s.strip() for s in skills_str.split(",")]
                        for skill in skills:
                            if skill:
                                skill_counts[skill] = skill_counts.get(skill, 0) + 1

            # Создаём DataFrame с результатами
            result = pd.DataFrame(
                list(skill_counts.items()),
                columns=["skill", "count"]
            ).sort_values("count", ascending=False)

            logger.debug(f"Получена статистика по {len(result)} навыкам")
            return result

        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return pd.DataFrame()

    def get_salary_statistics(self, group_by: str = "experience") -> pd.DataFrame:
        """
        Статистика зарплат по группам.

        Args:
            group_by: Поле для группировки (experience, area, employment)

        Returns:
            DataFrame со статистикой зарплат по группам
        """
        query = f"""
        SELECT
            {group_by},
            COUNT(*) as vacancy_count,
            AVG(salary_from) as avg_salary_from,
            MAX(salary_from) as max_salary_from,
            MIN(salary_from) as min_salary_from,
            AVG(salary_to) as avg_salary_to
        FROM vacancies
        -- Сомнительные числа в расчёт не идут: «18 EUR» и «400 UZS»
        -- обрушивают минимум по группе (src/salary_sanity.py).
        WHERE salary_from IS NOT NULL AND salary_doubt IS NULL
        GROUP BY {group_by}
        ORDER BY vacancy_count DESC
        """

        try:
            df = pd.read_sql_query(query, self.engine)
            logger.debug(f"Получена статистика зарплат по {group_by}")
            return df
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения статистики зарплат: {e}")
            return pd.DataFrame()

    def get_off_query_count(self) -> int:
        """Сколько вакансий помечено найденными не по запросу."""
        try:
            result = pd.read_sql_query(
                "SELECT COUNT(*) as count FROM vacancies WHERE COALESCE(off_query, 0) = 1",
                self.engine,
            )
            return int(result["count"].iloc[0])
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения количества: {e}")
            return 0

    def get_vacancy_count(self) -> int:
        """
        Получение общего количества вакансий в базе.

        Returns:
            Количество записей
        """
        # Найденные не по запросу в счёт не идут: число в шапке должно
        # сходиться с тем, по чему считается всё остальное на экране.
        query = "SELECT COUNT(*) as count FROM vacancies WHERE COALESCE(off_query, 0) = 0"

        try:
            result = pd.read_sql_query(query, self.engine)
            return int(result["count"].iloc[0])
        except SQLAlchemyError as e:
            logger.error(f"Ошибка получения количества: {e}")
            return 0

    def clear_database(self) -> None:
        """
        Очистка базы данных (удаление всех записей).

        Warning:
            Необратимая операция! Все данные будут удалены.
        """
        logger.warning("Очистка базы данных...")

        try:
            Base.metadata.drop_all(self.engine)
            self._create_tables()  # Создаём таблицы заново
            logger.info("База данных очищена")
        except SQLAlchemyError as e:
            logger.error(f"Ошибка очистки БД: {e}")
            raise

    def close(self) -> None:
        """Закрытие соединения с базой данных."""
        self.engine.dispose()
        logger.info("Соединение с БД закрыто")

    def __enter__(self) -> "VacancyStorage":
        """Поддержка контекстного менеджера."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Автоматическое закрытие при выходе из контекста."""
        self.close()

    # =========================================================================
    # Методы для работы с parser_runs (журнал парсингов)
    # =========================================================================

    def create_parser_run(
        self,
        keywords: List[str],
        max_pages: int = 10,
        days_back: int = 30,
        is_incremental: bool = True,
        use_cache: bool = True
    ) -> int:
        """
        Создать запись о запуске парсера.

        Args:
            keywords: Список ключевых слов
            max_pages: Макс. страниц на запрос
            days_back: Дней назад
            is_incremental: Инкрементальный режим
            use_cache: Использовать кэш

        Returns:
            ID созданной записи
        """
        with Session(self.engine) as session:
            try:
                run = ParserRunModel(
                    started_at=datetime.now(),
                    status="running",
                    keywords=json.dumps(keywords, ensure_ascii=False),
                    max_pages=max_pages,
                    days_back=days_back,
                    is_incremental=is_incremental,
                    use_cache=use_cache,
                )
                session.add(run)
                session.commit()
                run_id = run.id

                # Обновим app_settings
                self._update_settings(last_parse_at=datetime.now())

                logger.info(f"Создана запись парсинга #{run_id}: keywords={keywords}")
                return run_id

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Ошибка создания записи парсинга: {e}")
                raise

    def save_metrics_snapshot(self, run_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Снять состояние базы и сохранить его как точку истории.

        Args:
            run_id: Сбор, после которого делается снимок

        Returns:
            Сохранённые значения

        Note:
            Снимок считается по активным вакансиям: закрытые остаются в
            базе для истории, но текущее состояние рынка описывают не они.
        """
        активные = self.get_all_vacancies()

        # Курс, действовавший на день снимка: он уезжает в снимок вместе
        # с числами, которые им пересчитываются.
        курсы = self.get_currency_rates()

        медианы: Dict[str, Any] = {}
        медиана_рубли = None
        выборка_рубли = None
        с_зарплатой = 0

        if not активные.empty and "salary_from" in активные.columns:
            с_зарплатой = int(активные["salary_from"].notna().sum())

            # Снимок ложится в основу трендов и живёт годами: пустить в
            # него сомнительное число значит навсегда оставить кривую точку
            # на графике, которую потом нечем будет объяснить.
            for валюта, группа in только_правдоподобные(активные).groupby("salary_currency"):
                значения = группа["salary_from"]
                медианы[str(валюта)] = {
                    "median": float(значения.median()),
                    "sample": int(len(значения)),
                }

            рубли = медианы.get("RUB")
            if рубли:
                медиана_рубли = рубли["median"]
                выборка_рубли = рубли["sample"]

        снимок = {
            "taken_at": datetime.now(),
            "run_id": run_id,
            "source": "measured",
            "active_vacancies": int(len(активные)),
            "total_vacancies": int(len(self.get_all_vacancies(include_inactive=True))),
            "unique_companies": int(активные["employer_name"].nunique()) if not активные.empty else 0,
            "unique_regions": int(активные["area"].nunique()) if not активные.empty else 0,
            "with_salary": с_зарплатой,
            "median_salary_rub": медиана_рубли,
            "salary_sample_rub": выборка_рубли,
            "medians_by_currency": json.dumps(медианы, ensure_ascii=False),
            "rate_date": datetime.combine(курсы.на_дату, datetime.min.time()) if курсы else None,
            "rates": json.dumps(курсы.значения, ensure_ascii=False) if курсы else None,
        }

        with Session(self.engine) as session:
            try:
                session.add(MetricsSnapshotModel(**снимок))
                session.commit()
                logger.info(
                    f"Снимок метрик: {снимок['active_vacancies']} активных вакансий, "
                    f"{снимок['unique_companies']} компаний"
                )
            except SQLAlchemyError as e:
                session.rollback()
                # Снимок — это наблюдение за работой, а не сама работа:
                # его неудача не должна отменять успешный сбор.
                logger.error(f"Не удалось сохранить снимок метрик: {e}")
                return {}

        return снимок

    def get_metrics_snapshots(self, limit: int = 30, only_measured: bool = False) -> List[Dict[str, Any]]:
        """
        Снимки от новых к старым.

        Args:
            limit: Сколько вернуть
            only_measured: Только настоящие замеры, без восстановленных.
                Нужен там, где считаются зарплатные тренды: у
                восстановленных снимков зарплатных метрик нет
        """
        with Session(self.engine) as session:
            запрос = session.query(MetricsSnapshotModel)
            if only_measured:
                запрос = запрос.filter_by(source="measured")

            строки = запрос.order_by(MetricsSnapshotModel.taken_at.desc()).limit(limit).all()

            return [
                {
                    "taken_at": s.taken_at.isoformat() if s.taken_at else None,
                    "source": s.source,
                    "run_id": s.run_id,
                    "active_vacancies": s.active_vacancies,
                    "total_vacancies": s.total_vacancies,
                    "unique_companies": s.unique_companies,
                    "unique_regions": s.unique_regions,
                    "with_salary": s.with_salary,
                    "median_salary_rub": s.median_salary_rub,
                    "salary_sample_rub": s.salary_sample_rub,
                    "medians_by_currency": json.loads(s.medians_by_currency) if s.medians_by_currency else {},
                    "rate_date": s.rate_date.date().isoformat() if s.rate_date else None,
                    "rates": json.loads(s.rates) if s.rates else {},
                }
                for s in строки
            ]

    def save_currency_rates(self, курсы) -> int:
        """
        Сохранить курсы на их дату.

        Курс за день — один: повторный вызов в тот же день обновляет
        значение, а не плодит записи. Дата берётся из ответа ЦБ, а не из
        календаря: в выходной источник отдаёт последний рабочий день, и
        подписать его сегодняшним числом значило бы соврать.
        """
        сейчас = datetime.now()
        момент = datetime.combine(курсы.на_дату, datetime.min.time())

        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO currency_rates (currency, rate_date, value, fetched_at) "
                    "VALUES (:currency, :rate_date, :value, :fetched_at) "
                    "ON CONFLICT(currency, rate_date) DO UPDATE SET "
                    "value = excluded.value, fetched_at = excluded.fetched_at"
                ),
                [
                    {"currency": код, "rate_date": момент, "value": значение, "fetched_at": сейчас}
                    for код, значение in курсы.значения.items()
                ],
            )

        logger.info(f"Курсы сохранены: {len(курсы.значения)} валют на {курсы.на_дату:%d.%m.%Y}")
        return len(курсы.значения)

    def get_currency_rates(self) -> Optional["Курсы"]:
        """
        Последние известные курсы. None — их вовсе нет.

        Возвращается именно последний известный, а не только сегодняшний:
        если ЦБ недоступен, вчерашний курс с честной подписью полезнее
        пустого места. Насколько он свеж, видно по дате — её и показывают
        рядом с числами.
        """
        from src.cbr_rates import Курсы

        with self.engine.connect() as conn:
            дата = conn.execute(text("SELECT MAX(rate_date) FROM currency_rates")).scalar()
            if not дата:
                return None

            строки = conn.execute(
                text("SELECT currency, value FROM currency_rates WHERE rate_date = :d"),
                {"d": дата},
            ).fetchall()

        if isinstance(дата, str):
            дата = datetime.fromisoformat(дата)

        return Курсы(на_дату=дата.date(), значения={код: значение for код, значение in строки})

    def refresh_currency_rates(self) -> Optional["Курсы"]:
        """
        Обновить курсы у источника; при отказе — оставить прежние.

        Отказ ЦБ не должен ронять сбор данных: курс — вспомогательная
        величина, и работа без свежего курса возможна, а вот падение
        сбора из-за чужого сайта — нет.
        """
        from src.cbr_rates import запросить

        try:
            курсы = запросить()
        except Exception as e:
            прежние = self.get_currency_rates()
            logger.warning(
                f"Курсы ЦБ не обновлены ({type(e).__name__}): "
                + (f"остаются от {прежние.на_дату:%d.%m.%Y}" if прежние else "их вовсе нет")
            )
            return прежние

        self.save_currency_rates(курсы)
        return курсы

    def get_collection_settings(self) -> Dict[str, Any]:
        """
        Настройки сбора: почта для запросов и пауза между ними.

        Первичные значения берутся из окружения — при первом запуске в
        базе ещё пусто, а настроенное в `.env` терять незачем. Дальше
        источник истины — база.

        Returns:
            {"email": str, "request_delay": float}
        """
        почта_по_умолчанию = settings.hh_user_email or ""
        пауза_по_умолчанию = getattr(settings, "api_request_delay", 1.0) or 1.0

        with Session(self.engine) as session:
            запись = session.query(AppSettingsModel).filter_by(id=1).first()
            if not запись:
                return {
                    "email": почта_по_умолчанию,
                    "request_delay": пауза_по_умолчанию,
                    "search_queries": None,
                }

            return {
                "email": запись.hh_user_email or почта_по_умолчанию,
                "request_delay": запись.request_delay or пауза_по_умолчанию,
                "search_queries": _разобрать_запросы(запись.search_queries),
            }

    def save_collection_settings(
        self,
        email: Optional[str] = None,
        request_delay: Optional[float] = None,
        search_queries: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Сохранить настройки сбора.

        Args:
            email: Почта для заголовка запроса
            request_delay: Пауза между запросами в секундах

        Returns:
            Настройки после сохранения

        Note:
            Прежде почту дописывали в `.env` заменой по регулярному
            выражению: строка в комментарии попадала под замену наравне с
            настоящей, а при неудачной записи файл окружения оставался
            испорченным. База для этого надёжнее.
        """
        with Session(self.engine) as session:
            try:
                запись = session.query(AppSettingsModel).filter_by(id=1).first()
                if not запись:
                    запись = AppSettingsModel(id=1)
                    session.add(запись)

                if email is not None:
                    запись.hh_user_email = email
                if request_delay is not None:
                    запись.request_delay = request_delay
                if search_queries is not None:
                    # Пустой список сохраняется как пустой, а не как
                    # «не задано»: человек мог осознанно всё убрать.
                    запись.search_queries = json.dumps(search_queries, ensure_ascii=False)

                session.commit()
                logger.info("Настройки сбора сохранены")

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Не удалось сохранить настройки сбора: {e}")
                raise

        return self.get_collection_settings()

    def update_run_progress(
        self,
        run_id: int,
        collected: int = 0,
        current_keyword: str = "",
        current_page: int = 0,
        found_estimate: Optional[int] = None,
        min_interval: float = 1.0,
        percent: Optional[int] = None,
    ) -> bool:
        """
        Записать ход сбора и отметку живости.

        Args:
            run_id: Запись сбора
            collected: Сколько вакансий собрано к этому моменту
            current_keyword: Какой запрос обрабатывается
            current_page: Какая страница выдачи
            found_estimate: Сколько вакансий обещал источник
            min_interval: Не писать чаще, чем раз в столько секунд
            percent: Готовность сбора. Считает `src.progress` — здесь
                число только хранится: вторая формула в этом месте уже
                была, и она делила собранное за весь сбор на найденное
                по одному запросу

        Returns:
            Была ли запись выполнена

        Note:
            Событий хода сбора приходят сотни, а ценность у записи одна:
            показать, что работа идёт. Поэтому запись прореживается по
            времени — иначе сбор из тысячи событий даёт тысячу обращений
            к базе, конкурируя с сохранением самих вакансий.
        """
        сейчас = datetime.now()
        последняя = self._last_progress_write.get(run_id)
        if последняя and (сейчас - последняя).total_seconds() < min_interval:
            return False

        with Session(self.engine) as session:
            try:
                run = session.query(ParserRunModel).filter_by(id=run_id).first()
                if not run:
                    return False

                run.vacancies_collected = collected
                run.current_keyword = current_keyword or run.current_keyword
                run.current_page = current_page
                run.heartbeat_at = сейчас
                if found_estimate:
                    run.found_estimate = found_estimate
                if percent is not None:
                    # Назад полоса не ходит: при резке запроса на срезы
                    # доля внутри запроса считается по срезу и может
                    # оказаться меньше уже показанной.
                    run.progress_percent = max(run.progress_percent or 0, percent)

                session.commit()
                self._last_progress_write[run_id] = сейчас
                return True

            except SQLAlchemyError as e:
                session.rollback()
                # Ход работы — отчёт о ней, а не сама работа: сбой записи
                # прогресса не должен ронять сбор.
                logger.warning(f"Не удалось записать ход сбора #{run_id}: {e}")
                return False

    def get_active_run(self) -> Optional[Dict[str, Any]]:
        """
        Идущий сейчас сбор, каким его видит база.

        Returns:
            Словарь с ходом работы или None, если ничего не идёт
        """
        with Session(self.engine) as session:
            run = (
                session.query(ParserRunModel)
                .filter_by(status="running")
                .order_by(ParserRunModel.id.desc())
                .first()
            )
            if not run:
                return None

            return {
                "id": run.id,
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "keywords": json.loads(run.keywords) if run.keywords else [],
                "current_keyword": run.current_keyword or "",
                "current_page": run.current_page or 0,
                "vacancies_collected": run.vacancies_collected or 0,
                "found_estimate": run.found_estimate,
                "progress": run.progress_percent or 0,
                "heartbeat_at": run.heartbeat_at.isoformat() if run.heartbeat_at else None,
                "is_incremental": run.is_incremental,
                "use_cache": run.use_cache,
            }

    def mark_interrupted_runs(self, stale_after_minutes: int = 5) -> int:
        """
        Пометить оборвавшиеся сборы.

        Запись со статусом «running» и старой отметкой живости — это след
        сбора, чей процесс не пережил перезапуск. Отличать такие записи
        от идущей работы нужно на старте приложения: иначе интерфейс
        будет вечно ждать сбор, которого нет.

        Args:
            stale_after_minutes: Через сколько минут молчания сбор
                считается оборвавшимся

        Returns:
            Сколько записей помечено
        """
        граница = datetime.now() - timedelta(minutes=stale_after_minutes)

        with Session(self.engine) as session:
            try:
                зависшие = (
                    session.query(ParserRunModel)
                    .filter(ParserRunModel.status == "running")
                    .filter(
                        (ParserRunModel.heartbeat_at.is_(None))
                        | (ParserRunModel.heartbeat_at < граница)
                    )
                    .all()
                )

                for run in зависшие:
                    run.status = "interrupted"
                    run.completed_at = run.completed_at or datetime.now()
                    run.error_message = run.error_message or (
                        "Сбор прерван: приложение было перезапущено во время работы"
                    )

                session.commit()

                if зависшие:
                    logger.info(f"Помечено прерванных сборов: {len(зависшие)}")
                return len(зависшие)

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Не удалось пометить прерванные сборы: {e}")
                return 0

    def save_run_queries(self, run_id: int, by_keyword: Dict[str, Dict[str, Any]]) -> int:
        """
        Записать, что принёс каждый запрос в рамках одного сбора.

        Args:
            run_id: Запись сбора, к которой относится разбивка
            by_keyword: Статистика по запросам от коллектора

        Returns:
            Сколько строк записано

        Note:
            Ошибка записи разбивки не должна ронять сам сбор: вакансии
            уже сохранены, а разбивка — это пояснение к ним. Поэтому
            исключение здесь только логируется.
        """
        if not by_keyword:
            return 0

        with Session(self.engine) as session:
            try:
                for keyword, stats in by_keyword.items():
                    session.add(RunQueryModel(
                        run_id=run_id,
                        keyword=keyword,
                        status="complete" if stats.get("complete") else "partial",
                        found=stats.get("found") or None,
                        taken=stats.get("взято"),
                        pages=stats.get("pages", 0),
                        vacancies_new=stats.get("new", 0),
                        vacancies_updated=stats.get("updated", 0),
                        from_cache=stats.get("from_cache", 0),
                        errors_count=stats.get("errors", 0),
                        duration_ms=stats.get("duration_ms", 0),
                    ))
                session.commit()
                logger.info(f"Разбивка сбора #{run_id}: {len(by_keyword)} запросов")
                return len(by_keyword)

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Не удалось записать разбивку сбора #{run_id}: {e}")
                return 0

    def get_run_queries(self, run_id: int) -> List[Dict[str, Any]]:
        """Разбивка одного сбора по запросам, в порядке выполнения."""
        with Session(self.engine) as session:
            rows = (
                session.query(RunQueryModel)
                .filter_by(run_id=run_id)
                .order_by(RunQueryModel.id)
                .all()
            )
            return [
                {
                    "keyword": r.keyword,
                    "status": r.status,
                    "found": r.found,
                    "taken": r.taken,
                    "pages": r.pages,
                    "vacancies_new": r.vacancies_new,
                    "vacancies_updated": r.vacancies_updated,
                    "from_cache": r.from_cache,
                    "errors_count": r.errors_count,
                    "duration_ms": r.duration_ms,
                }
                for r in rows
            ]

    def complete_parser_run(
        self,
        run_id: int,
        status: str,
        vacancies_collected: int = 0,
        vacancies_new: int = 0,
        vacancies_updated: int = 0,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None
    ) -> None:
        """
        Завершить запись о парсинге.

        Args:
            run_id: ID записи парсинга
            status: completed / error / stopped
            vacancies_collected: Всего собрано
            vacancies_new: Новых вакансий
            vacancies_updated: Обновлено вакансий
            error_message: Текст ошибки (если есть)
            error_type: Короткий код причины — по нему интерфейс выбирает
                объяснение и следующий шаг
        """
        with Session(self.engine) as session:
            try:
                run = session.query(ParserRunModel).filter_by(id=run_id).first()
                if not run:
                    logger.error(f"Запись парсинга #{run_id} не найдена")
                    return

                run.completed_at = datetime.now()
                run.status = status
                run.vacancies_collected = vacancies_collected
                run.vacancies_new = vacancies_new
                run.vacancies_updated = vacancies_updated
                if error_message:
                    run.error_message = error_message
                if error_type:
                    run.error_type = error_type

                session.commit()

                # Обновим app_settings
                self._update_settings(
                    last_successful_parse_at=datetime.now() if status == "completed" else None,
                    total_parses_increment=1,
                    total_vacancies_collected_increment=vacancies_collected
                )

                logger.info(
                    f"Завершён парсинг #{run_id}: status={status}, "
                    f"collected={vacancies_collected}, new={vacancies_new}"
                )

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Ошибка завершения парсинга: {e}")
                raise

    def save_run_progress(self, run_id: int, состояние: Dict[str, Any]) -> None:
        """
        Запомнить, где сбор находится сейчас.

        Пишется после каждого пройденного запроса, а не на каждой
        странице: запись стоит открытия сессии, а гранулярность в один
        запрос — это и есть шаг, с которого имеет смысл продолжать.
        Вакансии запроса к этому моменту уже в базе.

        Ошибка записи не роняет сбор: без состояния он просто начнётся
        заново, а собранное никуда не денется.
        """
        with Session(self.engine) as session:
            try:
                run = session.get(ParserRunModel, run_id)
                if not run:
                    return
                run.progress_state = json.dumps(состояние, ensure_ascii=False)
                session.commit()
            except SQLAlchemyError as e:
                session.rollback()
                logger.warning(f"Не удалось записать состояние обхода #{run_id}: {e}")

    def get_run_progress(self, run_id: int) -> Dict[str, Any]:
        """Состояние обхода. Пустой словарь — «неизвестно», а не «ничего не пройдено»."""
        with Session(self.engine) as session:
            run = session.get(ParserRunModel, run_id)
            if not run or not run.progress_state:
                return {}
            try:
                return json.loads(run.progress_state)
            except json.JSONDecodeError:
                logger.warning(f"Состояние обхода #{run_id} не разобрано")
                return {}

    def find_resumable_run(self, keywords: List[str], within_hours: int = 24) -> Optional[Dict[str, Any]]:
        """
        Найти оборванный сбор, который имеет смысл продолжить.

        Продолжаем только то, что оборвалось само: статус `interrupted` —
        это след перезапуска приложения посреди работы. Сбор, который
        человек остановил кнопкой, продолжать нельзя: он сказал «хватит»,
        и молча дособрать за него — значит сделать не то, о чём просили.

        Набор запросов должен совпадать: продолжение с другим набором —
        это уже другой сбор. Срок в сутки взят потому, что дальше выдача
        источника успевает смениться и «продолжение» собирало бы вперемешку
        сегодняшнее со вчерашним.

        Returns:
            Запись сбора и его состояние, либо None — начинаем заново.
        """
        рубеж = datetime.now() - timedelta(hours=within_hours)

        with Session(self.engine) as session:
            кандидаты = (
                session.query(ParserRunModel)
                .filter(ParserRunModel.status == "interrupted")
                .filter(ParserRunModel.started_at >= рубеж)
                .order_by(ParserRunModel.started_at.desc())
                .limit(10)
                .all()
            )

            for run in кандидаты:
                if not run.progress_state:
                    continue
                try:
                    свои = json.loads(run.keywords) if run.keywords else []
                    состояние = json.loads(run.progress_state)
                except json.JSONDecodeError:
                    continue

                if sorted(свои) != sorted(keywords):
                    continue
                if not состояние.get("пройденные_запросы"):
                    continue

                return {
                    "id": run.id,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "keywords": свои,
                    "состояние": состояние,
                }

        return None

    def save_run_quality(self, run_id: int, качество: Dict[str, Any]) -> None:
        """
        Записать, годится ли собранное этим запуском для аналитики.

        Args:
            run_id: Запись сбора
            качество: Сводка от коллектора — всего, с карточкой, без
                навыков, неполных запросов

        Note:
            Ошибка записи не должна ронять сбор: вакансии уже сохранены,
            а качество — пояснение к ним.
        """
        if not качество:
            return

        with Session(self.engine) as session:
            try:
                run = session.get(ParserRunModel, run_id)
                if not run:
                    return

                run.q_with_details = качество.get("с_карточкой")
                run.q_without_skills = качество.get("без_навыков")
                run.q_incomplete = качество.get("неполных_запросов")
                session.commit()

                logger.info(
                    f"Качество сбора #{run_id}: с карточкой "
                    f"{качество.get('с_карточкой')}, без навыков "
                    f"{качество.get('без_навыков')}, неполных запросов "
                    f"{качество.get('неполных_запросов')}"
                )
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Не удалось записать качество сбора #{run_id}: {e}")

    def get_last_parser_run(self, only_successful: bool = True) -> Optional[Dict]:
        """
        Получить последний запуск парсера.

        Args:
            only_successful: Только успешные запуски

        Returns:
            Словарь с данными или None
        """
        with Session(self.engine) as session:
            try:
                query = session.query(ParserRunModel)
                if only_successful:
                    query = query.filter_by(status="completed")
                query = query.order_by(ParserRunModel.completed_at.desc())

                run = query.first()
                if not run:
                    return None

                return {
                    "id": run.id,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                    "status": run.status,
                    "keywords": json.loads(run.keywords) if run.keywords else [],
                    "max_pages": run.max_pages,
                    "days_back": run.days_back,
                    "is_incremental": run.is_incremental,
                    "use_cache": run.use_cache,
                    "vacancies_collected": run.vacancies_collected,
                    "vacancies_new": run.vacancies_new,
                    "vacancies_updated": run.vacancies_updated,
                    "errors_count": run.errors_count,
                    "error_message": run.error_message,
                }

            except SQLAlchemyError as e:
                logger.error(f"Ошибка получения последнего парсинга: {e}")
                return None

    def get_parser_runs_history(self, limit: int = 20) -> List[Dict]:
        """
        Получить историю запусков парсера.

        Args:
            limit: Макс. количество записей

        Returns:
            Список словарей с данными
        """
        with Session(self.engine) as session:
            try:
                runs = (
                    session.query(ParserRunModel)
                    .order_by(ParserRunModel.started_at.desc())
                    .limit(limit)
                    .all()
                )

                return [
                    {
                        "id": r.id,
                        "started_at": r.started_at.isoformat() if r.started_at else None,
                        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                        "status": r.status,
                        "keywords": json.loads(r.keywords) if r.keywords else [],
                        "vacancies_collected": r.vacancies_collected,
                        "vacancies_new": r.vacancies_new,
                        "vacancies_updated": r.vacancies_updated,
                        "is_incremental": r.is_incremental,
                        "use_cache": r.use_cache,
                        "error_message": r.error_message,
                        # Качество этого запуска, а не всей базы: по нему
                        # видно, ухудшается ли сбор со временем.
                        "качество": {
                            "с_карточкой": r.q_with_details,
                            "без_навыков": r.q_without_skills,
                            "неполных_запросов": r.q_incomplete,
                        },
                    }
                    for r in runs
                ]

            except SQLAlchemyError as e:
                logger.error(f"Ошибка получения истории парсингов: {e}")
                return []

    # =========================================================================
    # Методы для работы с app_settings
    # =========================================================================

    def _update_settings(
        self,
        last_parse_at=None,
        last_successful_parse_at=None,
        total_parses_increment=0,
        total_vacancies_collected_increment=0
    ) -> None:
        """
        Внутренний метод обновления настроек приложения.

        Args:
            last_parse_at: Дата последнего запуска
            last_successful_parse_at: Дата последнего успешного запуска
            total_parses_increment: Увеличить счётчик парсингов
            total_vacancies_collected_increment: Увеличить счётчик вакансий
        """
        with Session(self.engine) as session:
            try:
                settings_row = session.query(AppSettingsModel).filter_by(id=1).first()
                if not settings_row:
                    settings_row = AppSettingsModel(id=1)
                    session.add(settings_row)

                if last_parse_at:
                    settings_row.last_parse_at = last_parse_at
                if last_successful_parse_at:
                    settings_row.last_successful_parse_at = last_successful_parse_at
                if total_parses_increment > 0:
                    settings_row.total_parses = (settings_row.total_parses or 0) + total_parses_increment
                if total_vacancies_collected_increment > 0:
                    settings_row.total_vacancies_collected = (
                        (settings_row.total_vacancies_collected or 0) + total_vacancies_collected_increment
                    )

                settings_row.updated_at = datetime.now()
                session.commit()

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Ошибка обновления настроек: {e}")

    def get_app_settings(self) -> Optional[Dict]:
        """
        Получить настройки приложения.

        Returns:
            Словарь с настройками или None
        """
        with Session(self.engine) as session:
            try:
                settings_row = session.query(AppSettingsModel).filter_by(id=1).first()
                if not settings_row:
                    return None

                return {
                    "last_parse_at": settings_row.last_parse_at.isoformat() if settings_row.last_parse_at else None,
                    "last_successful_parse_at": settings_row.last_successful_parse_at.isoformat() if settings_row.last_successful_parse_at else None,
                    "total_parses": settings_row.total_parses or 0,
                    "total_vacancies_collected": settings_row.total_vacancies_collected or 0,
                    "app_version": settings_row.app_version,
                    "config_version": settings_row.config_version,
                }

            except SQLAlchemyError as e:
                logger.error(f"Ошибка получения настроек: {e}")
                return None

    def initialize_settings(self) -> None:
        """Инициализировать запись настроек (если ещё нет)."""
        with Session(self.engine) as session:
            try:
                existing = session.query(AppSettingsModel).filter_by(id=1).first()
                if not existing:
                    session.add(AppSettingsModel(id=1))
                    session.commit()
                    logger.info("Инициализированы настройки приложения")
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Ошибка инициализации настроек: {e}")


# =============================================================================
# Блок для тестирования модуля
# =============================================================================

if __name__ == "__main__":
    """
    Пример использования VacancyStorage для тестирования.

    Перед запуском убедитесь:
    1. Есть обработанный CSV файл в data/processed/
    2. Установлена sqlalchemy

    Запуск: python -m src.storage
    """

    import logging
    logging.getLogger("src").setLevel(logging.INFO)

    print("=" * 60)
    print("Тестирование VacancyStorage")
    print("=" * 60)

    # Создаём хранилище
    storage = VacancyStorage()

    try:
        # Проверяем наличие CSV файла для загрузки
        csv_path = settings.processed_data_dir / "vacancies_processed.csv"

        if csv_path.exists():
            # Загружаем CSV
            print(f"\n📥 Загрузка данных из {csv_path}")
            df = pd.read_csv(csv_path)

            # Сохраняем в БД
            print("-" * 60)
            print("💾 Сохранение в базу данных...")

            count = storage.replace_all_vacancies(df)
            print(f"✅ Сохранено записей: {count}")

            # Тестируем выборку
            print("\n" + "=" * 60)
            print("📊 Тестирование выборок")
            print("=" * 60)

            # Общее количество
            total = storage.get_vacancy_count()
            print(f"📈 Всего вакансий в БД: {total}")

            # Статистика по навыкам
            print("\n📋 Топ-10 навыков:")
            skills_df = storage.get_skills_statistics()
            for _, row in skills_df.head(10).iterrows():
                print(f"  • {row['skill']}: {row['count']}")

            # Статистика зарплат по опыту
            print("\n💰 Зарплаты по опыту:")
            salary_df = storage.get_salary_statistics("experience")
            for _, row in salary_df.iterrows():
                print(f"  • {row['experience']}: "
                      f"средняя {row['avg_salary_from']:,.0f} RUB")

        else:
            print(f"⚠️  CSV файл не найден: {csv_path}")
            print("Сначала запустите processor.py для обработки данных")

    except KeyboardInterrupt:
        print("\n\n⚠️  Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {type(e).__name__} - {e}")
        logger.exception("Детальная информация об ошибке")
    finally:
        storage.close()
        print("\n" + "=" * 60)
        print("Тестирование завершено!")
        print("=" * 60)
