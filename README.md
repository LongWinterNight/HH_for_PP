# HH.ru Analytics — ETL система для анализа вакансий

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Профессиональная ETL-система для сбора, обработки и анализа вакансий с HH.ru. Система автоматически извлекает навыки (Hard Skills, Soft Skills, Tools) из описаний вакансий, формирует аналитические отчёты в Excel и сохраняет данные в SQLite базу.

---

## 📑 Оглавление

- [Возможности](#-возможности)
- [Быстрый старт](#-быстрый-старт)
- [Установка](#-установка)
- [Использование](#-использование)
- [Оптимизированный парсинг](#-оптимизированный-парсинг)
- [Веб-интерфейс](#-веб-интерфейс)
- [CLI интерфейс](#-cli-интерфейс)
- [Архитектура](#-архитектура)
- [Конфигурация](#-конфигурация)
- [Структура проекта](#-структура-проекта)
- [Аналитика и отчёты](#-аналитика-и-отчёты)
- [Устранение неполадок](#-устранение-неполадок)
- [FAQ](#-faq)

---

## ✨ Возможности

### Сбор данных (Extract)
- ✅ Поиск вакансий через официальное API HH.ru
- ✅ Поддержка множественных поисковых запросов
- ✅ Автоматическая пагинация (до 400 страниц)
- ✅ Фильтрация по дате публикации
- ✅ Удаление дубликатов вакансий
- ✅ Rate limiting (1 запрос/сек)
- ✅ **Инкрементальный режим (только новые вакансии)**
- ✅ **Кэширование API ответов**

### Обработка данных (Transform)
- ✅ Извлечение навыков из описаний вакансий
- ✅ Классификация: Hard Skills, Soft Skills, Tools
- ✅ Лемматизация текста (pymorphy3)
- ✅ Извлечение зарплаты и работодателя
- ✅ Нормализация данных
- ✅ **Векторизованный поиск навыков**

### Загрузка и хранение (Load)
- ✅ Сохранение в JSON (сырые данные)
- ✅ Сохранение в CSV и Parquet (обработанные)
- ✅ SQLite база данных
- ✅ Upsert логика (без дубликатов)

### Аналитика и отчёты (Analyze)
- ✅ Консольная сводка по навыкам
- ✅ Excel-отчёты с графиками
- ✅ Статистика зарплат
- ✅ Распределение по регионам и опыту
- ✅ Расширенная аналитика с группировками
- ✅ Детализация "вакансия-навык"
- ✅ **Веб-интерфейс для управления системой**

---

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
cd F:\AI_projects\hh_analytics
pip install -r requirements.txt
```

### 2. Настройка окружения

Создайте `.env` в корне проекта:

```bash
HH_USER_EMAIL=ваш_email@example.com
API_REQUEST_DELAY=1.0
MAX_PAGES=10
DAYS_BACK=30
```

### 3. Тестовый запуск

```bash
# Быстрый тест (2 страницы, 7 дней)
python optimized_parser.py --max-pages 2 --days-back 7

# Полный пайплайн
python main.py
```

### 4. Запуск веб-интерфейса

```bash
python web/run.py
```

Откройте: http://localhost:8000/static/index.html

---

## ⚙️ Установка

### Шаг 1: Перейти в директорию проекта

```bash
cd F:\AI_projects\hh_analytics
```

### Шаг 2: Создать виртуальное окружение

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source tenv/bin/activate
```

### Шаг 3: Установить зависимости

```bash
pip install -r requirements.txt
```

### Шаг 4: Настроить переменные окружения (.env)

```bash
# HH.ru API Configuration
HH_USER_EMAIL=ваш_email@example.com

# Rate Limiting
API_REQUEST_DELAY=1.0

# Лимиты сбора
MAX_PAGES=10
DAYS_BACK=30
```

> ⚠️ **Важно:** Укажите реальный email в `HH_USER_EMAIL` для соблюдения правил API HH.ru.

---

## 📖 Использование

### Режимы работы main.py

| Команда | Описание |
|---------|----------|
| `python main.py` | Полный пайплайн (4 этапа) |
| `python main.py --collect` | Только сбор вакансий |
| `python main.py --process` | Только обработка |
| `python main.py --load` | Только загрузка в БД |
| `python main.py --analyze` | Только анализ и отчёты |
| `python main.py --collect --analyze` | Сбор и анализ |

### Параметры командной строки

```bash
python main.py [OPTIONS]

Режимы:
  --collect           Только сбор (Extract)
  --process           Только обработка (Transform)
  --load              Только загрузка (Load)
  --analyze           Только анализ (Analyze)

Параметры сбора:
  --keywords KEYWORDS ...   Поисковые запросы
  --max-pages N             Макс. страниц
  --days-back N             За сколько дней собирать
```

### Примеры

```bash
# Быстрый сбор по запросам
python main.py --collect --keywords "Python" "Backend" --max-pages 3

# Сбор и анализ за неделю
python main.py --collect --analyze --days-back 7 --max-pages 5

# Полный пайплайн с параметрами
python main.py --keywords "ML" "DL" "NLP" --max-pages 10 --days-back 30
```

---

## ⚡ Оптимизированный парсинг

### 🎯 Сравнение версий

| Параметр | Оригинальный | Оптимизированный |
|----------|--------------|------------------|
| Время сбора | 50-100 мин | **5-15 мин** |
| Кэширование | ❌ | ✅ |
| Инкрементальный режим | ❌ | ✅ |
| Прогресс-бар | ❌ | ✅ |
| Детали вакансий | Все страницы | Только 2 первые |

### 🚀 Команды оптимизированного парсера

#### Инкрементальный режим (рекомендуется)
```bash
python optimized_parser.py --incremental
```
- ✅ Собирает только новые вакансии
- ✅ Пропускает уже существующие в базе
- ⏱️ **Время: 5-15 минут**

#### Быстрый сбор (тестирование)
```bash
python optimized_parser.py --max-pages 3 --days-back 7
```
- ✅ 3 страницы на запрос
- ✅ За последние 7 дней
- ⏱️ **Время: 15 минут**

#### По конкретным навыкам
```bash
python optimized_parser.py --keywords "Python" "LLM" "Data Scientist" --max-pages 5
```
- ✅ Фокус на конкретных технологиях
- ⏱️ **Время: 5 минут**

#### Статистика кэша
```bash
python optimized_parser.py --cache-stats
```

#### Очистка кэша
```bash
python optimized_parser.py --clear-cache
```

### 📊 Рекомендации по использованию

| Задача | Команда | Время |
|--------|---------|-------|
| Ежедневное обновление | `--incremental --days-back 1 --max-pages 5` | ~3-5 мин |
| Еженедельное обновление | `--incremental --days-back 7` | ~10-15 мин |
| Полный сбор | `--max-pages 10 --days-back 30` | ~50-100 мин |
| Тестирование | `--keywords "Python" --max-pages 2` | ~1-2 мин |

---

## 🌐 Веб-интерфейс

### Быстрый запуск

```bash
# Запуск веб-приложения
python web/run.py

# Или через uvicorn
uvicorn web.app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Откройте в браузере:** http://localhost:8000/static/index.html

**API документация:** http://localhost:8000/docs

### Возможности веб-интерфейса

| Раздел | Описание |
|--------|----------|
| **Дашборд** | Сводная статистика, топ навыков, недавние вакансии |
| **Вакансии** | Поиск, фильтрация, пагинация, экспорт |
| **Аналитика** | Группировки технологий, Hard/Soft Skills, графики |
| **Парсер** | Запуск/остановка сбора, мониторинг прогресса |
| **Отчёты** | Список, скачивание, генерация новых отчётов |

### API Endpoints

#### Вакансии
- `GET /api/vacancies` — список с фильтрами
- `GET /api/dashboard` — данные для дашборда

#### Аналитика
- `GET /api/analytics/summary` — сводка
- `GET /api/analytics/advanced` — расширенная
- `GET /api/analytics/distribution` — распределение

#### Парсер
- `GET /api/parser/status` — статус
- `POST /api/parser/start` — запуск
- `POST /api/parser/stop` — остановка
- `GET /api/parser/cache/stats` — статистика кэша
- `POST /api/parser/cache/clear` — очистка кэша

#### Отчёты
- `GET /api/reports/list` — список
- `GET /api/reports/download/{filename}` — скачивание
- `POST /api/reports/generate` — генерация
- `GET /api/export/vacancies` — экспорт

### Примеры API запросов

```bash
# Получить вакансии с фильтром
curl "http://localhost:8000/api/vacancies?area=Москва&skill=Python&page=1&per_page=20"

# Запустить парсер (инкрементальный режим)
curl -X POST "http://localhost:8000/api/parser/start?incremental=true"

# Получить аналитику
curl "http://localhost:8000/api/analytics/advanced"

# Статистика кэша
curl "http://localhost:8000/api/parser/cache/stats"
```

---

## 🖥 CLI интерфейс

### Запуск

```bash
# Интерактивный режим
python -m src.db_cli

# Однострочные команды
python -m src.db_cli --stats
python -m src.db_cli --skill LLM --limit 10
python -m src.db_cli --list --area Москва
python -m src.db_cli --advanced
python -m src.db_cli --export my_data.xlsx
```

### Команды интерактивного режима

| Команда | Описание |
|---------|----------|
| `list [limit]` | Список вакансий (по умолчанию 20) |
| `search <skill> [limit]` | Поиск по навыку |
| `stats` | Статистика по базе |
| `advanced` | Расширенная аналитика |
| `export [path]` | Экспорт в Excel |
| `filter --area <region>` | Фильтр по региону |
| `filter --exp <experience>` | Фильтр по опыту |
| `help` | Справка |
| `quit` / `exit` | Выход |

---

## 🏗 Архитектура

Система построена по принципу **ETL (Extract-Transform-Load)**:

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐
│   Extract   │────▶│  Transform   │────▶│    Load     │────▶│   Analyze   │
│  (Сбор)     │     │ (Обработка)  │     │ (Загрузка)  │     │  (Анализ)   │
└─────────────┘     └──────────────┘     └─────────────┘     └─────────────┘
       │                    │                    │                    │
       ▼                    ▼                    ▼                    ▼
  HH.ru API           Навыки извлечены      SQLite БД            Excel-отчёт
  JSON файлы          CSV/Parquet          Хранилище            Консольная
                                                                  сводка
```

### Компоненты системы

| Модуль | Описание |
|--------|----------|
| `api_client.py` | Клиент для работы с HH.ru API |
| `collector.py` | Сборщик вакансий (Extract) |
| `processor.py` | Процессор для обработки (Transform) |
| `storage.py` | Хранилище SQLite (Load) |
| `analyzer.py` | Анализатор и генератор отчётов (Analyze) |
| `advanced_analyzer.py` | Расширенная аналитика с группировками |
| `db_cli.py` | CLI интерфейс для работы с БД |
| `config.py` | Конфигурация и настройки |
| `utils.py` | Вспомогательные утилиты |
| `optimized_parser.py` | Оптимизированный парсер с кэшем |

---

## ⚙️ Конфигурация

### Переменные окружения (.env)

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `HH_USER_EMAIL` | Email для User-Agent | `""` |
| `API_REQUEST_DELAY` | Задержка между запросами (сек) | `1.0` |
| `MAX_PAGES` | Макс. страниц для сбора | `10` |
| `DAYS_BACK` | За сколько дней собирать | `30` |
| `DATA_DIR` | Основная директория | `data` |
| `RAW_DATA_DIR` | Сырые данные | `data/raw` |
| `PROCESSED_DATA_DIR` | Обработанные данные | `data/processed` |
| `REPORTS_DIR` | Отчёты | `data/reports` |
| `DB_PATH` | SQLite база данных | `data/hh_vacancies.db` |
| `LOG_LEVEL` | Уровень логов | `INFO` |

### Параметры config.yaml

#### Поисковые запросы
```yaml
search_queries:
  - "Python developer"
  - "Data Scientist"
  - "Machine Learning engineer"

hard_skills:
  - "python"
  - "java"
  - "sql"
  - "pytorch"
  - "tensorflow"

soft_skills:
  - "communication"
  - "teamwork"
  - "leadership"

tools:
  - "docker"
  - "git"
  - "jupyter"
```

#### Обработка
```yaml
processing:
  min_skill_length: 2
  max_skills_per_vacancy: 50
  confidence_threshold: 0.7
  use_fuzzy_search: true
  find_synonyms: true
```

#### Отчётность
```yaml
reporting:
  top_n_skills: 50
  min_skill_frequency: 1
  export_formats:
    - xlsx
    - csv
  group_by_category: true
  show_trends: true
```

---

## 📁 Структура проекта

```
hh_analytics/
├── main.py                 # Точка входа (ETL пайплайн)
├── optimized_parser.py     # Оптимизированный парсер
├── requirements.txt        # Зависимости Python
├── config.yaml            # Конфигурация (словари навыков)
├── .env                   # Переменные окружения
├── .gitignore            # Git ignore
├── README.md             # Документация
│
├── src/                  # Исходный код
│   ├── __init__.py
│   ├── api_client.py     # HH.ru API клиент
│   ├── collector.py      # Сбор вакансий (Extract)
│   ├── processor.py      # Обработка (Transform)
│   ├── storage.py        # SQLite хранилище (Load)
│   ├── analyzer.py       # Анализ и отчёты (Analyze)
│   ├── advanced_analyzer.py  # Расширенная аналитика
│   ├── db_cli.py         # CLI интерфейс для БД
│   ├── config.py         # Конфигурация
│   └── utils.py          # Утилиты
│
├── web/                  # Веб-приложение
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py       # FastAPI бэкенд
│   ├── static/
│   │   └── index.html    # Веб-интерфейс (Vue.js 3)
│   └── run.py            # Скрипт запуска
│
├── data/                 # Данные
│   ├── raw/             # Сырые JSON
│   ├── processed/       # CSV и Parquet
│   ├── reports/         # Excel и CSV отчёты
│   └── hh_vacancies.db  # SQLite база
│
└── logs/                # Логи
    └── hh_analytics.log
```

---

## 🔄 ETL Пайплайн

### Этап 1: Extract (Сбор)

**Процесс:**
1. Подключение к HH.ru API
2. Поиск по ключевым словам
3. Пагинация результатов
4. Фильтрация по дате
5. Удаление дубликатов
6. Сохранение в JSON

**Выход:**
- `data/raw/vacancies_<query>_<timestamp>.json`
- `data/raw/all_vacancies_<timestamp>.json`

```bash
python main.py --collect --max-pages 5
```

### Этап 2: Transform (Обработка)

**Процесс:**
1. Загрузка JSON
2. Извлечение навыков
3. Классификация по категориям
4. Лемматизация
5. Извлечение зарплаты
6. Сохранение в CSV/Parquet

**Выход:**
- `data/processed/vacancies_processed.csv`
- `data/processed/vacancies_processed.parquet`

```bash
python main.py --process
```

### Этап 3: Load (Загрузка)

**Процесс:**
1. Чтение CSV
2. Создание таблицы SQLite
3. Массовая вставка
4. Индексация

**Выход:**
- `data/hh_vacancies.db`

```bash
python main.py --load
```

### Этап 4: Analyze (Анализ)

**Процесс:**
1. Подсчёт частоты навыков
2. Статистика зарплат
3. Распределение по опыту/регионам
4. Генерация Excel-отчёта
5. Консольная сводка
6. Расширенная аналитика с группировками

**Выход:**
- `data/reports/hh_analytics_report_<timestamp>.xlsx`
- `data/reports/hh_advanced_analytics_<timestamp>.xlsx`
- `data/reports/hh_skills_stats_<timestamp>.csv`

```bash
python main.py --analyze
```

---

## 📊 Аналитика и отчёты

### Стандартный отчёт (hh_analytics_report_*.xlsx)

| Лист | Описание |
|------|----------|
| **Summary** | Сводная статистика |
| **Hard Skills** | Топ профессиональных навыков |
| **Soft Skills** | Топ гибких навыков |
| **Tools** | Топ инструментов |
| **Salaries** | Анализ зарплат |
| **Experience** | Распределение по опыту |
| **Areas** | Распределение по регионам |

### Детальный отчёт (hh_advanced_analytics_*.xlsx)

| Лист | Описание |
|------|----------|
| **Summary** | Сводка по всем категориям |
| **Technology Groups** | 20+ групп технологий |
| **Hard Skills Groups** | 12+ групп hard skills |
| **Soft Skills Groups** | 8+ групп soft skills |
| **Vacancy-Skill Map** | Карта связей вакансия-навык |
| **Advanced Categories** | Расширенные категории |

### Консольная сводка

```
============================================================
📊 HH.ru Analytics — Сводка
============================================================

📈 Всего вакансий: 500
📋 Среднее навыков на вакансию: 12.45

🛠 Топ-10 Hard Skills:
   1. python: 245
   2. sql: 198
   3. django: 156

🔧 Топ-10 Tools:
   1. docker: 187
   2. git: 165
   3. linux: 134

💰 Зарплаты (RUB):
   Средняя: 150 000
   Медиана: 130 000

============================================================
```

---

## 🛠 Устранение неполадок

### Parquet: `Unable to find a usable engine`

**Решение:**
```bash
pip install pyarrow>=14.0.0
```

### Ошибка конфигурации

**Решение:** Проверьте `config.yaml` и `.env`.

### `HH_USER_EMAIL not set`

**Решение:** Добавьте в `.env`:
```
HH_USER_EMAIL=ваш_email@example.com
```

### `ModuleNotFoundError: No module named 'src'`

**Решение:** Запускайте через `python -m`:
```bash
python -m src.collector
```

### Rate Limit API

**Решение:**
1. Увеличьте `API_REQUEST_DELAY` в `.env`
2. Уменьшите `MAX_PAGES`
3. Делайте перерывы

### Медленный сбор

**Решение:**
1. Используйте `optimized_parser.py`
2. Включите инкрементальный режим
3. Уменьшите `MAX_PAGES` (до 5)
4. Уменьшите `DAYS_BACK` (до 7)

### Пустой DataFrame

**Решение:** Сначала запустите сбор:
```bash
python main.py --collect
```

---

## ❓ FAQ

### Q: Сколько вакансий можно собрать?

**A:**
- `MAX_PAGES=10` → ~1000 на запрос
- При 10 запросах → ~10 000
- Время: ~3-5 мин на 1000 (оптимизированный)

### Q: Как часто запускать сбор?

**A:**
- Не чаще 1 раза в час
- Задержка 1-2 сек между запросами

### Q: Можно ли PostgreSQL вместо SQLite?

**A:** Да, измените в `storage.py`:
```python
self.engine = create_engine(
    "postgresql://user:password@localhost/dbname"
)
```

### Q: Как добавить новые навыки?

**A:** В `config.yaml`:
```yaml
hard_skills:
  - "новый навык"
```

### Q: Где логи?

**A:** `logs/hh_analytics.log` и консоль.

### Q: Как экспортировать в Excel?

**A:** Автоматически при `--analyze`:
```bash
python main.py --analyze
```

### Q: Как остановить сбор досрочно?

**A:** Нажмите `Ctrl+C`. Данные сохранятся.

### Q: Слетит ли база при запуске парсера?

**A:** **НЕТ!** Существующие вакансии не удаляются, новые добавляются, дубликаты автоматически отфильтровываются.

---

## 📝 Лицензия

MIT License.

## 👥 Контакты

По вопросам: [ваш email]

## 🙏 Благодарности

- [HH.ru API](https://github.com/hhru/api)
- [pymorphy3](https://pymorphy3.readthedocs.io/)
- [pandas](https://pandas.pydata.org/)

---

**Удачи в анализе рынка труда! 🚀**
