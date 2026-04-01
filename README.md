# 🚀 HH.ru Analytics — Система анализа вакансий

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com)
[![Vue.js](https://img.shields.io/badge/Vue.js-3.x-green.svg)](https://vuejs.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI/CD](https://github.com/LongWinterNight/HH_for_PP/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/LongWinterNight/HH_for_PP/actions/workflows/ci-cd.yml)
[![Last Commit](https://img.shields.io/github/last-commit/LongWinterNight/HH_for_PP/main)](https://github.com/LongWinterNight/HH_for_PP/commits/main)
[![Issues](https://img.shields.io/github/issues/LongWinterNight/HH_for_PP)](https://github.com/LongWinterNight/HH_for_PP/issues)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/downloads/)

**HH.ru Analytics** — профессиональная ETL-система для сбора, обработки и анализа вакансий с HH.ru с автоматическим извлечением навыков (Hard Skills, Soft Skills, Tools) и формированием аналитических отчётов.

---

## 📋 Оглавление

- [Возможности](#-возможности)
- [Требования](#-требования)
- [Установка](#-установка)
- [Запуск](#-запуск)
- [API Документация](#-api-документация)
- [Демонстрация](#-демонстрация)
- [Структура проекта](#-структура-проекта)
- [Troubleshooting](#-troubleshooting)

---

## ✨ Возможности

### 📊 Аналитика в реальном времени
- **8 KPI метрик** с трендами (Средняя ЗП, Медиана, Вакансий, Навыков, Компаний, Регионов, Hard Skills, Soft Skills)
- **Топ-20 навыков** по категориям (Hard Skills, Soft Skills, Tools)
- **Фильтры аналитики**: период, домен, регион, опыт, зарплата

### 🔍 Поиск и фильтрация
- Автодополнение вакансий, регионов и навыков
- Расширенные фильтры (опыт, зарплата, навыки)
- Пагинация результатов

### 📥 Экспорт данных
- **PDF** — отчёты с KPI и топ навыков
- **Excel** — 5 листов (KPI, Hard, Soft, Tools, Данные)
- **CSV** — сырые данные для импорта

### 🤖 Парсер вакансий
- Оптимизированный сбор данных с API HH.ru
- Кэширование запросов
- Инкрементальное обновление
- Прогресс в реальном времени

---

## 🛠 Требования

| Компонент | Версия | Обязательно |
|-----------|--------|-------------|
| Python | 3.10+ | ✅ Да |
| pip | 23.0+ | ✅ Да |
| Git | 2.30+ | ✅ Да |
| Node.js | 18+ | ❌ Нет (Vue через CDN) |

**Операционные системы:**
- ✅ Windows 10/11
- ✅ Linux (Ubuntu 20.04+, Debian 11+)
- ✅ macOS 11+

---

## 📦 Установка

### Шаг 1: Клонирование репозитория

```bash
git clone https://github.com/LongWinterNight/HH_for_PP.git
cd HH_for_PP
```

### Шаг 2: Создание виртуального окружения

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Шаг 3: Установка зависимостей

```bash
pip install -r requirements.txt
```

### Шаг 4: Настройка переменных окружения

```bash
# Скопируйте пример файла конфигурации
cp hh_analytics/.env.example hh_analytics/.env
```

**Отредактируйте `hh_analytics/.env`:**
```env
# HH.ru API токен (получить на https://dev.hh.ru/)
HH_API_TOKEN=your_token_here

# База данных
DB_PATH=data/hh_analytics.db

# Логирование
LOG_LEVEL=INFO
LOG_FILE=logs/hh_analytics.log
```

> ⚠️ **Важно:** Для работы парсера необходим API токен HH.ru. Без токена будут доступны только функции анализа загруженных данных.

---

## ▶️ Запуск

### Быстрый старт (все компоненты)

**Windows:**
```bash
cd hh_analytics
python web/app/main.py
```

**Linux/macOS:**
```bash
cd hh_analytics
python3 web/app/main.py
```

**Откройте в браузере:** http://localhost:8000

### Раздельный запуск

#### 1. Запуск парсера (сбор данных)

```bash
cd hh_analytics
python optimized_parser.py
```

#### 2. Запуск веб-приложения

```bash
cd hh_analytics
python web/app/main.py
```

---

## 📡 API Документация

После запуска сервера доступны следующие endpoints:

### Основные endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/` | GET | Главная страница |
| `/api/health` | GET | Проверка статуса сервера |
| `/api/vacancies` | GET | Список вакансий с фильтрами |
| `/api/dashboard` | GET | Данные дашборда |

### Аналитика

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/analytics/kpi` | GET | KPI метрики с трендами |
| `/api/analytics/top-skills` | GET | Топ навыков по типу |
| `/api/analytics/distribution` | GET | Распределение данных |

### Параметры фильтров для аналитики:

```
GET /api/analytics/kpi?period=month&domain=IT&regions=Москва&experience=1-3 года&salary_only=true
```

| Параметр | Значения | Описание |
|----------|----------|----------|
| `period` | today, week, month, quarter, year, all_time | Период фильтрации |
| `domain` | IT, Строительство, Продажи... | Домен профессии |
| `regions` | Москва, СПб, Казань... | Регионы через запятую |
| `experience` | Без опыта, 1-3 года, 3-6 лет, Более 6 лет | Опыт работы |
| `salary_only` | true, false | Только вакансии с зарплатой |

### Экспорт

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/export/analytics` | POST | Экспорт аналитики (PDF/Excel/CSV) |
| `/api/export/vacancies` | GET | Экспорт вакансий (CSV/Excel) |
| `/api/reports/list` | GET | Список отчётов |
| `/api/reports/download/{filename}` | GET | Скачивание отчёта |

### Парсер

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/parser/status` | GET | Статус парсера |
| `/api/parser/start` | POST | Запуск парсера |
| `/api/parser/stop` | GET | Остановка парсера |
| `/api/parser/cache/stats` | GET | Статистика кэша |
| `/api/parser/cache/clear` | POST | Очистка кэша |

### Swagger UI

Полная документация доступна по адресу: http://localhost:8000/docs

---

## 📁 Структура проекта

```
HH_for_PP/
├── hh_analytics/                 # Основной проект
│   ├── .env                      # Переменные окружения
│   ├── .env.example              # Пример конфигурации
│   ├── .gitignore                # Игнорируемые файлы
│   ├── requirements.txt          # Python зависимости
│   ├── config.yaml               # Конфигурация парсера
│   │
│   ├── src/                      # Исходный код
│   │   ├── __init__.py
│   │   ├── config.py             # Загрузка конфигурации
│   │   ├── collector.py          # Парсер HH.ru
│   │   ├── analyzer.py           # Анализ данных
│   │   ├── advanced_analyzer.py  # Расширенная аналитика
│   │   ├── storage.py            # Работа с БД
│   │   └── utils.py              # Утилиты
│   │
│   ├── web/                      # Веб-приложение
│   │   ├── app/
│   │   │   ├── main.py           # FastAPI сервер
│   │   │   └── __init__.py
│   │   └── static/
│   │       ├── index.html        # Vue.js приложение
│   │       └── favicon.ico
│   │
│   ├── data/                     # Данные
│   │   ├── hh_analytics.db       # SQLite база данных
│   │   └── professions_catalog.json
│   │
│   ├── logs/                     # Логи
│   │   └── hh_analytics.log
│   │
│   └── reports/                  # Сгенерированные отчёты
│       └── *.xlsx, *.pdf
│
├── optimized_parser.py           # Оптимизированный парсер
├── check_functionality.py        # Проверка функциональности
├── fill_all_domains.py           # Заполнение доменов
│
├── README.md                     # Эта документация
├── LICENSE                       # Лицензия
└── .gitignore                    # Git игнор
```

---

## 🔧 Troubleshooting

### Ошибка: `ModuleNotFoundError: No module named 'fastapi'`

**Решение:**
```bash
pip install -r requirements.txt
```

### Ошибка: `PermissionError: [Errno 13] Permission denied: 'data/hh_analytics.db'`

**Решение:**
```bash
# Windows: Запустить от имени администратора
# Linux/macOS:
chmod 755 data/
chmod 644 data/hh_analytics.db
```

### Ошибка: `Address already in use: port 8000`

**Решение:**
```bash
# Windows
netstat -ano | findstr :8000
taskkill /F /PID <PID>

# Linux/macOS
lsof -i :8000
kill -9 <PID>
```

### Ошибка: `HH API token is required`

**Решение:**
1. Получить токен на https://dev.hh.ru/
2. Добавить в `.env`:
   ```env
   HH_API_TOKEN=your_token_here
   ```

### Ошибка: `reportlab not found`

**Решение:**
```bash
pip install reportlab xlsxwriter
```

### Данные не отображаются

**Решение:**
1. Проверить наличие данных в БД:
   ```bash
   python check_functionality.py
   ```
2. Запустить парсер для сбора данных

---

## 📞 Контакты

**Разработчик:** Safan Ch  
**Email:** safanch2705@gmail.com  
**GitHub:** https://github.com/LongWinterNight/HH_for_PP

---

## 📄 Лицензия

MIT License — см. файл [LICENSE](LICENSE)

---

## 🙏 Благодарности

- [HH.ru API](https://dev.hh.ru/) — источник данных
- [FastAPI](https://fastapi.tiangolo.com/) — веб-фреймворк
- [Vue.js](https://vuejs.org/) — frontend фреймворк
- [Chart.js](https://www.chartjs.org/) — визуализация данных

---

**Версия:** 1.1.1
**Дата обновления:** 1 апреля 2026 г.
**Статус:** ✅ Активная разработка
