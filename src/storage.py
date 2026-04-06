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

from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import json

import pandas as pd
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    Index,
    text,
)
from sqlalchemy.orm import declarative_base, Session
from sqlalchemy.exc import SQLAlchemyError

from src.config import settings
from src.utils import get_logger, ensure_dir

# Инициализируем логгер для модуля
logger = get_logger(__name__)

# Базовый класс для ORM моделей
Base = declarative_base()


# =============================================================================
# Модели БД
# =============================================================================

class VacancyModel(Base):
    """
    ORM модель для таблицы вакансий.

    Соответствует таблице 'vacancies' в SQLite.
    Содержит все основные поля для анализа.
    """

    __tablename__ = "vacancies"

    # Первичный ключ
    id = Column(Integer, primary_key=True, autoincrement=True)

    # ID вакансии из HH API (уникальный)
    vacancy_id = Column(String(50), unique=True, nullable=False, index=True)

    # Основная информация
    vacancy_name = Column(String(500), nullable=False)
    published_at = Column(DateTime)
    applied_at = Column(DateTime)

    # Навыки (хранятся как строки через запятую)
    all_skills = Column(Text)
    hard_skills = Column(Text)
    soft_skills = Column(Text)
    tools = Column(Text)

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

    # Индексы для ускорения поиска
    __table_args__ = (
        Index("idx_vacancy_id", "vacancy_id"),
        Index("idx_employer", "employer_name"),
        Index("idx_area", "area"),
        Index("idx_published_at", "published_at"),
        Index("idx_experience", "experience"),
        Index("idx_salary_from", "salary_from"),
        Index("idx_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        """Строковое представление для отладки."""
        return f"<Vacancy(id={self.vacancy_id}, name='{self.vacancy_name[:50]}...')>"


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

    # Метаданные
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<ParserRun(id={self.id}, status='{self.status}', collected={self.vacancies_collected})>"


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
        >>> storage.save_dataframe(df)
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

    def save_dataframe(self, df: pd.DataFrame, chunk_size: int = 1000) -> int:
        """
        Сохранение DataFrame в базу данных.

        Args:
            df: DataFrame с обработанными вакансиями
            chunk_size: Количество строк для вставки за один раз

        Returns:
            Количество сохранённых записей

        Note:
            Используется pandas to_sql с параметром if_exists='replace'
            для полной замены данных. Для incremental загрузки используйте
            save_vacancies_incremental.
        """
        if df.empty:
            logger.warning("Пустой DataFrame, сохранение пропущено")
            return 0

        logger.info(f"Сохранение {len(df)} записей в БД")

        try:
            # pandas to_sql автоматически создаёт таблицу если её нет
            # if_exists='replace' — удаляет старую таблицу и создаёт новую
            # Это проще для начала, потом можно заменить на upsert
            df.to_sql(
                "vacancies",
                self.engine,
                if_exists="replace",  # 'replace' | 'append' | 'fail'
                index=False,
                chunksize=chunk_size,
                method="multi",  # Массовая вставка для скорости
            )

            logger.info(f"Сохранено {len(df)} записей в {self.db_path}")
            return len(df)

        except SQLAlchemyError as e:
            logger.error(f"Ошибка сохранения в БД: {e}")
            raise

    def save_vacancies_incremental(
        self,
        df: pd.DataFrame,
        update_existing: bool = True
    ) -> Dict[str, int]:
        """
        Инкрементальное сохранение с upsert логикой.

        Args:
            df: DataFrame с вакансиями
            update_existing: Обновлять ли существующие записи

        Returns:
            Словарь со статистикой:
            - inserted: количество новых записей
            - updated: количество обновлённых записей
            - skipped: количество пропущенных

        Note:
            Upsert = INSERT OR UPDATE
            В SQLite реализуется через INSERT ... ON CONFLICT
        """
        if df.empty:
            return {"inserted": 0, "updated": 0, "skipped": 0}

        stats = {"inserted": 0, "updated": 0, "skipped": 0}

        with Session(self.engine) as session:
            try:
                for _, row in df.iterrows():
                    # Проверяем существует ли вакансия
                    existing = session.query(VacancyModel).filter(
                        VacancyModel.vacancy_id == row["vacancy_id"]
                    ).first()

                    if existing:
                        if update_existing:
                            # Обновляем существующую запись
                            for col, value in row.items():
                                if hasattr(existing, col):
                                    setattr(existing, col, value)
                            existing.updated_at = datetime.now()
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        # Создаём новую запись
                        vacancy = VacancyModel(**row.to_dict())
                        session.add(vacancy)
                        stats["inserted"] += 1

                # Фиксируем транзакцию
                session.commit()
                logger.info(
                    f"Incremental save: {stats['inserted']} inserted, "
                    f"{stats['updated']} updated, {stats['skipped']} skipped"
                )

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Ошибка incremental save: {e}")
                raise

        return stats

    def get_all_vacancies(self) -> pd.DataFrame:
        """
        Получение всех вакансий из базы.

        Returns:
            DataFrame со всеми вакансиями

        Note:
            Для больших баз данных используйте get_vacancies_filtered
            с параметрами фильтрации.
        """
        query = "SELECT * FROM vacancies"

        try:
            df = pd.read_sql_query(query, self.engine)
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
        WHERE salary_from IS NOT NULL
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

    def get_vacancy_count(self) -> int:
        """
        Получение общего количества вакансий в базе.

        Returns:
            Количество записей
        """
        query = "SELECT COUNT(*) as count FROM vacancies"

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

    def complete_parser_run(
        self,
        run_id: int,
        status: str,
        vacancies_collected: int = 0,
        vacancies_new: int = 0,
        vacancies_updated: int = 0,
        error_message: Optional[str] = None
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

            count = storage.save_dataframe(df)
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
