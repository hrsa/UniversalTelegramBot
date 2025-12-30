FROM postgres:18.1-alpine

RUN apk add --no-cache dcron

COPY scripts/backup.sh /usr/local/bin/backup.sh
COPY scripts/restore.sh /usr/local/bin/restore.sh
COPY scripts/setup-cron.sh /usr/local/bin/setup-cron.sh

RUN chmod +x /usr/local/bin/backup.sh \
    && chmod +x /usr/local/bin/restore.sh \
    && chmod +x /usr/local/bin/setup-cron.sh

ENTRYPOINT ["/usr/local/bin/setup-cron.sh"]
CMD ["postgres"]