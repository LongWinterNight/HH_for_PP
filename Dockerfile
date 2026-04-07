# ============================================================
# HH.ru Analytics — Dockerfile (Production)
# ============================================================
# Образ: Python 3.11 slim (минимальный размер)
# Запуск: uvicorn с 4 worker'ами для конкурентности
# ============================================================

FROM python:3.11-slim-bookworm

# Метки
LABEL maintainer="HH.ru Analytics Team"
LABEL description="ETL-система для сбора и анализа вакансий с HH.ru"
LABEL version="2.0.0"

# Переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Рабочая директория
WORKDIR /app

# Системные зависимости (для psycopg2 и других)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копирование зависимостей (кэш Docker layer)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install psycopg2-binary>=2.9.9  # PostgreSQL драйвер

# Копирование исходного кода
COPY src/ ./src/
COPY web/ ./web/
COPY config.yaml .
COPY optimized_parser.py .
COPY main.py .

# Создание директорий для данных и логов
RUN mkdir -p data/raw data/processed data/reports logs

# Непривилегированный пользователь (безопасность)
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

# Порт (для uvicorn)
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Запуск (4 worker'а для конкурентности)
CMD ["uvicorn", "web.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--log-level", "info"]
