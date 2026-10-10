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
    hh_access_token: str = Field(
        default="",
        description="OAuth access_token приложения HH.ru (dev.hh.ru/admin). "
                    "Обязателен: с 2025 г. endpoint /vacancies закрыт для анонимов"
    )
    hh_proxy: str = Field(
        default="",
        description="HTTP/SOCKS-прокси для запросов к HH.ru, например "
                    "http://127.0.0.1:7899 (пусто — прямое соединение)"
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
    detailed_pages: int = Field(
        default=0,
        description="Сколько страниц выдачи разбирать с карточками вакансий. "
                    "0 — карточка берётся у каждой новой вакансии, сколько бы "
                    "их ни было: без карточки у вакансии 2,4 навыка вместо "
                    "14,7, и пятая часть базы остаётся пустой"
    )
    days_back: int = Field(
        default=30,
        description="За сколько дней собирать вакансии"
    )
    кэш_выдачи_часов: int = Field(
        default=6,
        description="Сколько часов живёт закэшированная страница выдачи. "
                    "Выдача меняется быстро: работодатель публикует вакансию "
                    "утром, и вечерний сбор по вчерашнему кэшу её не увидит. "
                    "Шесть часов — компромисс между свежестью и числом "
                    "обращений к источнику"
    )
    кэш_карточек_часов: int = Field(
        default=168,
        description="Сколько часов живёт закэшированная карточка вакансии. "
                    "Карточка почти не меняется: работодатель правит текст "
                    "редко, а зарплата и статус приходят из выдачи. Неделя "
                    "экономит тысячи обращений при повторных сборах — "
                    "карточка запрашивается на каждую новую вакансию"
    )
    резать_упёршиеся: bool = Field(
        default=True,
        description="Резать запрос, упёршийся в предел выдачи, на срезы по "
                    "регионам и датам. Источник отдаёт не больше 2000 "
                    "вакансий на запрос: по «Рекрутеру» он знает 10 294 и "
                    "показывает пятую часть. Включено: внутри среза карточки "
                    "не запрашиваются (S4‑5a), поэтому обход стоит минут, а "
                    "не часов, — прежняя цена считалась вместе с ними"
    )
    max_slices: int = Field(
        default=100,
        description="Предохранитель: сколько срезов по регионам сбор вправе "
                    "обойти за один запуск. Без предела запрос по стране с "
                    "городами способен занять тысячи обращений к источнику"
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

    # Словарь навыков переехал в данные (`data/skills.yaml`, S7‑1a): он
    # меняется еженедельно, а конфиг приложения — раз в полгода. Свойства
    # остались, потому что их знает старый код обработки; читают они
    # теперь файл данных, а конфиг — только пока переноса не было.
    def раздел_из_конфига(self, ключ: str) -> List[str]:
        """
        Раздел словаря так, как он записан в самом конфиге.

        Нужен хранилищу словаря: пока файла данных нет, оно читает
        конфиг. Обращаться за этим к свойствам ниже нельзя — они сами
        спрашивают хранилище, и получился бы замкнутый круг.
        """
        return self._config.get(ключ, [])

    def _раздел_словаря(self, раздел: str, старый_ключ: str) -> List[str]:
        from src.skills_store import загрузить

        значения = загрузить().get(раздел)
        if значения:
            return значения
        return self._config.get(старый_ключ, [])

    @property
    def hard_skills(self) -> List[str]:
        """Список Hard Skills."""
        return self._раздел_словаря("hard", "hard_skills")

    @property
    def soft_skills(self) -> List[str]:
        """Список Soft Skills."""
        return self._раздел_словаря("soft", "soft_skills")

    @property
    def tools(self) -> List[str]:
        """Список Tools & Technologies."""
        return self._раздел_словаря("tools", "tools")

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
    hh_access_token=os.getenv("HH_ACCESS_TOKEN", ""),
    hh_proxy=os.getenv("HH_PROXY", ""),
    api_request_delay=float(os.getenv("API_REQUEST_DELAY", "1.0")),
    max_pages=int(os.getenv("MAX_PAGES", "10")),
    detailed_pages=int(os.getenv("DETAILED_PAGES", "0")),
    days_back=int(os.getenv("DAYS_BACK", "30")),
    кэш_выдачи_часов=int(os.getenv("КЭШ_ВЫДАЧИ_ЧАСОВ", "6")),
    кэш_карточек_часов=int(os.getenv("КЭШ_КАРТОЧЕК_ЧАСОВ", "168")),
    резать_упёршиеся=os.getenv("РЕЗАТЬ_УПЁРШИЕСЯ", os.getenv("SPLIT_BY_REGION", "true")).strip().lower()
    in ("1", "true", "yes", "да"),
    max_slices=int(os.getenv("MAX_SLICES", "100")),
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

# Поисковые запросы для удобного импорта.
SEARCH_QUERIES = config_loader.search_queries

# Словарей навыков здесь больше нет.
#
# Прежде рядом стояли HARD_SKILLS, SOFT_SKILLS и TOOLS — снимки словаря,
# сделанные в момент импорта модуля. Ими никто не пользовался, а вреда
# они приносили двояко: значение застывало на первом обращении, и, когда
# словарь переехал в данные (S7‑1a), эти строки замкнули импорт в круг —
# конфиг звал хранилище, которое в этот момент само загружалось.
#
# Словарь берут через `config_loader.hard_skills` или, лучше, напрямую
# из `src.skills_store`.
