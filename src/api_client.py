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


class ПричинаОтказа:
    """
    Почему источник не отдал данные.

    Причина нужна не для журнала, а для человека: «нет токена» и «сеть
    недоступна» требуют разных действий, а в общем сообщении об ошибке
    они неразличимы. Раньше в интерфейс уходил текст исключения — по
    нему нельзя было понять ни что случилось, ни что делать.
    """

    НЕТ_ТОКЕНА = "no_token"
    ТОКЕН_ОТКЛОНЁН = "token_rejected"
    НЕТ_ПОЧТЫ = "no_email"
    СЛИШКОМ_ЧАСТО = "rate_limited"
    СЕТЬ = "network"
    НЕИЗВЕСТНО = "unknown"


class ОтказИсточника(Exception):
    """Источник отказал по известной причине."""

    def __init__(self, причина: str, подробности: str = "") -> None:
        super().__init__(подробности or причина)
        self.причина = причина
        self.подробности = подробности


class TooManyRequests(Exception):
    """
    Источник отказал из-за частоты запросов (HTTP 429).

    Отдельный тип, а не общий HTTPError: по нему настроен повтор, и его
    же считает статистика сбора. Прежде отказ бросался как HTTPError,
    который в условие повтора не входил, — страница молча терялась и в
    данных выглядела как отсутствие вакансий.
    """

    def __init__(self, retry_after: Optional[float] = None) -> None:
        super().__init__("Источник просит снизить частоту запросов")
        self.retry_after = retry_after
        self.причина = ПричинаОтказа.СЛИШКОМ_ЧАСТО


# В каких полях вакансии источник ищет слова запроса.
#
# Без ограничения он ищет везде, включая название компании: по запросу
# «Арт-директор» приходила 331 вакансия ресторанов работодателя
# «АРТ РЕСТ». Замер 10.10.2026 по ответам самого источника:
#
#     запрос         везде   название   название и описание
#     Арт-директор     736        106                    401
#     3dsmax           702          3                    702
#     рендер           176          2                    176
#
# Название и описание снимают ровно найденное по названию компании и
# ничего не отнимают у запросов-навыков. Только название оставляет от
# «3dsmax» три вакансии из семисот: навык называют в описании, а не в
# должности.
ПОЛЯ_ПОИСКА = ("name", "description")


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

    # Потолок паузы из заголовка Retry-After: источник может попросить
    # ждать очень долго, а сбор не должен зависать на часы.
    MAX_RETRY_AFTER = 60.0

    # Столько успешных запросов подряд возвращают задержку к базовой.
    SUCCESSES_TO_RESTORE = 20

    def __init__(
        self,
        email: Optional[str] = None,
        delay: float = 1.0,
        access_token: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> None:
        """
        Инициализация клиента.

        Args:
            email: Email для заголовка User-Agent. Если None, берётся из .env
            delay: Задержка между запросами в секундах (по умолчанию 1.0)
            access_token: OAuth access_token приложения HH.ru. Если None,
                берётся из .env (HH_ACCESS_TOKEN). Обязателен с 2025 года —
                без него endpoint /vacancies возвращает 403 forbidden.
            proxy: URL прокси (http/socks) для запросов. Если None, берётся
                из .env (HH_PROXY). Пусто — прямое соединение.

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

        # OAuth-токен: с 2025 года HH.ru закрыл анонимный доступ к /vacancies
        self.access_token = access_token if access_token is not None else settings.hh_access_token
        if not self.access_token:
            logger.warning(
                "HH_ACCESS_TOKEN не задан. Endpoint /vacancies закрыт для "
                "анонимных запросов (403 forbidden). Зарегистрируйте приложение "
                "на https://dev.hh.ru/admin и укажите токен в .env"
            )

        self.base_url = "https://api.hh.ru/"

        # Базовая задержка — та, к которой сбор возвращается после
        # отказов. Текущая может быть выше, но только временно.
        self.base_delay = delay
        self.delay = delay

        # Сколько раз источник просил снизить частоту за время жизни
        # клиента. Число уходит в статистику сбора: по нему видно, что
        # выборка неполна не потому, что вакансий нет.
        self.rate_limit_hits = 0
        self._successes_since_limit = 0

        # Создаём сессию для переиспользования TCP-соединений
        self.session = requests.Session()

        # Прокси для обхода региональных ограничений сайта hh.ru
        proxy = proxy if proxy is not None else settings.hh_proxy
        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})
            logger.info(f"HHAPIClient использует прокси: {proxy}")

        # HH.ru требует два заголовка идентификации начиная с 2024 года:
        # User-Agent — стандартный HTTP-заголовок
        # HH-User-Agent — специфичный заголовок API HH.ru (без него 403)
        ua = f"HHAnalytics/1.0 ({self.email})"
        headers = {
            "User-Agent": ua,
            "HH-User-Agent": ua,
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            "Referer": "https://hh.ru/",
        }
        # OAuth 2.0: авторизуем запросы токеном приложения
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        self.session.headers.update(headers)

        logger.info(
            f"HHAPIClient инициализирован с email: {self.email}, delay: {delay}s, "
            f"токен: {'да' if self.access_token else 'нет'}"
        )

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
            retry=(
                retry_if_result(is_server_error)
                | retry_if_exception_type((requests.ConnectionError, requests.Timeout, TooManyRequests))
            ),
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

            # Источник просит снизить частоту
            if response.status_code == 429:
                self.rate_limit_hits += 1

                # Сколько ждать, говорит сам источник. Заголовка может не
                # быть — тогда решает стратегия повторов.
                retry_after = None
                header = response.headers.get("Retry-After")
                if header:
                    try:
                        retry_after = min(float(header), self.MAX_RETRY_AFTER)
                    except ValueError:
                        retry_after = None

                # Задержка растёт временно и с потолком: без потолка
                # достаточно нескольких отказов, чтобы сбор встал.
                self.delay = min(self.delay * 2, self.base_delay * 8)
                logger.warning(
                    f"Источник просит снизить частоту (429). Пауза "
                    f"{retry_after if retry_after else 'по стратегии повторов'}, "
                    f"задержка между запросами {self.delay:.1f}s"
                )

                if retry_after:
                    time.sleep(retry_after)

                raise TooManyRequests(retry_after)

            # Для 4xx ошибок (кроме 429) — не повторяем, просто логируем
            if 400 <= response.status_code < 500:
                # 403 на /vacancies почти всегда = отсутствие/протухший OAuth-токен
                if response.status_code == 403:
                    hint = (
                        " Проверьте HH_ACCESS_TOKEN в .env — с 2025 г. поиск "
                        "вакансий требует токен приложения (dev.hh.ru/admin)."
                        if not self.access_token
                        else " Токен задан, но отклонён — возможно, протух; "
                             "обновите access_token на dev.hh.ru/admin."
                    )
                    logger.error(f"HTTP 403 forbidden от {url}.{hint} Ответ: {response.text[:200]}")
                else:
                    logger.error(f"Ошибка клиента: {response.status_code}, {response.text[:200]}")
                return response

            # Для 5xx — выбрасываем исключение для retry
            if response.status_code >= 500:
                logger.warning(f"Ошибка сервера: {response.status_code}. Повторная попытка...")
                response.raise_for_status()

            return response

        try:
            response = _execute_request()

            # Успешная серия возвращает задержку к базовой: разовый отказ
            # не должен замедлять весь оставшийся сбор.
            if response.status_code < 400:
                self._successes_since_limit += 1
                if self._successes_since_limit >= self.SUCCESSES_TO_RESTORE and self.delay > self.base_delay:
                    logger.info(f"Задержка возвращена к базовой: {self.base_delay:.1f}s")
                    self.delay = self.base_delay
                    self._successes_since_limit = 0

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
        per_page: int = 100,
        order_by: str = "publication_time",
        date_from: Optional[str] = None,
        area: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Поиск вакансий по ключевому слову.

        Args:
            keyword: Поисковый запрос (например, "Python developer" или "LLM")
            page: Номер страницы для пагинации (начинается с 0)
            per_page: Количество вакансий на странице (максимум 100)
            order_by: Порядок выдачи. По умолчанию по дате публикации, а
                не по релевантности: сбор ограничивает выборку возрастом
                вакансий, и при сортировке по релевантности старые
                вакансии перемешаны со свежими — прекратить обход в
                нужном месте становится невозможно
            date_from: Нижняя граница даты публикации в формате ISO
                (`2026-08-08` или `2026-08-08T00:00:00`). Отсекает старые
                вакансии на стороне источника: иначе они скачиваются и
                тут же выбрасываются, расходуя лимит запросов впустую
            area: Идентификатор региона из справочника hh.ru (`1` —
                Москва, `2` — Санкт-Петербург, `113` — Россия). Без него
                запрос идёт по всей стране, а источник отдаёт не больше
                2000 вакансий на запрос: по популярной профессии мы
                видим первую тысячу и не знаем, что за ней. Разбиение
                того же запроса по регионам — единственный способ уйти
                глубже этого предела
            date_to: Верхняя граница даты публикации. Вместе с
                `date_from` задаёт окно: им режется запрос, который
                упёрся в предел выдачи, а делить его по регионам уже
                некуда — например, вакансии одного города

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
            "order_by": order_by,
            "search_field": list(ПОЛЯ_ПОИСКА),
        }
        if date_from:
            params["date_from"] = date_from
        # Регион уходит в запрос только когда он задан: пустой area
        # источник понимает иначе, чем его отсутствие.
        if area:
            params["area"] = area
        if date_to:
            params["date_to"] = date_to

        где = f", регион {area}" if area else ""
        logger.info(f"Поиск вакансий: '{keyword}', страница {page}{где}")

        return self._make_request(url, params)

    def get_areas(self) -> Optional[Any]:
        """
        Справочник регионов: страны, их регионы и города.

        Нужен, чтобы резать запрос на срезы: источник отдаёт не больше
        2000 вакансий на запрос, и по популярной профессии мы видим
        пятую часть выдачи. Тот же запрос по регионам обходит предел —
        у каждого своя выдача.

        Returns:
            Дерево регионов как его отдаёт источник, либо None при
            ошибке. Справочник кладётся на диск (`src/regions.py`):
            он меняется раз в год, и спрашивать его на каждый сбор
            значит тратить лимит запросов на неизменное.
        """
        url = f"{self.base_url}areas"

        logger.info("Получение справочника регионов")
        return self._make_request(url, {})

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

    def проверить_доступ(self) -> Dict[str, Any]:
        """
        Проверить, отвечает ли источник и пускает ли он нас.

        Один лёгкий запрос вместо целого сбора: человеку нужно знать, что
        доступ работает, до того как он запустит работу на десять минут и
        получит отказ на середине.

        Returns:
            {"доступно": bool, "задержка_мс": int, "причина": str | None,
             "подробности": str}
        """
        import time as _time

        if not self.email:
            return {
                "доступно": False,
                "задержка_мс": 0,
                "причина": ПричинаОтказа.НЕТ_ПОЧТЫ,
                "подробности": "Источник требует контактную почту в заголовке запроса",
            }

        начало = _time.monotonic()
        try:
            ответ = self.session.get(
                f"{self.base_url}vacancies",
                params={"text": "python", "per_page": 1},
                timeout=10,
            )
        except requests.RequestException as e:
            return {
                "доступно": False,
                "задержка_мс": int((_time.monotonic() - начало) * 1000),
                "причина": ПричинаОтказа.СЕТЬ,
                "подробности": f"Источник недоступен: {type(e).__name__}",
            }

        задержка = int((_time.monotonic() - начало) * 1000)

        if ответ.status_code == 200:
            return {"доступно": True, "задержка_мс": задержка, "причина": None, "подробности": ""}

        if ответ.status_code == 403:
            причина = ПричинаОтказа.НЕТ_ТОКЕНА if not self.access_token else ПричинаОтказа.ТОКЕН_ОТКЛОНЁН
            return {
                "доступно": False,
                "задержка_мс": задержка,
                "причина": причина,
                "подробности": ответ.text[:200],
            }

        if ответ.status_code == 429:
            return {
                "доступно": False,
                "задержка_мс": задержка,
                "причина": ПричинаОтказа.СЛИШКОМ_ЧАСТО,
                "подробности": "Источник просит снизить частоту запросов",
            }

        return {
            "доступно": False,
            "задержка_мс": задержка,
            "причина": ПричинаОтказа.НЕИЗВЕСТНО,
            "подробности": f"Источник ответил {ответ.status_code}",
        }

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
