# 📚 GitHub Instructions — HH.ru Analytics

## 🎯 Цель
Опубликовать проект HH.ru Analytics на GitHub для демонстрации.

---

## 📋 Шаг 1: Подготовка репозитория

### 1.1 Проверка файлов перед коммитом

**✅ Что должно быть в репозитории:**

```
hh_analytics/
├── src/                        # Исходный код
├── web/
│   ├── app/main.py             # FastAPI сервер
│   └── static/index.html       # Vue.js приложение
├── data/
│   ├── hh_analytics.db         # База данных (опционально)
│   └── professions_catalog.json
├── .env.example                # Пример конфигурации
├── .gitignore                  # Git игнор
├── config.yaml                 # Конфигурация парсера
├── requirements.txt            # Python зависимости
├── README.md                   # Основная документация
├── DEPLOYMENT.md               # Инструкция по развёртыванию
├── QUICKSTART.md               # Быстрый старт
└── check_demo_ready.py         # Проверка готовности
```

**❌ Что НЕ должно быть:**

```
.env                    # Содержит секреты
venv/                   # Виртуальное окружение
__pycache__/            # Python кэш
*.pyc                   # Python компиляция
logs/*.log              # Логи
reports/*.xlsx          # Большие файлы отчётов
data/raw/*.json         # Сырые данные (большие)
```

---

## 🚀 Шаг 2: Инициализация Git

### Если Git ещё не инициализирован:

```bash
cd f:\AI_projects\hh_analytics

# Инициализация
git init

# Добавить все файлы
git add .

# Первый коммит
git commit -m "Initial commit: HH.ru Analytics v1.1.0

Features:
- ETL pipeline для сбора вакансий с HH.ru
- Веб-интерфейс с аналитикой
- KPI метрики с трендами
- Топ навыков (Hard/Soft/Tools)
- Фильтры и экспорт (PDF, Excel, CSV)
- Парсер с кэшированием

Tech stack:
- Backend: Python 3.10+, FastAPI
- Frontend: Vue.js 3, TailwindCSS
- Database: SQLite
- Data: Pandas, NumPy
\""
```

### Если Git уже инициализирован:

```bash
cd f:\AI_projects\hh_analytics

# Проверка статуса
git status

# Добавить изменения
git add .

# Закоммитить
git commit -m "Add filters and export functionality v1.1.0

New features:
- Analytics filters (period, domain, regions, experience)
- Export to PDF, Excel, CSV
- Enhanced KPI metrics with trends
- Top-20 skills by category

Updated:
- README.md with full documentation
- DEPLOYMENT.md with setup instructions
- requirements.txt with new dependencies
\""
```

---

## 🌐 Шаг 3: Создание репозитория на GitHub

### 3.1 Создание репозитория

1. Открыть https://github.com/new
2. **Repository name:** `HH_for_PP`
3. **Description:** "HH.ru Analytics — Система анализа вакансий с извлечением навыков"
4. **Visibility:** Public (или Private для закрытого доступа)
5. **НЕ** ставить галочки:
   - ❌ Add a README file
   - ❌ Add .gitignore
   - ❌ Choose a license
6. Нажать **Create repository**

### 3.2 Привязка удалённого репозитория

```bash
# Добавить remote
git remote add origin https://github.com/LongWinterNight/HH_for_PP.git

# Проверить
git remote -v
```

### 3.3 Отправка кода

```bash
# Переименовать ветку в main
git branch -M main

# Отправить на GitHub
git push -u origin main
```

---

## 🔄 Шаг 4: Обновление существующего репозитория

```bash
# 1. Проверить изменения
git status

# 2. Добавить новые файлы
git add .

# 3. Закоммитить
git commit -m "Update: Filters, export, and documentation v1.1.0"

# 4. Запушить
git push origin main
```

---

## 📝 Шаг 5: Настройка репозитория

### 5.1 Добавление тегов (Topics)

На GitHub перейти в репозиторий → Settings → Topics:

```
python
fastapi
vuejs
data-analysis
hhru
web-scraping
etl
analytics
dashboard
pandas
```

### 5.2 Закрепление README

README.md автоматически отображается на главной странице репозитория.

### 5.3 Добавление лицензии

1. Settings → License
2. Выбрать **MIT License**
3. Commit changes

Или через терминал:
```bash
# Создать файл LICENSE
echo "MIT License - see LICENSE file" > LICENSE
git add LICENSE
git commit -m "Add MIT license"
git push
```

---

## 🏷️ Шаг 6: Создание релиза

### 6.1 Тегирование версии

```bash
# Создать тег
git tag -a v1.1.0 -m "Version 1.1.0 - Filters and Export"

# Отправить тег
git push origin v1.1.0
```

### 6.2 Создание релиза на GitHub

1. На GitHub: репозиторий → **Releases** → **Draft a new release**
2. **Tag version:** `v1.1.0`
3. **Release title:** `HH.ru Analytics v1.1.0 - Filters & Export`
4. **Description:**

```markdown
## 🎯 Основные изменения

### Новое в версии 1.1.0

#### Фильтры аналитики
- Период (сегодня, неделя, месяц, квартал, год)
- Домен профессии
- Регионы
- Опыт работы
- Только с зарплатой

#### Экспорт данных
- PDF отчёты с KPI и топ навыков
- Excel с 5 листами (KPI, Hard, Soft, Tools, Данные)
- CSV для импорта

#### Улучшения
- Обновлённые API endpoints с фильтрацией
- Улучшенный UI/UX
- Расширенная документация

### Технические детали

**Backend:**
- FastAPI endpoints с поддержкой фильтров
- Pandas для обработки данных
- ReportLab для PDF экспорта
- XlsxWriter для Excel экспорта

**Frontend:**
- Vue.js 3 компоненты
- TailwindCSS для стилей
- Chart.js для визуализации

### Установка

```bash
git clone https://github.com/LongWinterNight/HH_for_PP.git
cd HH_for_PP/hh_analytics
pip install -r requirements.txt
python web/app/main.py
```

### Документация

- [README.md](README.md) — основная документация
- [QUICKSTART.md](QUICKSTART.md) — быстрый старт
- [DEPLOYMENT.md](DEPLOYMENT.md) — инструкция по развёртыванию

### Авторы

- Safan Ch (safanch2705@gmail.com)

### Лицензия

MIT License
```

5. Нажать **Publish release**

---

## 📊 Шаг 7: GitHub Actions (опционально)

### 7.1 CI/CD для тестов

Создать `.github/workflows/tests.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Run tests
      run: |
        pytest tests/ -v
```

### 7.2 Авто-деплой на Render

Создать `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Render

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Deploy to Render
      env:
        deploy_token: ${{ secrets.RENDER_DEPLOY_TOKEN }}
      run: |
        curl -X POST https://api.render.com/deploy/your-service-id
```

---

## 🔐 Шаг 8: Безопасность

### 8.1 Secrets для GitHub Actions

Settings → Secrets and variables → Actions:

```
HH_API_TOKEN=your_token_here
DATABASE_URL=sqlite:///data/hh_analytics.db
```

### 8.2 Проверка .gitignore

Убедиться что `.env` не попадёт в репозиторий:

```bash
# Проверить что в .gitignore
cat .gitignore | grep ".env"

# Должно быть:
# .env
```

---

## 📈 Шаг 9: Статистика и мониторинг

### 9.1 GitHub Insights

- **Traffic:** Показывает просмотры и клоны
- **Clones:** Кто клонировал репозиторий
- **Referrers:** Откуда приходят пользователи

### 9.2 Добавление badges в README

```markdown
[![Stars](https://img.shields.io/github/stars/LongWinterNight/HH_for_PP.svg)](https://github.com/LongWinterNight/HH_for_PP/stargazers)
[![Forks](https://img.shields.io/github/forks/LongWinterNight/HH_for_PP.svg)](https://github.com/LongWinterNight/HH_for_PP/network)
[![Issues](https://img.shields.io/github/issues/LongWinterNight/HH_for_PP.svg)](https://github.com/LongWinterNight/HH_for_PP/issues)
[![License](https://img.shields.io/github/license/LongWinterNight/HH_for_PP.svg)](https://github.com/LongWinterNight/HH_for_PP/blob/main/LICENSE)
```

---

## 🎓 Шаг 10: Продвижение проекта

### 10.1 Поделиться в соцсетях

**LinkedIn:**
```
🚀 Представляю мой новый проект — HH.ru Analytics!

Система для сбора и анализа вакансий с HH.ru:
✅ ETL pipeline
✅ Веб-интерфейс с аналитикой
✅ KPI метрики и тренды
✅ Экспорт в PDF, Excel, CSV

Tech stack: Python, FastAPI, Vue.js, Pandas

GitHub: https://github.com/LongWinterNight/HH_for_PP

#python #fastapi #vuejs #dataanalysis #webdevelopment
```

**Telegram каналы:**
- Python-разработка
- Вакансии для разработчиков
- Open Source проекты

### 10.2 Добавление на платформы

- [Habr Career](https://career.habr.com/)
- [Hugging Face Spaces](https://huggingface.co/spaces)
- [Product Hunt](https://www.producthunt.com/)

---

## ✅ Чек-лист публикации

### Подготовка:
- [ ] Все файлы на месте
- [ ] .env в .gitignore
- [ ] README.md заполнен
- [ ] Документация актуальна
- [ ] Тесты проходят

### Публикация:
- [ ] Git инициализирован
- [ ] Репозиторий создан
- [ ] Код загружен
- [ ] Теги проставлены
- [ ] Релиз создан

### Настройка:
- [ ] Topics добавлены
- [ ] Лицензия выбрана
- [ ] Secrets настроены
- [ ] CI/CD настроен (опционально)

### Продвижение:
- [ ] Поделиться в соцсетях
- [ ] Обновить резюме
- [ ] Добавить в портфолио

---

## 📞 Поддержка

**Вопросы и предложения:**
- Email: safanch2705@gmail.com
- GitHub Issues: https://github.com/LongWinterNight/HH_for_PP/issues

---

**Успешной публикации! 🚀**
