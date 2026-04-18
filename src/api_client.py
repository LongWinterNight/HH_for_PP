"""
Модуль для работы с HH.ru API.

Содержит класс HHAPIClient, который реализует:
- Rate limiting (не более 1 запроса в секунду по умолчанию)
- Экспоненциальную задержку при ошибках (Exponential Backoff)
- Обработку HTTP-ошибок (429, 5xx, 4xx)
- Логирование всех запросов

Важно: HH.ru требует заголовок User-Agent с контактным email.
Нарушение правил API может привести к блокировке.
"""

import time
from typing import Optional, Dict, List, Any

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    retry_if_result,
    RetryError,
)

from src.utils import get_logger
from src.config import settings

# Инициализируем логгер для модуля
logger = get_logger(__name__)


class HHAPIClient:
    """
    Клиент для работы с HH.ru API.

    Атрибуты:
        base_url (str): Базовый URL API HH.ru
        session (requests.Session): Сессия для переиспользования соединений
        delay (float): Задержка между запросами в секундах
        email (str): Email для заголовка User-Agent

    Пример использования:
        >>> client = HHAPIClient(email="your_email@example.com")
        >>> vacancies = client.search_vacancies(keyword="Python developer")
        >>> print(f"Найдено вакансий: {len(vacancies)}")
    """

    def __init__(self, email: Optional[str] = None, delay: float = 1.0) -> None:
        """
        Инициализация клиента.

        Args:
            email: Email для заголовка User-Agent. Если None, берётся из .env
            delay: Задержка между запросами в секундах (по умолчанию 1.0)

        Raises:
            ValueError: Если email не передан и не найден в окружении
        """
        # Берём email из параметра или из переменных окружения
        self.email = email or settings.hh_user_email
        if not self.email:
            raise ValueError(
                "Email для User-Agent не указан. "
                "Передайте его в конструктор или задайте HH_USER_EMAIL в .env"
            )

        self.base_url = "https://api.hh.ru/"
        self.delay = delay

        # Создаём сессию для переиспользования TCP-соединений
        # Это ускоряет работу при множественных запросах
        self.session = requests.Session()

        # HH.ru требует два заголовка идентификации начиная с 2024 года:
        # User-Agent — стандартный HTTP-заголовок
        # HH-User-Agent — специфичный заголовок API HH.ru (без него 403)
        ua = f"HHAnalytics/1.0 ({self.email})"
        self.session.headers.update({
            "User-Agent": ua,
            "HH-User-Agent": ua,
        })


        logger.info(f"HHAPIClient инициализирован с email: {self.email}, delay: {delay}s")

    def _make_request(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Внутренний метод для выполнения HTTP-запросов с retry logic.

        Использует декоратор @retry из библиотеки tenacity для:
        - Повторных попыток при 5xx ошибках (до 3 раз)
        - Экспоненциальной задержки между попытками
        - Отдельной обработки 429 ошибки (Too Many Requests)

        Args:
            url: Полный URL для запроса
            params: Словарь query-параметров

        Returns:
            JSON-ответ в виде словаря или None при критической ошибке

        Note:
            При 4xx ошибках (кроме 429) повторные попытки не делаются,
            так как это ошибки клиента (неверный запрос, ресурс не найден)
        """
        # Функция для проверки результата — возвращает True, если нужно повторить
        def is_server_error(result: Optional[requests.Response]) -> bool:
            """Повторяем запрос только при 5xx ошибках."""
            if result is None:
                return False
            return 500 <= result.status_code < 600

        # Функция для проверки исключения — повторяем при ошибках сети
        def is_network_error(exception: Exception) -> bool:
            """Повторяем при ошибках подключения."""
            return isinstance(exception, (requests.ConnectionError, requests.Timeout))

        # Декоратор retry настраивает стратегию повторных попыток
        @retry(
            # Повторяем при 5xx ошибках ИЛИ ошибках сети
            retry=(retry_if_result(is_server_error) | retry_if_exception_type((requests.ConnectionError, requests.Timeout))),
            # Максимум 3 попытки
            stop=stop_after_attempt(3),
            # Экспоненциальная задержка: 1с, 2с, 4с (с джиттером)
            wait=wait_exponential(multiplier=1, min=1, max=10),
            # Логгируем каждую попытку
            reraise=True,
        )
        def _execute_request() -> requests.Response:
            # Rate limiting: ждём перед каждым запросом
            time.sleep(self.delay)

            logger.debug(f"Выполняется запрос: {url}, params: {params}")

            response = self.session.get(url, params=params, timeout=30)

            # Логгируем статус ответа
            logger.debug(f"Получен ответ: {response.status_code}")

            # Специальная обработка 429 ошибки (Too Many Requests)
            if response.status_code == 429:
                logger.warning("Получен HTTP 429 (Too Many Requests). Увеличиваю задержку...")
                # Увеличиваем задержку в 2 раза на будущее
                self.delay *= 2
                # Выбрасываем исключение для повторной попытки
                raise requests.exceptions.HTTPError("Rate limit exceeded")

            # Для 4xx ошибок (кроме 429) — не повторяем, просто логируем
            if 400 <= response.status_code < 500:
                logger.error(f"Ошибка клиента: {response.status_code}, {response.text}")
                return response

            # Для 5xx — выбрасываем исключение для retry
            if response.status_code >= 500:
                logger.warning(f"Ошибка сервера: {response.status_code}. Повторная попытка...")
                response.raise_for_status()

            return response

        try:
            response = _execute_request()

            # После успешного запроса проверяем статус
            if response.status_code >= 400:
                logger.warning(f"Завершаем с ошибкой {response.status_code}")
                return None

            return response.json()

        except RetryError as e:
            # Если все попытки исчерпаны
            logger.error(f"Все попытки исчерпаны после {e.last_attempt.attempt_number} раз")
            return None
        except requests.RequestException as e:
            # Ошибки сети, таймауты
            logger.error(f"Ошибка запроса: {type(e).__name__} - {e}")
            return None

    def search_vacancies(
        self,
        keyword: str,
        page: int = 0,
        per_page: int = 100
    ) -> Optional[Dict[str, Any]]:
        """
        Поиск вакансий по ключевому слову.

        Args:
            keyword: Поисковый запрос (например, "Python developer" или "LLM")
            page: Номер страницы для пагинации (начинается с 0)
            per_page: Количество вакансий на странице (максимум 100)

        Returns:
            Словарь с результатами поиска или None при ошибке.
            Структура ответа:
            {
                "items": List[Dict],  # Список вакансий
                "found": int,         # Общее количество найденных
                "pages": int,         # Количество страниц
                "page": int,          # Текущая страница
                "per_page": int       # Вакансий на странице
            }

        Пример:
            >>> client = HHAPIClient()
            >>> result = client.search_vacancies("Python developer", page=0, per_page=100)
            >>> if result:
            ...     print(f"Найдено вакансий: {result['found']}")
            ...     for vacancy in result['items']:
            ...         print(vacancy['name'])
        """
        # Формируем URL для поиска вакансий
        # Документация: https://github.com/hhru/api/blob/master/docs/vacancies.md
        url = f"{self.base_url}vacancies"

        # Параметры запроса согласно документации HH API
        params = {
            "text": keyword,
            "page": page,
            "per_page": per_page,
            # area: можно добавить регион (например, 1 для Москвы)
            # order_by: можно сортировать по релевантности или дате
        }

        logger.info(f"Поиск вакансий: '{keyword}', страница {page}")

        return self._make_request(url, params)

    def get_vacancy_details(self, vacancy_id: str) -> Optional[Dict[str, Any]]:
        """
        Получение детальной информации о вакансии по ID.

        Args:
            vacancy_id: Уникальный идентификатор вакансии (строка)

        Returns:
            Полная информация о вакансии или None при ошибке.
            Структура ответа включает:
            - name: название вакансии
            - employer: информация о работодателе
            - description: полное описание
            - skills: требуемые навыки
            - salary: информация о зарплате
            - schedule: график работы
            - и другие поля

        Пример:
            >>> client = HHAPIClient()
            >>> vacancy = client.get_vacancy_details("12345678")
            >>> if vacancy:
            ...     print(f"Вакансия: {vacancy['name']}")
            ...     print(f"Зарплата: {vacancy.get('salary', 'не указана')}")
        """
        # Формируем URL для получения деталей вакансии
        url = f"{self.base_url}vacancies/{vacancy_id}"

        logger.info(f"Получение деталей вакансии: {vacancy_id}")

        return self._make_request(url)

    def close(self) -> None:
        """
        Закрытие сессии и освобождение ресурсов.

        Рекомендуется вызывать после завершения работы с клиентом.
        """
        self.session.close()
        logger.info("Сессия HHAPIClient закрыта")

    def __enter__(self) -> "HHAPIClient":
        """Поддержка контекстного менеджера (with statement)."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Автоматическое закрытие сессии при выходе из контекста."""
        self.close()


# =============================================================================
# Блок для тестирования модуля
# =============================================================================

if __name__ == "__main__":
    """
    Пример использования HHAPIClient для тестирования.

    Перед запуском убедитесь, что:
    1. В .env файле указан HH_USER_EMAIL=your_email@example.com
    2. У вас есть подключение к интернету
    3. Вы не превысили лимиты API HH.ru

    Запуск: python -m src.api_client
    """

    # Настраиваем логгер для консольного вывода (уровень INFO)
    import logging
    logging.getLogger("src").setLevel(logging.INFO)

    print("=" * 60)
    print("Тестирование HHAPIClient")
    print("=" * 60)

    # Используем контекстный менеджер для автоматического закрытия сессии
    with HHAPIClient() as client:
        # Тест 1: Поиск вакансий по ключевому слову
        print("\n🔍 Тест 1: Поиск вакансий 'Python developer'")
        print("-" * 60)

        search_result = client.search_vacancies(
            keyword="Python developer",
            page=0,
            per_page=5  # Берём мало для быстрого теста
        )

        if search_result:
            print(f"✅ Найдено вакансий: {search_result['found']}")
            print(f"📄 Страниц: {search_result['pages']}")
            print(f"📋 Показано: {len(search_result['items'])}")

            if search_result['items']:
                first_vacancy = search_result['items'][0]
                print(f"\nПервая вакансия:")
                print(f"  • Название: {first_vacancy['name']}")
                print(f"  • Работодатель: {first_vacancy.get('employer', {}).get('name', 'N/A')}")
                print(f"  • ID: {first_vacancy['id']}")
        else:
            print("❌ Ошибка при поиске вакансий")

        # Тест 2: Получение деталей вакансии (если есть ID из предыдущего запроса)
        if search_result and search_result['items']:
            vacancy_id = search_result['items'][0]['id']

            print(f"\n📄 Тест 2: Детали вакансии {vacancy_id}")
            print("-" * 60)

            details = client.get_vacancy_details(vacancy_id)

            if details:
                print(f"✅ Вакансия: {details['name']}")
                print(f"🏢 Работодатель: {details.get('employer', {}).get('name', 'N/A')}")

                # Информация о зарплате
                salary = details.get('salary')
                if salary:
                    from_currency = salary.get('from', 'не указана')
                    to_currency = salary.get('to', '')
                    currency = salary.get('currency', 'RUB')
                    print(f"💰 Зарплата: от {from_currency} {currency}")
                else:
                    print("💰 Зарплата: не указана")

                # Ключевые навыки
                skills = details.get('key_skills', [])
                if skills:
                    skill_names = [s['name'] for s in skills[:5]]  # Первые 5
                    print(f"🛠 Навыки: {', '.join(skill_names)}")
            else:
                print("❌ Ошибка при получении деталей")

    print("\n" + "=" * 60)
    print("Тестирование завершено!")
    print("=" * 60)
