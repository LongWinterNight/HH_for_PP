# HH.ru Analytics

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Система для сбора и анализа вакансий с HH.ru. Парсит вакансии через публичный API, извлекает Hard Skills, Soft Skills и Tools, строит аналитику и формирует отчёты.

---

## Возможности

- Сбор вакансий по ключевым словам (59 профессий из коробки)
- 8 KPI метрик: зарплаты, количество вакансий, навыков, компаний, регионов
- Топ-20 навыков по трём категориям: Hard Skills, Soft Skills, Tools
- Фильтры: период, регион, опыт, только с зарплатой
- Экспорт в PDF, Excel, CSV
- Поиск с автодополнением и фильтрами

---

## Требования

| | |
|---|---|
| Python | 3.10 или новее |
| Git | любая версия |
| ОС | Windows 10/11, Linux, macOS |
| Аккаунт | HH.ru (нужен email) |

---

## Установка

### 1. Клонировать репозиторий

```bash
git clone https://github.com/LongWinterNight/HH_for_PP.git
cd HH_for_PP
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

> Если `pip` не найден — используй `pip3` или `python -m pip install -r requirements.txt`

### 3. Создать файл конфигурации

**Windows:**
```cmd
copy .env.example .env
```

**Linux / macOS:**
```bash
cp .env.example .env
```

### 4. Указать email

Открой файл `.env` в текстовом редакторе и замени значение:

```env
HH_USER_EMAIL=твой_email@example.com
```

Это стандартное требование API HH.ru — email идентифицирует запросы. OAuth-токен не нужен. Данные хранятся только локально на твоём компьютере.

> Можно пропустить этот шаг — email можно ввести прямо в интерфейсе при первом запуске.

### 5. Запустить

```bash
python web/app/main.py
```

Открой в браузере: **http://localhost:8000**

---

## Первый запуск

1. Если email не был указан в `.env` — появится окно для его ввода. Введи email от аккаунта HH.ru.
2. Перейди во вкладку **Парсер**.
3. Выбери профессию из каталога или введи ключевое слово вручную.
4. Нажми **Запустить** и дождись завершения (прогресс отображается в реальном времени).
5. Перейди в **Аналитику** — данные появятся автоматически.

---

## Структура проекта

```
HH_for_PP/
├── src/
│   ├── api_client.py        # HTTP-клиент HH.ru API
│   ├── collector.py         # Сборщик вакансий
│   ├── storage.py           # SQLite база данных
│   ├── analyzer.py          # Excel-отчёты
│   ├── advanced_analyzer.py # Расширенная аналитика
│   ├── config.py            # Загрузка .env
│   └── utils.py
│
├── web/
│   ├── app/main.py          # FastAPI сервер (20+ эндпоинтов)
│   └── static/
│       ├── index.html       # Главная страница (Vue.js)
│       └── analytics.html   # Страница аналитики
│
├── data/
│   ├── hh_vacancies.db      # База данных (создаётся автоматически)
│   └── reports/             # Сгенерированные отчёты
│
├── tests/                   # Тесты (35 штук)
├── config.yaml              # Словари навыков и ключевые слова
├── .env.example             # Пример конфигурации
└── requirements.txt
```

---

## API

После запуска доступна автодокументация: **http://localhost:8000/docs**

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

---

## Устранение проблем

### `ModuleNotFoundError`

```bash
pip install -r requirements.txt
```

### Порт 8000 занят

**Windows:**
```cmd
netstat -ano | findstr :8000
taskkill /F /PID <PID>
```

**Linux / macOS:**
```bash
kill -9 $(lsof -t -i:8000)
```

### Парсер возвращает 403

HH.ru временно блокирует IP при слишком частых запросах — это защита от DDoS.  
Подожди 1–2 часа и попробуй снова. Если используешь VPN или прокси — попробуй отключить.

### Данные не отображаются

Убедись что парсер завершил работу и нашёл хотя бы несколько вакансий. Проверь консоль на ошибки.

---

## Docker

```bash
docker compose up -d
```

Приложение запустится на **http://localhost:8000**. Конфигурация берётся из `.env`.

---

## Контакты

**Разработчик:** Safan Ch  
**Email:** safanch2705@gmail.com  
**GitHub:** https://github.com/LongWinterNight/HH_for_PP

---

**Версия:** 1.2.0
