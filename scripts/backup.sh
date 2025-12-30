#!/bin/sh

BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/backup_${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

echo "$(date): Starting database backup to ${BACKUP_FILE}"

mkdir -p ${BACKUP_DIR}

pg_dump -U ${POSTGRES_USER} ${POSTGRES_DB} | gzip > ${BACKUP_FILE}

if [ $? -eq 0 ]; then
    echo "$(date): Backup completed successfully: ${BACKUP_FILE}"

    SIZE=$(du -h ${BACKUP_FILE} | cut -f1)
    echo "$(date): Backup size: ${SIZE}"
else
    echo "$(date): Backup failed!"
    exit 1
fi

find ${BACKUP_DIR} -name "backup_*.sql.gz" -type f -mtime +7 -delete
echo "$(date): Cleaned up old backups (older than 7 days)"