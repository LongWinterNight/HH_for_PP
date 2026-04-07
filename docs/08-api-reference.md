# 🔌 API Reference

## Базовый URL

```
http://localhost:8000/api
```

## Аутентификация

Не требуется для чтения. Для запуска парсера необходим настроенный email (`POST /api/user/email`).

---

## Endpoints

### GET /api/health

**Ответ:**
```json
{"status": "ok"}
```

---

### GET /api/dashboard

**Описание:** Данные для главной страницы дашборда.

**Ответ:**
```json
{
  "total_vacancies": 305,
  "total_skills": 1250,
  "avg_salary": 150000,
  "recent_vacancies": [
    {
      "name": "Python Developer",
      "company": "Яндекс",
      "area": "Москва",
      "salary": 180000,
      "currency": "RUB"
    }
  ],
  "top_skills": [
    {"name": "Python", "value": 120},
    {"name": "FastAPI", "value": 45}
  ],
  "vacancies_by_currency": {
    "RUB": {"count": 280, "avg_salary": 145000}
  },
  "vacancies_by_area": {"Москва": 150, "Санкт-Петербург": 80},
  "salary_trend": [
    {"date": "2026-03-01", "avg_salary": 142000}
  ],
  "sparklines": {
    "vacancies": [5, 8, 12, 15, 10, 7, 20, 25, 18, 14, 11, 9, 6, 3],
    "skills": [50, 60, 80, 95, 70, 55, 120, 150, 110, 85, 65, 50, 40, 20],
    "salaries": [140000, 142000, 145000, 148000, 150000, 152000, 155000, 158000, 160000, 162000, 165000, 168000, 170000, 172000]
  },
  "last_updated": "2026-04-07T14:30:00"
}
```

---

### GET /api/vacancies

**Параметры:**
| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `page` | int | 1 | Страница |
| `per_page` | int | 20 | Записей на страницу |
| `search` | string | "" | Поиск по названию |
| `area` | string | "" | Фильтр по региону |
| `experience` | string | "" | Фильтр по опыту |
| `skill` | string | "" | Поиск по навыкам |
| `salary_only` | bool | false | Только с зарплатой |
| `sort_by` | string | "salary" | salary|date|none |
| `sort_order` | string | "desc" | asc|desc |

**Ответ:**
```json
{
  "total": 305,
  "page": 1,
  "items": [...]
}
```

---

### POST /api/parser/start

**Параметры:**
| Параметр | Тип | По умолчанию | Описание |
|----------|-----|-------------|----------|
| `keywords` | string[] | Из конфига | Ключевые слова |
| `max_pages` | int | 10 | Макс. страниц |
| `days_back` | int | 30 | Дней назад |
| `incremental` | bool | false | Инкрементальный режим |
| `use_cache` | bool | true | Использовать кэш |

**Ошибка 403 (email не настроен):**
```json
{"detail": "Для запуска парсера необходимо настроить email. Укажите ваш email от HH.ru в настройках (иконка ⚙️ в навигации)."}
```

**Ответ 200:**
```json
{"message": "Парсер запущен", "state": {...}}
```

---

### GET /api/user/email

**Ответ:**
```json
{"email": "user@example.com", "is_configured": true}
```

### POST /api/user/email

**Тело запроса:**
```json
{"email": "user@example.com"}
```

**Ответ 200:**
```json
{"message": "Email сохранён", "email": "user@example.com", "env_updated": true}
```

**Ошибка 400:**
```json
{"detail": "Неверный формат email"}
```

---

### GET /api/parser/last-run

**Ответ:**
```json
{
  "last_run": {
    "id": 5,
    "started_at": "2026-04-07T10:00:00",
    "completed_at": "2026-04-07T10:05:30",
    "status": "completed",
    "keywords": ["Python Developer", "Data Scientist"],
    "max_pages": 10,
    "days_back": 30,
    "is_incremental": true,
    "use_cache": true,
    "vacancies_collected": 305,
    "vacancies_new": 120,
    "vacancies_updated": 185,
    "errors_count": 0
  }
}
```

---

### GET /api/analytics/kpi

**Параметры:**
| Параметр | Тип | Описание |
|----------|-----|----------|
| `period` | string | all_time|today|week|month|quarter|year |
| `domain` | string | Фильтр по домену |
| `regions` | string | Фильтр по регионам |
| `experience` | string | Фильтр по опыту |
| `salary_only` | bool | Только с зарплатой |

**Ответ:**
```json
{
  "metrics": {
    "avg_salary": {"value": 150000, "trend_percent": 5.2, "trend_direction": "up"},
    "median_salary": {"value": 135000, "trend_percent": 3.1, "trend_direction": "up"},
    "total_vacancies": {"value": 305, "trend_percent": 12.5, "trend_direction": "up"},
    "total_skills": {"value": 1250, "trend_percent": 8.3, "trend_direction": "up"},
    "unique_companies": {"value": 89, "trend_percent": -2.1, "trend_direction": "down"},
    "unique_regions": {"value": 45, "trend_percent": 0, "trend_direction": "same"},
    "hard_skills_count": {"value": 320, "trend_percent": 15.2, "trend_direction": "up"},
    "soft_skills_count": {"value": 180, "trend_percent": 5.0, "trend_direction": "up"}
  }
}
```

---

### GET /api/export/vacancies

**Параметры:**
| Параметр | Тип | По умолчанию |
|----------|-----|-------------|
| `format` | string | csv (xlsx|csv) |

**Ответ:** Файл для скачивания.

---

## Коды ошибок

| Код | Описание |
|-----|----------|
| 200 | Успех |
| 400 | Неверный запрос (неверный email) |
| 403 | Нет доступа (email не настроен) |
| 404 | Не найдено |
| 500 | Ошибка сервера |
