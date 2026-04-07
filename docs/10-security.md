# 🔒 Безопасность и настройки

## Email для HH API

### Почему это важно

HH.ru требует идентификации пользователя. Без email:
- ❌ Парсер не запустится (403 ошибка)
- ❌ API вернёт ошибку аутентификации
- ❌ Риск бана IP за анонимные запросы

### Как настроить

1. Открыть проект → нажать ⚙️ (или ⚠️ если email не настроен)
2. Ввести email от аккаунта HH.ru
3. Нажать "Сохранить"
4. Проверить ✅ зелёную рамку (формат корректен)

### Валидация

**Клиентская (frontend):**
```javascript
// Регулярное выражение
/^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/

// Кнопка "Сохранить" disabled пока email не валиден
```

**Серверная (backend):**
```python
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

@app.post("/api/user/email")
def set_user_email(email_data: dict):
    email = email_data.get("email", "").strip()
    if not email:
        raise HTTPException(400, "Email не может быть пустым")
    if not EMAIL_REGEX.match(email):
        raise HTTPException(400, "Неверный формат email")
```

### Где хранится

| Место | Назначение |
|-------|-----------|
| `user_settings` (in-memory) | Быстрый доступ в рамках сессии сервера |
| `.env` файл (`HH_USER_EMAIL=`) | Постоянное хранение |
| `localStorage` (`hh_user_email`) | Кэш на стороне клиента |

---

## Защита от бана HH API

### Rate Limiting

```python
# В api_client.py
self.delay = 1.0  # Задержка между запросами (секунды)

# В config.yaml
API_REQUEST_DELAY=1.0
```

### Retry Logic

```python
# tenacity — автоматический retry при ошибках
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type(requests.RequestException)
)
def _make_request(self, url, params):
    ...
```

### Обработка 429 (Too Many Requests)

```python
if response.status_code == 429:
    time.sleep(60)  # Ждём 1 минуту
    return self._make_request(url, params)  # Retry
```

---

## .env файл

### Что содержит

```env
HH_USER_EMAIL=your_email@example.com  # ⚠️ Обязательно!
API_REQUEST_DELAY=1.0
MAX_PAGES=10
DAYS_BACK=30
DB_PATH=data/hh_vacancies.db
LOG_LEVEL=INFO
LOG_FILE=logs/hh_analytics.log
```

### .gitignore

```gitignore
.env                    # Секреты
data/*.db               # БД (опционально)
data/raw/*.json         # Сырые данные
data/reports/*.xlsx     # Отчёты
logs/*.log              # Логи
```

**Никогда не коммитьте `.env` в Git!**

---

## CORS (Cross-Origin Resource Sharing)

**Сейчас (dev):**
```python
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
```

**Для продакшена:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.ru"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

---

## SQL-инъекции

**Защита:** SQLAlchemy ORM использует параметризованные запросы:
```python
# Безопасно (параметризация)
session.query(VacancyModel).filter_by(vacancy_id=vacancy_id).first()

# Никогда не делать:
cursor.execute(f"SELECT * FROM vacancies WHERE id = {user_input}")
```

---

## XSS (Cross-Site Scripting)

**Защита:** Vue.js автоматически экранирует `{{ }}`:
```html
<!-- Безопасно (Vue экранирует) -->
<p>{{ vacancy.name }}</p>

<!-- Опасно (raw HTML) -->
<p v-html="vacancy.description"></p>  <!-- Не используется в проекте -->
```

---

## Чек-лист безопасности

| Проверка | Статус |
|----------|--------|
| `.env` не в Git | ✅ |
| Email обязателен для парсера | ✅ |
| Rate limiting (1с задержка) | ✅ |
| Retry logic (tenacity) | ✅ |
| SQL-инъекции защищены | ✅ |
| XSS защищены (Vue.js) | ✅ |
| CORS настроен (для prod) | ⏳ Нужно изменить |
| SSL (для prod) | ⏳ Настроить при деплое |
| Бэкапы БД | ⏳ Настроить cron |
