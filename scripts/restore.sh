#!/bin/sh

set -e

BACKUP_DIR="/backups"

echo "========================================"
echo "PostgreSQL Database Restore Script"
echo "========================================"
echo ""

# Function to list available backups
list_backups() {
    echo "Available backups in ${BACKUP_DIR}:"
    echo ""
    ls -lht ${BACKUP_DIR}/backup_*.sql.gz 2>/dev/null | awk '{print NR") " $9 " (" $5 ", " $6 " " $7 " " $8 ")"}'
    echo ""
}

get_latest_backup() {
    ls -t ${BACKUP_DIR}/backup_*.sql.gz 2>/dev/null | head -n 1
}

if [ ! -d "${BACKUP_DIR}" ]; then
    echo "ERROR: Backup directory ${BACKUP_DIR} does not exist!"
    exit 1
fi

BACKUP_COUNT=$(ls -1 ${BACKUP_DIR}/backup_*.sql.gz 2>/dev/null | wc -l)
if [ ${BACKUP_COUNT} -eq 0 ]; then
    echo "ERROR: No backup files found in ${BACKUP_DIR}!"
    echo "Backup files should match pattern: backup_*.sql.gz"
    exit 1
fi

if [ -z "$1" ]; then
    BACKUP_FILE=$(get_latest_backup)
    echo "No backup file specified. Using latest backup:"
    echo "${BACKUP_FILE}"
    echo ""
else
    if [ -f "$1" ]; then
        BACKUP_FILE="$1"
    elif [ -f "${BACKUP_DIR}/$1" ]; then
        BACKUP_FILE="${BACKUP_DIR}/$1"
    else
        echo "ERROR: Backup file not found: $1"
        echo ""
        list_backups
        exit 1
    fi
fi

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
BACKUP_DATE=$(stat -c %y "${BACKUP_FILE}" 2>/dev/null || stat -f "%Sm" "${BACKUP_FILE}")

echo "Backup file: ${BACKUP_FILE}"
echo "Size: ${BACKUP_SIZE}"
echo "Date: ${BACKUP_DATE}"
echo ""

echo "⚠️  WARNING ⚠️"
echo "This will:"
echo "  1. Terminate all connections to the database"
echo "  2. DROP the existing database '${POSTGRES_DB}'"
echo "  3. Recreate it from the backup"
echo "  4. ALL CURRENT DATA WILL BE LOST"
echo ""
echo "Available backups:"
list_backups

read -p "Are you sure you want to continue? (type 'yes' to confirm): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Restore cancelled."
    exit 0
fi

echo ""
echo "Starting restore process..."
echo ""

echo "Step 1/4: Terminating active connections..."
psql -U ${POSTGRES_USER} -d postgres -c "
    SELECT pg_terminate_backend(pg_stat_activity.pid)
    FROM pg_stat_activity
    WHERE pg_stat_activity.datname = '${POSTGRES_DB}'
    AND pid <> pg_backend_pid();
" 2>/dev/null || echo "No active connections found"

# Step 2: Drop the database
echo "Step 2/4: Dropping database '${POSTGRES_DB}'..."
psql -U ${POSTGRES_USER} -d postgres -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};"

# Step 3: Recreate the database
echo "Step 3/4: Creating fresh database '${POSTGRES_DB}'..."
psql -U ${POSTGRES_USER} -d postgres -c "CREATE DATABASE ${POSTGRES_DB};"

# Step 4: Restore from backup
echo "Step 4/4: Restoring data from backup..."
gunzip -c "${BACKUP_FILE}" | psql -U ${POSTGRES_USER} -d ${POSTGRES_DB}

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ Restore completed successfully!"
    echo "=========================================="
    echo ""
    echo "Database '${POSTGRES_DB}' has been restored from:"
    echo "${BACKUP_FILE}"
    echo ""

    echo "Database statistics:"
    psql -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "
        SELECT schemaname, tablename,
               pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
        FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
        LIMIT 10;
    "
else
    echo ""
    echo "=========================================="
    echo "❌ Restore FAILED!"
    echo "=========================================="
    echo ""
    echo "The database may be in an inconsistent state."
    echo "Please check the error messages above."
    exit 1
fi