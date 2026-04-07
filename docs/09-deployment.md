# 🚀 Развёртывание (Deployment)

## Варианты развёртывания

| Вариант | Сложность | Цена | Для кого |
|---------|-----------|------|----------|
| **Docker Compose** (рекомендуется) | Средняя | 300-500₽/мес | Продакшен |
| Локальный запуск | Низкая | Бесплатно | Разработка/демо |
| VPS без Docker | Высокая | 300-500₽/мес | Устаревший подход |

---

## 🐳 Docker Compose (Рекомендуется)

### Архитектура

```
┌─────────────────────────────────────────────────────────┐
│  Интернет                                                │
└──────────────────┬──────────────────────────────────────┘
                   │ HTTPS (порт 443)
                   ▼
┌─────────────────────────────────────────────────────────┐
│  Caddy (reverse proxy + авто SSL/Let's Encrypt)         │
│  Контейнер: hh_caddy                                     │
└──────────────────┬──────────────────────────────────────┘
                   │ HTTP (внутренняя сеть)
                   ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI (uvicorn, 4 workers)                            │
│  Контейнер: hh_app                                       │
│  ├── /api/dashboard                                      │
│  ├── /api/parser/start (rate limited)                    │
│  └── /static (Vue.js SPA)                                │
└──────────┬──────────────────────────────┬────────────────┘
           │                              │
           ▼                              ▼
┌──────────────────────┐    ┌──────────────────────────────┐
│  PostgreSQL 16       │    │  Volumes (персистентные)      │
│  Контейнер: hh_pg    │    │  ├── postgres_data            │
│  ├── vacancies       │    │  ├── app_data                 │
│  ├── parser_runs     │    │  ├── app_logs                 │
│  └── app_settings    │    │  ├── caddy_data (SSL)         │
└──────────────────────┘    │  └── caddy_config             │
                            └──────────────────────────────┘
```

### Файлы проекта

| Файл | Назначение |
|------|-----------|
| `Dockerfile` | Образ FastAPI приложения |
| `docker-compose.yml` | Оркестрация (app + postgres + caddy) |
| `.dockerignore` | Исключения из образа |
| `caddy/Caddyfile` | Конфиг reverse proxy + SSL |
| `scripts/init_db.sql` | Инициализация схемы PostgreSQL |
| `scripts/backup.sh` | Скрипт бэкапа БД |
| `.env.production.example` | Шаблон production .env |

### Шаг 1: Подготовка сервера (VPS)

**Рекомендуемые провайдеры (Россия, оплата картами РФ):**

| Провайдер | Цена/мес | CPU/RAM/SSD | Дата-центр |
|-----------|----------|-------------|-----------|
| **Timeweb Cloud** | 350-500₽ | 2 vCPU / 2GB / 25GB | Москва |
| **Selectel** | 300-450₽ | 2 vCPU / 2GB / 20GB | СПб |
| **Beget VPS** | 400₽ | 2 vCPU / 2GB / 20GB | Москва |

**Минимальные требования:**
- CPU: 2 vCPU
- RAM: 2 GB
- SSD: 20 GB
- OS: Ubuntu 22.04 или 24.04

### Шаг 2: Установка Docker

```bash
# Подключение к VPS
ssh root@your-server-ip

# Установка Docker + Docker Compose
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# Проверка
docker --version
docker compose version
```

### Шаг 3: Клонирование проекта

```bash
cd /opt
git clone https://github.com/LongWinterNight/HH_for_PP.git
cd HH_for_PP/hh_analytics
```

### Шаг 4: Настройка .env

```bash
# Копируем шаблон
cp .env.production.example .env

# Редактируем
nano .env
```

**Обязательно изменить:**
```env
HH_USER_EMAIL=ваш_email@example.com
POSTGRES_PASSWORD=Сложный_Пароль_2026!
APP_DOMAIN=hh-analytics.example.com  # Ваш реальный домен
```

### Шаг 5: Настройка домена

1. Купите домен (например, на reg.ru или timeweb)
2. Создайте A-запись: `hh-analytics.example.com → IP вашего VPS`
3. В `caddy/Caddyfile` замените `hh-analytics.example.com` на ваш домен

### Шаг 6: Запуск

```bash
# Сборка и запуск всех контейнеров
docker compose up -d --build

# Проверка статус
docker compose ps

# Логи
docker compose logs -f app
docker compose logs -f caddy
```

### Шаг 7: Проверка

```bash
# Healthcheck
curl http://localhost:8000/api/health
# Ожидается: {"status":"ok"}

# SSL проверка (после настройки домена)
curl -I https://hh-analytics.example.com
# Ожидается: HTTP/2 200 + SSL сертификат Let's Encrypt
```

### Управление сервисом

```bash
# Остановка
docker compose down

# Перезапуск
docker compose restart

# Обновление
git pull
docker compose up -d --build

# Логи
docker compose logs -f app

# Бэкап
docker compose exec postgres pg_dump -U hh_user hh_analytics > backup_$(date +%Y%m%d).sql
```

### Настройка бэкапов (cron)

```bash
# Копируем скрипт
chmod +x scripts/backup.sh

# Добавляем в cron (каждый день в 3:00)
crontab -e
# Добавить строку:
0 3 * * * /opt/HH_for_PP/hh_analytics/scripts/backup.sh >> /var/log/hh-backup.log 2>&1
```

---

## 💻 Локальный запуск (для разработки)

```bash
cd hh_analytics
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
python web/run.py
# http://localhost:8000
```

---

## 🔧 Troubleshooting

### Контейнер не запускается

```bash
# Проверка лого
docker compose logs app

# Частые причины:
# 1. PostgreSQL не успел запуститься → подождите 30с
# 2. Ошибка в .env → проверьте синтаксис
# 3. Порт 8000 занят → измените в docker-compose.yml
```

### SSL не работает

```bash
# Проверка домена
nslookup hh-analytics.example.com

# Проверка Caddy
docker compose logs caddy

# Убедитесь что порты 80 и 443 открыты
# В брандмауэре VPS разрешите 80/tcp и 443/tcp
```

### PostgreSQL недоступен

```bash
docker compose logs postgres
docker compose restart postgres
```

### Очистка и пересборка

```bash
docker compose down -v  # Удаляет все volumes (данные!)
docker compose up -d --build
```
