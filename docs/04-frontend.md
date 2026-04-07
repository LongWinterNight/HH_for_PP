# 🎨 Frontend (Vue.js 3 SPA)

## Технологии

- **Vue.js 3** (CDN) — реактивный фреймворк
- **Chart.js 4** — графики и диаграммы
- **Tailwind CSS** (CDN) — утилитарные стили
- **Font Awesome 6** — иконки

## Структура `web/static/index.html` (~4300 строк)

```
┌─────────────────────────────────────────────────────┐
│  <head>                                              │
│  ├── Vue.js 3 CDN                                    │
│  ├── Chart.js 4 CDN                                  │
│  ├── Tailwind CSS CDN                               │
│  ├── Font Awesome CDN                                │
│  └── <style> (кастомные стили + анимации)           │
├─────────────────────────────────────────────────────┤
│  <body>                                              │
│  ├── <div id="app"> (Vue корень)                    │
│  │   ├── <nav> (навигация)                          │
│  │   │   ├── Логотип + название                     │
│  │   │   ├── Вкладки: Дашборд, Вакансии, Профессии, │
│  │   │   │   Аналитика, Парсер, Отчёты              │
│  │   │   └── Кнопки: ⚙️ настройки, ❓ помощь       │
│  │   │                                              │
│  │   ├── 🔔 Toast уведомления (удалено)              │
│  │   │                                              │
│  │   ├── ⚙️ Модалка настройки Email                 │
│  │   │   ├── Валидация в реальном времени           │
│  │   │   ├── Сохранение в localStorage + сервер     │
│  │   │   └── Блокировка парсера без email           │
│  │   │                                              │
│  │   ├── 🎓 Onboarding Wizard (модалка)             │
│  │   │   ├── Шаг 1: Укажите запрос                  │
│  │   │   ├── Шаг 2: Запустите парсер               │
│  │   │   └── Шаг 3: Изучите результаты              │
│  │   │                                              │
│  │   ├── <main> (основной контент)                  │
│  │   │   │                                          │
│  │   │   ├── 🚀 Hero-секция                         │
│  │   │   │   ├── Приветствие + кнопка "Запустить"   │
│  │   │   │   └── Всегда видна                        │
│  │   │   │                                          │
│  │   │   ├── 📋 "Как это работает"                  │
│  │   │   │   ├── 3 шага с иконками                  │
│  │   │   │   ├── Стрелки-переходы (десктоп)         │
│  │   │   │   └── Кнопка "Перейти к парсеру"         │
│  │   │   │                                          │
│  │   │   ├── 📊 KPI карточки (4 шт)                 │
│  │   │   │   ├── Всего вакансий + Sparkline         │
│  │   │   │   ├── Всего навыков + Sparkline          │
│  │   │   │   ├── Средняя зарплата + Sparkline       │
│  │   │   │   └── Статус парсера                     │
│  │   │   │                                          │
│  │   │   ├── 📈 Графики и таблицы                    │
│  │   │   │   ├── Топ навыков (прогресс-бары)        │
│  │   │   │   └── Недавние вакансии (таблица)         │
│  │   │   │                                          │
│  │   │   ├── 📉 Тренд зарплат (Chart.js)            │
│  │   │   │                                          │
│  │   │   ├── ⚡ Быстрые действия (4 кнопки)          │
│  │   │   │                                          │
│  │   │   ├── 💼 Вакансии (вкладка)                  │
│  │   │   │   ├── Поиск с autocomplete               │
│  │   │   │   ├── Фильтры + сортировка               │
│  │   │   │   └── Пагинация                          │
│  │   │   │                                          │
│  │   │   ├── 🔍 Поиск профессий (вкладка)           │
│  │   │   ├── 📊 Аналитика (вкладка)                 │
│  │   │   ├── 🤖 Парсер (вкладка)                    │
│  │   │   └── 📄 Отчёты (вкладка)                    │
│  │   │                                              │
│  │   └── 💬 Модалка деталей вакансии                │
│  │                                                  │
│  └── <script> (Vue.js приложение)                   │
│      ├── createApp({ data, computed, methods })     │
│      └── .mount('#app')                             │
└─────────────────────────────────────────────────────┘
```

## Vue.js данные

### `data()` — основные поля

```javascript
currentTab: 'dashboard'           // Активная вкладка
dashboardData: {}                 // Данные дашборда с API
parserState: {}                   // Статус парсера
skeletonLoading: true             // Показывать skeleton?
showOnboarding: false             // Показать onboarding?
showEmailModal: false             // Модалка email
emailInput: ''                    // Введённый email
userEmailConfigured: false        // Email настроен?
isValidEmailFormat: false         // Формат email корректен?
vacanciesList: { items: [] }      // Список вакансий
analyticsData: {}                 // Данные аналитики
```

### `computed` свойства

```javascript
primaryCurrency    // Основная валюта (RUB приоритет)
primaryAvgSalary   // Средняя ЗП в основной валюте
sortedVacancies    // Отсортированные вакансии
vacanciesTrend     // Тренд вакансий (%)
```

### `methods` — ключевые

```javascript
// API вызовы
fetchDashboard()           // GET /api/dashboard
loadVacancies()            // GET /api/vacancies
loadAnalytics()            // GET /api/analytics/*
loadParserStatus()         // GET /api/parser/status

// Email
openEmailModal()           // Открыть модалку
saveEmail()                // POST /api/user/email
loadUserEmail()            // GET /api/user/email
validateEmailInput()       // Валидация в реальном времени

// Парсер
startParser()              // POST /api/parser/start
stopParser()               // GET /api/parser/stop

// Утилиты
formatNumber(num)          // 150000 → "150 000"
getCurrencySymbol(code)    // "RUB" → "₽"
formatDate(dateStr)        // ISO → ru-RU
drawSparkline(id, data)    // Рисует мини-график на canvas
```

## Анимации

| Анимация | Где используется |
|----------|-----------------|
| `fadeInUp` | KPI-карточки (stagger) |
| `slideInRight` | Skill bars |
| `scaleIn` | Модалки |
| `shimmer` | Skeleton-заглушки |
| `fade` | Переходы вкладок |

## API_BASE

```javascript
const API_BASE = 'http://localhost:8000/api';
```

Для продакшена изменить на реальный URL.

## Скелетон-загрузка

```javascript
// При загрузке дашборда:
fetchDashboard() {
    this.skeletonLoading = true;
    // ... fetch ...
    setTimeout(() => {
        this.skeletonLoading = false;  // Минимум 600мс
    }, 600);
}
```

## Sparklines (мини-графики)

```javascript
drawSparkline(canvasId, data, lineColor, fillColor) {
    // Canvas 2D рисует линию + заполнение
    // Данные за 14 дней из dashboardData.sparklines
}
```

## Автообновление

```javascript
mounted() {
    // Каждые 2 секунды:
    setInterval(() => {
        this.loadParserStatus();
    }, 2000);
}
```
