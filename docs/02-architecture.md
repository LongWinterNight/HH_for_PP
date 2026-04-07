# 🏗 Архитектура и схема работы

## Общая архитектура

Проект построен на **ETL-архитектуре** (Extract → Transform → Load → Analyze):

```
[HH.ru API] → Extract → [Raw JSON] → Transform → [Processed DataFrame]
     ↓
  Load → [SQLite/PostgreSQL] → Analyze → [Dashboard/Reports]
```

## Компоненты системы

### 1. Парсер (Extract)

**Файлы:**
- `optimized_parser.py` — основной парсер
- `src/api_client.py` — клиент HH API
- `src/collector.py` — сборщик вакансий

**Поток данных:**
```
User запускает парсер
    ↓
Проверка email (403 если не настроен)
    ↓
Для каждого запроса:
    1. Проверка кэша (api_cache.db)
    2. Если нет в кэше → запрос к HH API
    3. Сохранение в кэш (24 часа TTL)
    4. Сохранение в raw JSON
    ↓
Векторизованная обработка навыков
    ↓
Загрузка в БД (upsert)
```

**Кэширование:**
```python
# APICache в optimized_parser.py
class APICache:
    # Таблица: api_cache
    # Поля: url, response_json, timestamp
    # Автоочистка: >7 дней
```

**Rate Limiting:**
- Задержка между запросами: `API_REQUEST_DELAY=1.0s`
- Retry logic: tenacity (экспоненциальный backoff)
- Обработка 429 ошибок

### 2. Процессор (Transform)

**Файлы:**
- `src/processor.py` — VacancyProcessor
- `config.yaml` — словари навыков

**Что делает:**
```python
class VacancyProcessor:
    def process_vacancies(df):
        # 1. Извлечение hard_skills из description
        # 2. Извлечение soft_skills
        # 3. Извлечение tools/технологий
        # 4. Подсчёт skill_count
        # 5. Нормализация зарплат
        return processed_df
```

### 3. Хранилище (Load)

**Файлы:**
- `src/storage.py` — VacancyStorage

**Таблицы:**
```sql
-- vacancies (основная)
id, vacancy_id (UNIQUE), vacancy_name, published_at,
all_skills, hard_skills, soft_skills, tools,
skill_count, hard_skill_count, soft_skill_count, tools_count,
salary_from, salary_to, salary_currency, salary_gross,
employer_name, employer_id, employer_url, vacancy_url,
experience, employment, schedule, area,
created_at, updated_at

-- parser_runs (журнал парсингов)
id, started_at, completed_at, status,
keywords (JSON), max_pages, days_back,
is_incremental, use_cache,
vacancies_collected, vacancies_new, vacancies_updated,
errors_count, error_message, created_at

-- app_settings (синглтон, id=1)
id=1, last_parse_at, last_successful_parse_at,
total_parses, total_vacancies_collected,
app_version, config_version, updated_at
```

**Индексы:**
```sql
idx_vacancy_id, idx_employer, idx_area,
idx_published_at, idx_experience,
idx_salary_from, idx_created_at
```

**Режимы сохранения:**
- `save_dataframe()` — полная замена (if_exists='replace')
- `save_vacancies_incremental()` — upsert логика (INSERT OR UPDATE)

### 4. Аналитика (Analyze)

**Файлы:**
- `src/analyzer.py` — базовая аналитика
- `src/advanced_analyzer.py` — расширенная аналитика

**Что считает:**
```python
class VacancyAnalyzer:
    # Частота навыков (hard/soft/tools)
    # Статистика зарплат (по опыту, регионам, занятости)
    # Excel-отчёты с графиками (openpyxl)

class AdvancedAnalytics:
    # Группировки: LLM, Vector DB, RAG, ML libs, Cloud, Docker, CI/CD
    # Карта связей "вакансия-навык"
    # Детальный Excel-отчёт (6 листов)
```

### 5. Веб-приложение (Serve)

**Файлы:**
- `web/app/main.py` — FastAPI сервер
- `web/static/index.html` — Vue.js 3 SPA
- `web/run.py` — точка входа (uvicorn)

**Endpoints:**
```
GET  /                      → index.html
GET  /analytics             → analytics.html
GET  /api/health            → {"status": "ok"}
GET  /api/dashboard         → KPI, навыки, вакансии, sparklines
GET  /api/vacancies         → список с фильтрами/сортировкой
GET  /api/analytics/kpi     → 8 KPI метрик с трендами
GET  /api/analytics/top-skills → топ навыков (hard/soft/tools)
GET  /api/analytics/distribution → опыт, занятость, зарплаты, регионы
GET  /api/analytics/advanced → технологии, hard/soft skills
GET  /api/parser/status     → статус парсера
POST /api/parser/start      → запуск парсера (требует email!)
GET  /api/parser/stop       → остановка
GET  /api/parser/last-run   → последний запуск
GET  /api/parser/history    → история запусков
GET  /api/user/email        → статус email
POST /api/user/email        → сохранить email
GET  /api/app/settings      → настройки приложения
GET  /api/reports/list      → список отчётов
GET  /api/export/vacancies  → экспорт (xlsx/csv)
POST /api/export/analytics  → экспорт аналитики
GET  /api/professions/*     → каталог профессий
GET  /api/autocomplete/*    → автодополнение
```

**Фоновые задачи:**
- Парсер запускается через `BackgroundTasks` FastAPI
- Автоматическое обновление статуса каждые 2 сек (polling)
- Генерация отчётов в фоне

## Поток запроса пользователя

```
1. Пользователь открывает http://localhost:8000
2. FastAPI отдаёт index.html (статический файл)
3. Vue.js делает fetch('/api/dashboard')
4. FastAPI читает из SQLite → возвращает JSON
5. Vue.js рендерит графики Chart.js
6. Парсинг: POST /api/parser/start → BackgroundTask → in-progress polling
```

## Безопасность

- **Email required**: 403 при попытке запустить парсер без настроенного email
- **Rate limiting**: задержка 1с между запросами к HH API
- **.env**: не коммитится в Git (секреты)
- **CORS**: разрешены все origins (для dev, изменить для prod)
