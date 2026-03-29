"""
Модуль утилит для проекта.

Содержит вспомогательные функции:
- Настройка логгера с цветным выводом
- Валидаторы данных
- Общие вспомогательные функции
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import colorlog


def get_logger(
    name: str,
    level: Optional[str] = None,
    log_file: Optional[Path] = None
) -> logging.Logger:
    """
    Создание и настройка логгера.

    Использует colorlog для цветного вывода в консоль:
    - INFO — зелёный
    - WARNING — жёлтый
    - ERROR — красный
    - CRITICAL — красный жирный

    Args:
        name: Имя логгера (обычно __name__ модуля)
        level: Уровень логирования (по умолчанию из settings)
        log_file: Путь к файлу для записи логов

    Returns:
        Настроенный экземпляр logging.Logger

    Пример:
        >>> logger = get_logger(__name__)
        >>> logger.info("Сообщение")
    """
    from src.config import settings

    # Получаем уровень из настроек или используем INFO
    log_level = getattr(logging, level or settings.log_level.upper(), logging.INFO)

    # Создаём логгер
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Если уже есть обработчики — не добавляем новые
    if logger.handlers:
        return logger

    # Формат для консольного вывода (с цветами)
    console_format = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        }
    )

    # Формат для файлового вывода (без цветов)
    file_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # Файловый обработчик (если указан файл)
    if log_file:
        # Создаём директорию для логов если её нет
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger


def ensure_dir(directory: Path) -> Path:
    """
    Создание директории если она не существует.

    Args:
        directory: Путь к директории

    Returns:
        Тот же путь (для chaining)

    Пример:
        >>> ensure_dir(Path("data/raw"))
        PosixPath('data/raw')
    """
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Обрезка текста до указанной длины.

    Args:
        text: Исходный текст
        max_length: Максимальная длина
        suffix: Суффикс для обрезанного текста

    Returns:
        Обрезанный текст

    Пример:
        >>> truncate_text("Длинный текст", 10)
        'Длинный...'
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Безопасное деление с обработкой деления на ноль.

    Args:
        numerator: Числитель
        denominator: Знаменатель
        default: Значение по умолчанию при делении на ноль

    Returns:
        Результат деления или default

    Пример:
        >>> safe_divide(10, 0)
        0.0
        >>> safe_divide(10, 2)
        5.0
    """
    if denominator == 0:
        return default
    return numerator / denominator


def format_number(num: int) -> str:
    """
    Форматирование числа с разделителями тысяч.

    Args:
        num: Число для форматирования

    Returns:
        Отформатированная строка

    Пример:
        >>> format_number(1000000)
        '1 000 000'
    """
    return f"{num:,}".replace(",", " ")


def validate_email(email: str) -> bool:
    """
    Простая валидация email.

    Args:
        email: Email для проверки

    Returns:
        True если email валиден

    Note:
        Это базовая проверка формата, не гарантирует
        существование почтового ящика.
    """
    import re
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email))
