# 📁 Структура проекта

## Дерево файлов

```
HH_Parsing/
├── .env                              # Секреты (не коммитится!)
├── requirements.txt                  # Python зависимости
│
├── hh_analytics/                     # Основной проект
│   │
│   ├── main.py                       # ETL точка входа (CLI)
│   ├── optimized_parser.py           # Оптимизированный парсер с кэшем
│   ├── config.yaml                   # Конфигурация (запросы, навыки)
│   ├── aggressive_categorization.py  # Категоризация вакансий
│   ├── clean_skills.py               # Очистка навыков
│   ├── collect_professions.py        # Сбор профессий
│   ├── create_professions_catalog.py # Создание каталога
│   ├── fill_all_domains.py           # Заполнение доменов
│   ├── fill_empty_domains.py         # Заполнение пустых доменов
│   ├── final_distribution.py         # Финальное распределение
│   ├── fix_domains.py                # Исправление доменов
│   ├── check_demo_ready.py           # Проверка готовности к демо
│   ├── check_functionality.py        # Проверка функциональности
│   │
│   ├── src/                          # Исходный код
│   │   ├── __init__.py
│   │   ├── api_client.py             # Клиент HH API (retry, rate limit)
│   │   ├── collector.py              # Стандартный сборщик вакансий
│   │   ├── processor.py              # Обработка и извлечение навыков
│   │   ├── storage.py                # SQLite ORM + методы БД
│   │   ├── analyzer.py               # Базовая аналитика
│   │   ├── advanced_analyzer.py      # Расширенная аналитика
│   │   ├── config.py                 # Загрузчик конфига (pydantic)
│   │   ├── db_cli.py                 # CLI для БД
│   │   └── utils.py                  # Утилиты (логгер, dirs)
│   │
│   ├── web/                          # Веб-приложение
│   │   ├── run.py                    # Точка входа (uvicorn)
│   │   ├── test_api.py               # Тесты API
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   └── main.py               # FastAPI сервер (все endpoints)
│   │   └── static/
│   │       └── index.html            # Vue.js 3 SPA (~4300 строк)
│   │
│   ├── data/                         # Данные
│   │   ├── hh_vacancies.db           # SQLite БД (vacancies, parser_runs, app_settings)
│   │   ├── api_cache.db              # Кэш API запросов
│   │   ├── professions_catalog.json  # Каталог профессий
│   │   ├── raw/                      # Сырые JSON файлы
│   │   │   ├── all_vacancies_*.json
│   │   │   └── vacancies_*.json
│   │   ├── processed/                # Обработанные CSV/Parquet
│   │   └── reports/                  # Сгенерированные отчёты (xlsx, pdf)
│   │
│   ├── logs/                         # Логи
│   │   └── hh_analytics.log
│   │
│   ├── tests/                        # Unit тесты
│   │   ├── __init__.py
│   │   ├── test_analyzer.py
│   │   ├── test_api_client.py
│   │   └── test_processor.py
│   │
│   ├── docs/                         # Документация (этот раздел)
│   │   ├── 01-overview.md
│   │   ├── 02-architecture.md
│   │   ├── 03-file-structure.md     ← этот файл
│   │   ├── 04-frontend.md
│   │   ├── 05-backend.md
│   │   ├── 06-database.md
│   │   ├── 07-parser.md
│   │   ├── 08-api-reference.md
│   │   ├── 09-deployment.md
│   │   └── 10-security.md
│   │
│   ├── .env                          # Локальные секреты
│   ├── .env.example                  # Шаблон .env
│   ├── .gitignore                    # Git игнор
│   ├── .editorconfig
│   ├── pyproject.toml                # Метаданные проекта
│   ├── requirements.txt              # Зависимости
│   ├── README.md                     # Главная документация
│   ├── CHANGELOG.md
│   ├── CONTRIBUTING.md
│   ├── CODE_OF_CONDUCT.md
│   ├── SECURITY.md
│   ├── DEMO_CHECKLIST.md
│   ├── QUICKSTART.md
│   ├── ROADMAP.md
│   ├── DEPLOYMENT.md
│   ├── GITHUB_SETUP.md
│   ├── GITHUB_INSTRUCTIONS.md
│   ├── PROJECT_READY.md
│   │
│   ├── .github/                      # GitHub шаблоны
│   │   ├── ISSUE_TEMPLATE/
│   │   │   ├── bug_report.md
│   │   │   └── feature_request.md
│   │   └── pull_request_template.md
│   │
│   └── agents/                       # AI агент промпты
│       └── DevOps.md
```

## Ключевые файлы

| Файл | Назначение | Строк |
|------|-----------|-------|
| `web/static/index.html` | Весь фронтенд (Vue.js 3) | ~4300 |
| `web/app/main.py` | Весь бэкенд (FastAPI) | ~1850 |
| `optimized_parser.py` | Парсер с кэшем | ~811 |
| `src/advanced_analyzer.py` | Расширенная аналитика | ~941 |
| `src/storage.py` | ORM + хранилище | ~915 |
| `config.yaml` | Конфигурация | ~1210 |

## Зависимости между модулями

```
main.py (ETL)
    ├── optimized_parser.py → src/api_client.py
    ├── src/collector.py → src/api_client.py
    ├── src/processor.py → config.yaml
    ├── src/storage.py → src/config.py
    └── src/analyzer.py → pandas

web/app/main.py
    ├── src/storage.py
    ├── optimized_parser.py
    ├── src/advanced_analyzer.py
    └── src/config.py
```

## Что НЕ коммитится в Git

```
.env                    # Секреты
data/*.db               # БД (опционально, для демо можно)
data/raw/*.json         # Сырые данные (большие файлы)
data/reports/*.xlsx     # Отчёты
logs/*.log              # Логи
__pycache__/
venv/
.pytest_cache/
```
