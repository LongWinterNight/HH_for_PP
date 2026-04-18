# HH.ru Analytics — Система анализа вакансий

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com)
[![Vue.js](https://img.shields.io/badge/Vue.js-3.x-green.svg)](https://vuejs.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI/CD](https://github.com/LongWinterNight/HH_for_PP/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/LongWinterNight/HH_for_PP/actions/workflows/ci-cd.yml)
[![Last Commit](https://img.shields.io/github/last-commit/LongWinterNight/HH_for_PP/main)](https://github.com/LongWinterNight/HH_for_PP/commits/main)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/downloads/)

**HH.ru Analytics** — self-hosted ETL-система для сбора, обработки и анализа вакансий с HH.ru.  
Автоматически извлекает Hard Skills, Soft Skills и Tools из описаний вакансий, строит аналитику и формирует отчёты в PDF/Excel/CSV.

---

## Возможности

### Аналитика
- **8 KPI метрик** — средняя и медианная зарплата, количество вакансий, навыков, компаний, регионов, Hard/Soft Skills
- **Топ-20 навыков** по трём категориям: Hard Skills, Soft Skills, Tools
- **Фильтры**: период, регион, опыт работы, только с зарплатой
- **Sparkline-тренды** на KPI карточках
- **Распределение** по зарплате, опыту, регионам и валютам

### Парсер
- Сбор по ключевым словам через публичный API HH.ru (без OAuth, анонимно)
- Поддержка 59 профессий из коробки — от IT до строительства и юриспруденции
- Инкрементальное обновление — не дублирует уже собранные вакансии
- Кэширование запросов
- Прогресс в реальном времени

### Экспорт
- **PDF** — отчёт с KPI и топ навыков
- **Excel** — 5 листов (KPI, Hard Skills, Soft Skills, Tools, Данные)
- **CSV** — сырые данные

### Поиск
- Автодополнение по названию вакансии, региону, навыку
- Расширенные фильтры, сортировка, пагинация

---

## Требования

| Компонент | Версия | Обязательно |
|-----------|--------|-------------|
| Python | 3.10+ | Да |
| pip | 23.0+ | Да |
| Git | 2.30+ | Да |
| Node.js | — | Нет (Vue через CDN) |

**ОС:** Windows 10/11, Linux (Ubuntu 20.04+), macOS 11+

---

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone https://github.com/LongWinterNight/HH_for_PP.git
cd HH_for_PP
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

### 3. Создать файл окружения

```bash
# Windows
copy .env.example .env

# Linux/macOS
cp .env.example .env
```

Отредактировать `.env` — указать email от аккаунта на HH.ru:

```env
HH_USER_EMAIL=your_email@example.com
```

> Это стандартное требование API HH.ru — email идентифицирует запросы.  
> OAuth-токен не нужен. Данные хранятся только локально.

### 4. Запустить

```bash
python web/app/main.py
```

Открыть в браузере: **http://localhost:8000**

При первом запуске можно указать email прямо в интерфейсе — он сохранится в `.env` автоматически.

---

## Структура проекта

```
HH_for_PP/
├── src/
│   ├── api_client.py       # HTTP-клиент HH.ru API (rate limiting, retry)
│   ├── collector.py        # Сборщик вакансий (пагинация, дедупликация)
│   ├── analyzer.py         # Excel-отчёты
│   ├── advanced_analyzer.py# Расширенная аналитика по навыкам
│   ├── storage.py          # SQLite хранилище
│   ├── config.py           # Загрузка .env и config.yaml
│   └── utils.py            # Логгер и утилиты
│
├── web/
│   ├── app/main.py         # FastAPI сервер (20+ эндпоинтов)
│   └── static/
│       ├── index.html      # Vue.js 3 SPA (~4300 строк)
│       └── analytics.html  # Страница аналитики
│
├── data/
│   ├── hh_vacancies.db     # SQLite база данных
│   ├── professions_catalog.json
│   ├── raw/                # Сырые JSON от парсера
│   └── reports/            # Сгенерированные отчёты
│
├── tests/                  # Unit-тесты (35 тестов)
├── optimized_parser.py     # Оптимизированный парсер с кэшем
├── config.yaml             # Ключевые слова и словари навыков
├── .env.example            # Пример конфигурации
├── docker-compose.yml      # Docker для продакшена
└── Dockerfile
```

---

## API

После запуска доступна Swagger-документация: **http://localhost:8000/docs**

### Основные эндпоинты

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/health` | Статус сервера |
| GET | `/api/dashboard` | Дашборд с KPI и последними вакансиями |
| GET | `/api/vacancies` | Вакансии с фильтрами и пагинацией |
| GET | `/api/analytics/kpi` | 8 KPI метрик с трендами |
| GET | `/api/analytics/top-skills` | Топ навыков (hard/soft/tools) |
| GET | `/api/analytics/distribution` | Распределение по зарплате, опыту, регионам |
| GET | `/api/analytics/advanced` | Расширенная аналитика |
| POST | `/api/parser/start` | Запуск парсера |
| GET | `/api/parser/status` | Статус и прогресс парсера |
| GET | `/api/parser/stop` | Остановка парсера |
| POST | `/api/export/analytics` | Экспорт отчёта (pdf/xlsx/csv) |
| GET | `/api/export/vacancies` | Экспорт вакансий (csv/xlsx) |
| GET | `/api/professions/list` | Каталог профессий |
| GET | `/api/autocomplete/skills` | Автодополнение навыков |

### Параметры фильтров аналитики

```
GET /api/analytics/kpi?period=month&regions=Москва&experience=1-3 года&salary_only=true
```

| Параметр | Значения |
|----------|----------|
| `period` | today, week, month, quarter, year, all_time |
| `regions` | Москва, Санкт-Петербург, Казань, ... |
| `experience` | Без опыта, 1-3 года, 3-6 лет, Более 6 лет |
| `salary_only` | true / false |

---

## Docker (продакшен)

```bash
docker compose up -d
```

Приложение поднимается на http://localhost:8000. Конфигурация в `.env.production.example`.

---

## Troubleshooting

### `ModuleNotFoundError`
```bash
pip install -r requirements.txt
```

### Порт 8000 занят
```bash
# Windows
netstat -ano | findstr :8000
taskkill /F /PID <PID>

# Linux/macOS
lsof -i :8000 | kill -9 <PID>
```

### Парсер возвращает 403
HH.ru использует DDoS Guard. Возможные причины:
- Слишком много запросов за короткое время — подождите 1–2 часа
- Запросы идут через общий прокси/VPN с заблокированным IP — отключите прокси для запросов к api.hh.ru

### Данные не отображаются
Запустите парсер через интерфейс или проверьте БД:
```bash
python check_functionality.py
```

---

## Контакты

**Разработчик:** Safan Ch  
**Email:** safanch2705@gmail.com  
**GitHub:** https://github.com/LongWinterNight/HH_for_PP

---

## Лицензия

MIT License — см. файл [LICENSE](LICENSE)

---

**Версия:** 1.2.0 | **Статус:** Активная разработка
