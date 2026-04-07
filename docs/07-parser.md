# 🤖 Парсер вакансий

## Файлы

| Файл | Описание |
|------|----------|
| `optimized_parser.py` | Оптимизированный парсер с кэшем (~811 строк) |
| `src/api_client.py` | Клиент HH API (~360 строк) |
| `src/collector.py` | Стандартный сборщик вакансий |

## Архитектура парсера

```
User запускает парсер (POST /api/parser/start)
    ↓
Проверка email (403 если не настроен)
    ↓
Для каждого запроса из keywords:
    1. Проверить кэш (APICache)
    2. Если нет в кэше → GET https://api.hh.ru/vacancies
    3. Сохранить ответ в кэш (api_cache.db)
    4. Сохранить сырые данные в data/raw/
    ↓
Векторизованная обработка навыков
    ↓
Загрузка в БД (upsert)
    ↓
Обновление parser_runs + app_settings
```

## APICache (кэширование)

**Файл:** `optimized_parser.py`

```python
class APICache:
    # Таблица: api_cache
    # Поля: url, response_json, timestamp
    # TTL: 24 часа
    # Автоочистка: >7 дней
```

**Зачем:**
- Снижает нагрузку на HH API
- Ускоряет повторные запуски
- Защищает от бана (меньше запросов)

## OptimizedVacancyCollector

**Основные параметры:**
```python
OptimizedVacancyCollector(
    max_pages=10,           # Макс. страниц на запрос
    days_back=30,           # Дней назад
    use_cache=True,         # Использовать кэш
    incremental=True        # Только новые вакансии
)
```

**Методы:**
```python
collector.collect_all(keywords=["Python Developer", "Data Scientist"])
# Возвращает: {"total": N, "unique": M, "new": K, "updated": J}
```

**Инкрементальный режим:**
- Сравнивает vacancy_id с уже существующими в БД
- Загружает только новые вакансии
- Пропускает кэшированные запросы

## HHAPIClient

**Файл:** `src/api_client.py`

```python
class HHAPIClient:
    def __init__(self, email, delay=1.0):
        self.email = email
        self.delay = delay  # Задержка между запросами
        self.session = requests.Session()
        self.session.headers = {
            "User-Agent": f"HHAnalyticsBot/1.0 ({self.email})"
        }
```

**Rate Limiting:**
- Задержка: `API_REQUEST_DELAY=1.0s`
- Retry: tenacity (экспоненциальный backoff)
- Обработка 429 (Too Many Requests)

**Методы:**
```python
client.search_vacancies(keyword, page, per_page=100)
client.get_vacancy(vacancy_id)
client.get_area(area_id)
client.get_profession_areas(profession_id)
```

## Поток запроса к HH API

```
1. Формируем URL: https://api.hh.ru/vacancies?text=Python+Developer&page=0&per_page=100
2. Проверяем кэш (api_cache.db)
3. Если есть → возвращаем из кэша
4. Если нет → GET запрос + задержка 1с
5. Сохраняем в кэш (timestamp = now)
6. Возвращаем JSON
7. При ошибке 429 → ждём 60с → retry (max 3)
```

## Сохранение данных

```
Raw JSON → Processed DataFrame → SQLite (upsert)
     ↓              ↓                  ↓
data/raw/    data/processed/    hh_vacancies.db
*.json       *.csv              ├── vacancies
                                ├── parser_runs
                                └── app_settings
```

## Email защита

```python
# В web/app/main.py:
user_email = user_settings.get("hh_user_email")
if not user_email:
    raise HTTPException(403, "Настройте email через ⚙️")

logger.info(f"🔑 Парсер запущен с email: {user_email}")
```

## Логирование в консоли

При запуске парсера в консоли будет видно:
```
🔑 Парсер запущен с email: user@example.com
🔑 HHAPIClient инициализирован с email: user@example.com, delay: 1.0s
📡 Запросы к HH API будут отправляться от: user@example.com
📥 Запрос: Python Developer
✅ Сохранено: 150 вакансий (новых: 120, обновлено: 30)
```
