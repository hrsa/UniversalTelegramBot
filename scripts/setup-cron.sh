#!/bin/sh

echo "Setting up cron job for database backups..."

apk add --no-cache dcron

mkdir -p /backups
chown postgres:postgres /backups

chmod +x /usr/local/bin/backup.sh
mkdir -p /var/log
touch /var/log/backup.log
chown postgres:postgres /var/log/backup.log

echo "0 2 * * * /usr/local/bin/backup.sh >> /var/log/backup.log 2>&1" | crontab -u postgres -

crond -b -l 2

echo "Cron job configured for postgres user"
echo "Starting PostgreSQL..."

exec docker-entrypoint.sh "$@"