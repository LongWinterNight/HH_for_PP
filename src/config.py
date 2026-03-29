"""
Модуль конфигурации проекта.

Загружает настройки из:
1. .env файла (переменные окружения)
2. config.yaml (словари навыков, поисковые запросы)

Использует pydantic для валидации настроек.
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """
    Класс для хранения настроек проекта.

    Все настройки загружаются из .env файла.
    Pydantic обеспечивает валидацию типов данных.
    """

    # HH.ru API
    hh_user_email: str = Field(
        default="",
        description="Email для заголовка User-Agent"
    )

    # Rate Limiting
    api_request_delay: float = Field(
        default=1.0,
        description="Задержка между запросами в секундах"
    )

    # Лимиты сбора
    max_pages: int = Field(
        default=10,
        description="Максимальное количество страниц для сбора"
    )
    days_back: int = Field(
        default=30,
        description="За сколько дней собирать вакансии"
    )

    # Пути к данным
    data_dir: Path = Field(
        default=Path("data"),
        description="Основная директория для данных"
    )
    raw_data_dir: Path = Field(
        default=Path("data/raw"),
        description="Директория для сырых данных"
    )
    processed_data_dir: Path = Field(
        default=Path("data/processed"),
        description="Директория для обработанных данных"
    )
    reports_dir: Path = Field(
        default=Path("data/reports"),
        description="Директория для отчётов"
    )

    # База данных
    db_path: Path = Field(
        default=Path("data/hh_vacancies.db"),
        description="Путь к SQLite базе данных"
    )

    # Логирование
    log_level: str = Field(
        default="INFO",
        description="Уровень логирования"
    )
    log_file: Path = Field(
        default=Path("logs/hh_analytics.log"),
        description="Путь к файлу логов"
    )

    class Config:
        """Конфигурация Pydantic модели."""
        arbitrary_types_allowed = True


class ConfigLoader:
    """
    Загрузчик конфигурации из YAML файла.

    Предоставляет доступ к:
    - Поисковым запросам
    - Словарям навыков
    - Параметрам обработки
    """

    def __init__(self, config_path: Path) -> None:
        """
        Инициализация загрузчика.

        Args:
            config_path: Путь к config.yaml
        """
        self.config_path = config_path
        self._config: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Загрузка конфигурации из YAML файла."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)

    @property
    def search_queries(self) -> List[str]:
        """Список поисковых запросов."""
        return self._config.get("search_queries", [])

    @property
    def hard_skills(self) -> List[str]:
        """Список Hard Skills."""
        return self._config.get("hard_skills", [])

    @property
    def soft_skills(self) -> List[str]:
        """Список Soft Skills."""
        return self._config.get("soft_skills", [])

    @property
    def tools(self) -> List[str]:
        """Список Tools & Technologies."""
        return self._config.get("tools", [])

    @property
    def processing(self) -> Dict[str, Any]:
        """Параметры обработки данных."""
        return self._config.get("processing", {})

    @property
    def reporting(self) -> Dict[str, Any]:
        """Параметры отчётности."""
        return self._config.get("reporting", {})

    @property
    def advanced_categories(self) -> Dict[str, List[str]]:
        """Расширенные категории для детальной аналитики."""
        return self._config.get("advanced_categories", {})

    def get_all_skills(self) -> Dict[str, List[str]]:
        """
        Получение всех словарей навыков.

        Returns:
            Словарь {category: [skills]}
        """
        return {
            "hard_skills": self.hard_skills,
            "soft_skills": self.soft_skills,
            "tools": self.tools
        }

    def get_advanced_category_skills(self) -> Dict[str, Dict[str, List[str]]]:
        """
        Получение расширенных категорий навыков.

        Returns:
            Словарь {category_name: {subcategory: [skills]}}
        """
        return self._config.get("advanced_categories", {})


# =============================================================================
# Инициализация глобальных объектов
# =============================================================================

# Определяем базовую директорию проекта
PROJECT_ROOT = Path(__file__).parent.parent

# Загружаем переменные окружения из .env
load_dotenv(PROJECT_ROOT / ".env")

# Создаём объект настроек из переменных окружения
settings = Settings(
    hh_user_email=os.getenv("HH_USER_EMAIL", ""),
    api_request_delay=float(os.getenv("API_REQUEST_DELAY", "1.0")),
    max_pages=int(os.getenv("MAX_PAGES", "10")),
    days_back=int(os.getenv("DAYS_BACK", "30")),
    data_dir=PROJECT_ROOT / os.getenv("DATA_DIR", "data"),
    raw_data_dir=PROJECT_ROOT / os.getenv("RAW_DATA_DIR", "data/raw"),
    processed_data_dir=PROJECT_ROOT / os.getenv("PROCESSED_DATA_DIR", "data/processed"),
    reports_dir=PROJECT_ROOT / os.getenv("REPORTS_DIR", "data/reports"),
    db_path=PROJECT_ROOT / os.getenv("DB_PATH", "data/hh_vacancies.db"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_file=PROJECT_ROOT / os.getenv("LOG_FILE", "logs/hh_analytics.log"),
)

# Загружаем конфигурацию из YAML
config_loader = ConfigLoader(PROJECT_ROOT / "config.yaml")

# Словари навыков для удобного импорта
SEARCH_QUERIES = config_loader.search_queries
HARD_SKILLS = config_loader.hard_skills
SOFT_SKILLS = config_loader.soft_skills
TOOLS = config_loader.tools
