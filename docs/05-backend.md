# ⚙️ Backend (FastAPI)

## Файл: `web/app/main.py` (~1850 строк)

## Инициализация приложения

```python
app = FastAPI(title="HH.ru Analytics", version="2.0.0")

# CORS (для dev — все origins)
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

# Статика
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# In-memory состояние
user_settings = {"hh_user_email": None}
parser_state = {"is_running": False, "status": "idle", ...}
```

## Глобальные переменные

| Переменная | Тип | Назначение |
|-----------|-----|-----------|
| `parser_state` | dict | Состояние парсера (in-memory) |
| `user_settings` | dict | Настройки пользователя (email) |

## Все endpoints

### Страницы

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/` | Главная страница (index.html) |
| GET | `/analytics` | Страница аналитики |
| GET | `/favicon.ico` | Favicon заглушка |

### Общие

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/health` | `{"status": "ok"}` |

### Дашборд

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/dashboard` | KPI, навыки, вакансии, sparklines, last_updated |
| GET | `/api/vacancies` | Список вакансий с фильтрами |

**Параметры `/api/vacancies`:**
```
page, per_page, search, area, experience, skill,
salary_only, sort_by (salary|date|none), sort_order (asc|desc)
```

### Аналитика

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/analytics/kpi` | 8 KPI метрик с трендами |
| GET | `/api/analytics/top-skills` | Топ навыков (type=hard|soft|tools) |
| GET | `/api/analytics/distribution` | Распределение (опыт, занятость, зарплаты) |
| GET | `/api/analytics/advanced` | Технологии, hard/soft skills |

### Парсер

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/parser/status` | Текущий статус |
| POST | `/api/parser/start` | Запуск (требует email! 403 без него) |
| GET | `/api/parser/stop` | Остановка |
| GET | `/api/parser/last-run` | Последний запуск |
| GET | `/api/parser/history` | История запусков (limit=20) |
| GET | `/api/parser/cache/stats` | Статистика кэша |
| POST | `/api/parser/cache/clear` | Очистка кэша (days=7) |

### Пользователь

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/user/email` | Статус email |
| POST | `/api/user/email` | Сохранить email (валидация + обновление .env) |
| GET | `/api/app/settings` | Настройки приложения |

### Профессии

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/professions/list` | Список профессий |
| GET | `/api/professions/search` | Поиск |

### Автодополнение

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/autocomplete/vacancies` | Вакансии (q=...) |
| GET | `/api/autocomplete/areas` | Регионы (q=...) |
| GET | `/api/autocomplete/skills` | Навыки (q=...) |

### Экспорт и отчёты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/reports/list` | Список отчётов |
| GET | `/api/reports/download/{filename}` | Скачивание |
| POST | `/api/reports/generate` | Генерация |
| GET | `/api/export/vacancies` | Экспорт вакансий (format=xlsx|csv) |
| POST | `/api/export/analytics` | Экспорт аналитики |

## Защита парсера

```python
@app.post("/api/parser/start")
def start_parser(...):
    user_email = user_settings.get("hh_user_email")
    if not user_email:
        raise HTTPException(403, "Настройте email через ⚙️")
    # ... запуск парсера
```

## Фоновые задачи

```python
@app.post("/api/parser/start")
def start_parser(background_tasks: BackgroundTasks, ...):
    # ...
    background_tasks.add_task(run)  # Парсер в фоне
    return {"message": "Парсер запущен"}
```

## Запуск сервера

```bash
# web/run.py
uvicorn web.app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Логирование

```python
from src.utils import get_logger
logger = get_logger(__name__)

# Логи:
logger.info(f"🔑 Парсер запущен с email: {user_email}")
logger.info(f"📡 Запросы к HH API будут отправляться от: {email}")
```

## Зависимости

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.6
aiofiles>=23.2.1
pandas>=2.0.0
sqlalchemy>=2.0.0
openpyxl>=3.1.0
reportlab>=4.0.0
```
