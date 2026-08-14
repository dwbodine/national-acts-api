#!/usr/bin/env sh
set -Eeuo pipefail

BACKUP_ENV_FILE="${BACKUP_ENV_FILE:-/backup/backup.env}"
if [ -f "$BACKUP_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$BACKUP_ENV_FILE"
  set +a
fi

: "${MYSQL_DATABASE:?MYSQL_DATABASE is required}"
: "${MYSQL_CONTAINER:?MYSQL_CONTAINER is required}"
: "${MYSQL_USER:?MYSQL_USER is required}"
: "${S3_BUCKET:?S3_BUCKET is required}"

if [ -z "${MYSQL_PASSWORD:-}" ]; then
  : "${MYSQL_PASSWORD_FILE:?Set MYSQL_PASSWORD or MYSQL_PASSWORD_FILE}"
  MYSQL_PASSWORD=$(cat "$MYSQL_PASSWORD_FILE")
fi

DATE="$(date -u +'%Y-%m-%d_%H-%M-%S')"
S3_KEY="${S3_KEY:-mysql/${MYSQL_DATABASE}/${DATE}.sql.gz}"

docker exec "${MYSQL_CONTAINER}" \
  mariadb-dump \
    -h 127.0.0.1 \
    -u"${MYSQL_USER}" \
    -p"${MYSQL_PASSWORD}" \
    --single-transaction \
    --quick \
    --lock-tables=false \
    "${MYSQL_DATABASE}" \
| gzip -1 \
| aws s3 cp - "s3://${S3_BUCKET}/${S3_KEY}"

echo "Backup uploaded: s3://${S3_BUCKET}/${S3_KEY}"
