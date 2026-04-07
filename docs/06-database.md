# 🗄️ База данных (SQLite)

## Файл: `src/storage.py` (~915 строк)

## Таблицы

### 1. `vacancies` — основная таблица

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER PK | Автоинкремент |
| `vacancy_id` | VARCHAR(50) UNIQUE | ID из HH API |
| `vacancy_name` | VARCHAR(500) | Название вакансии |
| `published_at` | DATETIME | Дата публикации на HH |
| `applied_at` | DATETIME | Резервное поле |
| `all_skills` | TEXT | Все навыки (через запятую) |
| `hard_skills` | TEXT | Hard skills |
| `soft_skills` | TEXT | Soft skills |
| `tools` | TEXT | Технологии/инструменты |
| `skill_count` | INTEGER | Общее кол-во навыков |
| `hard_skill_count` | INTEGER | Кол-во hard skills |
| `soft_skill_count` | INTEGER | Кол-во soft skills |
| `tools_count` | INTEGER | Кол-во tools |
| `salary_from` | FLOAT | Зарплата от |
| `salary_to` | FLOAT | Зарплата до |
| `salary_currency` | VARCHAR(10) | Валюта (RUB, USD, EUR) |
| `salary_gross` | BOOLEAN | Gross зарплата |
| `employer_name` | VARCHAR(300) | Название компании |
| `employer_id` | VARCHAR(50) | ID компании |
| `employer_url` | VARCHAR(500) | URL компании |
| `vacancy_url` | VARCHAR(500) | URL вакансии |
| `experience` | VARCHAR(100) | Требуемый опыт |
| `employment` | VARCHAR(100) | Тип занятости |
| `schedule` | VARCHAR(100) | График работы |
| `area` | VARCHAR(200) | Регион |
| `created_at` | DATETIME | Дата создания записи |
| `updated_at` | DATETIME | Дата обновления |

**Индексы:**
```sql
idx_vacancy_id (vacancy_id)
idx_employer (employer_name)
idx_area (area)
idx_published_at (published_at)
idx_experience (experience)
idx_salary_from (salary_from)
idx_created_at (created_at)
```

### 2. `parser_runs` — журнал парсингов

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER PK | Автоинкремент |
| `started_at` | DATETIME NOT NULL | Время запуска |
| `completed_at` | DATETIME | Время завершения |
| `status` | VARCHAR(20) | running/completed/error/stopped |
| `keywords` | TEXT | JSON массив запросов |
| `max_pages` | INTEGER | Макс. страниц на запрос |
| `days_back` | INTEGER | Дней назад |
| `is_incremental` | BOOLEAN | Инкрементальный режим |
| `use_cache` | BOOLEAN | Использовать кэш |
| `vacancies_collected` | INTEGER | Всего собрано |
| `vacancies_new` | INTEGER | Новых вакансий |
| `vacancies_updated` | INTEGER | Обновлено |
| `errors_count` | INTEGER | Кол-во ошибок |
| `error_message` | TEXT | Текст ошибки |
| `created_at` | DATETIME | Дата создания записи |

### 3. `app_settings` — настройки (синглтон, id=1)

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER PK | Всегда 1 |
| `last_parse_at` | DATETIME | Последний запуск |
| `last_successful_parse_at` | DATETIME | Последний успешный |
| `total_parses` | INTEGER | Всего запусков |
| `total_vacancies_collected` | INTEGER | Всего вакансий за всё время |
| `app_version` | VARCHAR(20) | Версия приложения |
| `config_version` | VARCHAR(20) | Версия конфига |
| `updated_at` | DATETIME | Дата обновления |

## VacancyStorage — класс

### Основные методы

| Метод | Описание |
|-------|----------|
| `__init__(db_path)` | Инициализация, создание таблиц |
| `save_dataframe(df)` | Полная замена данных |
| `save_vacancies_incremental(df)` | Upsert логика |
| `get_all_vacancies()` | Получить все вакансии (DataFrame) |
| `get_vacancies_filtered(...)` | С фильтрами |
| `get_skills_statistics()` | Статистика навыков |
| `get_salary_statistics(group_by)` | Статистика зарплат |
| `get_vacancy_count()` | Общее кол-во вакансий |

### Методы для parser_runs

| Метод | Описание |
|-------|----------|
| `create_parser_run(keywords, ...)` | Создать запись запуска |
| `complete_parser_run(run_id, status, ...)` | Завершить запись |
| `get_last_parser_run(only_successful)` | Последний запуск |
| `get_parser_runs_history(limit)` | История запусков |

### Методы для app_settings

| Метод | Описание |
|-------|----------|
| `initialize_settings()` | Создать запись если нет |
| `get_app_settings()` | Получить настройки |
| `_update_settings(...)` | Внутренний метод обновления |

## Режимы сохранения

### `save_dataframe()` — полная замена
```python
df.to_sql("vacancies", engine, if_exists="replace", ...)
```
Используется при полном ETL пайплайне.

### `save_vacancies_incremental()` — upsert
```python
for _, row in df.iterrows():
    existing = session.query(VacancyModel).filter_by(vacancy_id=row["vacancy_id"]).first()
    if existing:
        # UPDATE
    else:
        # INSERT
```
Используется при инкрементальном парсинге.

## Миграция на PostgreSQL

Для продакшена заменить SQLite на PostgreSQL:

```python
# Вместо:
self.engine = create_engine(f"sqlite:///{self.db_path}")

# Использовать:
self.engine = create_engine(
    f"postgresql+psycopg2://{user}:{pass}@{host}:{port}/{dbname}"
)
```

**Важно:** SQLite не поддерживает:
- Конкурентные записи (database is locked)
- Connection pooling
- Репликацию
- Партиционирование

При >100K записей — обязательный переход на PostgreSQL.
