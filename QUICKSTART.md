# ⚡ Быстрый старт — HH.ru Analytics

## 🚀 Запуск за 1 минуту

### Windows

```bash
# 1. Открыть терминал в папке проекта
cd f:\AI_projects\hh_analytics

# 2. Активировать виртуальное окружение
venv\Scripts\activate

# 3. Запустить сервер
python web/app/main.py

# 4. Открыть браузер
# http://localhost:8000
```

### Linux/macOS

```bash
cd hh_analytics
source venv/bin/activate
python3 web/app/main.py
# http://localhost:8000
```

---

## 📦 Первая установка

```bash
# 1. Клонировать репозиторий
git clone https://github.com/LongWinterNight/HH_for_PP.git
cd HH_for_PP/hh_analytics

# 2. Создать виртуальное окружение
python -m venv venv

# 3. Активировать
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 4. Установить зависимости
pip install -r requirements.txt

# 5. Создать .env файл
copy .env.example .env  # Windows
# или
cp .env.example .env    # Linux/macOS

# 6. Запустить сервер
python web/app/main.py
```

---

## 🎯 Демонстрация за 5 минут

### 1. Дашборд (2 мин)
- http://localhost:8000
- Показать KPI метрики
- Показать топ навыков

### 2. Аналитика (2 мин)
- Вкладка "Аналитика"
- Применить фильтр "За месяц"
- Экспорт в PDF

### 3. Вакансии (1 мин)
- Вкладка "Вакансии"
- Поиск "Python"
- Открыть вакансию

---

## 🔧 Проблемы?

| Проблема | Решение |
|----------|---------|
| Порт 8000 занят | `netstat -ano \| findstr :8000` → `taskkill /F /PID <PID>` |
| ModuleNotFoundError | `pip install -r requirements.txt` |
| Нет данных | Запустить парсер или проверить путь к БД |
| Браузер не открывается | Открыть вручную http://localhost:8000 |

---

## 📞 Контакты

- Email: safanch2705@gmail.com
- GitHub: https://github.com/LongWinterNight/HH_for_PP

**Версия:** 1.1.0 | **Дата:** 31.03.2026
