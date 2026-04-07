# 🚀 Развёртывание (Deployment)

## Локальный запуск

```bash
cd hh_analytics
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
python web/run.py
# http://localhost:8000
```

## Конфигурация

### .env файл

```env
# HH.ru API Configuration
HH_USER_EMAIL=your_email@example.com

# Rate Limiting
API_REQUEST_DELAY=1.0

# Лимиты
MAX_PAGES=10
DAYS_BACK=30

# Пути
DATA_DIR=data
DB_PATH=data/hh_vacancies.db

# Логирование
LOG_LEVEL=INFO
LOG_FILE=logs/hh_analytics.log
```

## Развёртывание на VPS (Россия)

### Рекомендуемые провайдеры

| Провайдер | Цена/мес | Оплата из РФ | Дата-центр |
|-----------|----------|-------------|-----------|
| **Timeweb Cloud** | 300-450₽ | ✅ | Москва |
| **Selectel** | 200-400₽ | ✅ | СПб |
| **Beget VPS** | 350₽ | ✅ | Москва |

### Минимальные требования

| Ресурс | Минимум | Рекомендовано |
|--------|---------|---------------|
| CPU | 1 vCPU | 2 vCPU |
| RAM | 1 GB | 2 GB |
| SSD | 15 GB | 25 GB |
| OS | Ubuntu 22.04 | Ubuntu 24.04 |

### Шаги развёртывания

```bash
# 1. Подключение к VPS
ssh root@your-server-ip

# 2. Установка зависимостей
apt update && apt install -y python3.11 python3.11-venv nginx

# 3. Клонирование репозитория
git clone https://github.com/LongWinterNight/HH_for_PP.git
cd HH_for_PP/hh_analytics

# 4. Виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Создание .env
cp .env.example .env
nano .env  # Укажите свой email

# 6. Запуск
python web/run.py
```

### Nginx как reverse proxy

```nginx
server {
    listen 80;
    server_name your-domain.ru;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### systemd сервис

```ini
[Unit]
Description=HH.ru Analytics
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/HH_for_PP/hh_analytics
ExecStart=/opt/HH_for_PP/hh_analytics/venv/bin/python web/run.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable hh-analytics
sudo systemctl start hh-analytics
```

## SSL (Let's Encrypt)

```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d your-domain.ru
```

## Миграция на PostgreSQL (продакшен)

```bash
# Установка PostgreSQL
apt install postgresql postgresql-contrib

# Создание БД
sudo -u postgres psql
CREATE DATABASE hh_analytics;
CREATE USER hh_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE hh_analytics TO hh_user;

# Обновление .env
DB_URL=postgresql+psycopg2://hh_user:your_password@localhost:5432/hh_analytics
```

## Мониторинг

```bash
# Логи
tail -f logs/hh_analytics.log

# Статус сервиса
sudo systemctl status hh-analytics

# Ресурсы
htop
df -h
```

## Бэкапы

```bash
#!/bin/bash
# backup.sh
DATE=$(date +%Y%m%d_%H%M%S)
sqlite3 data/hh_vacancies.db ".backup data/backups/hh_vacancies_$DATE.db"
# Очистка старых бэкапов (>30 дней)
find data/backups/ -name "*.db" -mtime +30 -delete
```

```bash
# Cron: каждый день в 3:00
0 3 * * * /opt/HH_for_PP/hh_analytics/scripts/backup.sh
```

## Troubleshooting

### Порт 8000 занят
```bash
netstat -tlnp | grep 8000
kill -9 <PID>
```

### ModuleNotFoundError
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### База данных пуста
```bash
# Проверить путь к БД в .env
# Или запустить парсер через интерфейс
```

### Сервер не отвечает
```bash
sudo systemctl restart hh-analytics
sudo journalctl -u hh-analytics -n 50
```
