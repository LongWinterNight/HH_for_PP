#!/bin/bash
# ============================================================
# Backup Script — автоматический бэкап PostgreSQL
# ============================================================
# Запускать через cron: 0 3 * * * /app/scripts/backup.sh
# ============================================================

set -euo pipefail

# Настройки
BACKUP_DIR="/app/data/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="hh_analytics"
DB_USER="hh_user"
DB_HOST="postgres"
RETENTION_DAYS=30

# Создание директории
mkdir -p "$BACKUP_DIR"

# Бэкап PostgreSQL
echo "[$DATE] Starting PostgreSQL backup..."
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -F c -f "$BACKUP_DIR/hh_analytics_$DATE.dump"

# Бэкап volume данных (raw JSON, отчёты)
echo "[$DATE] Archiving application data..."
tar czf "$BACKUP_DIR/app_data_$DATE.tar.gz" \
    /app/data/raw/ \
    /app/data/processed/ \
    /app/data/reports/ \
    2>/dev/null || true

# Очистка старых бэкапов
echo "[$DATE] Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "*.dump" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "[$DATE] Backup completed successfully."
echo "[$DATE] Files in $BACKUP_DIR:"
ls -lh "$BACKUP_DIR" | tail -5
