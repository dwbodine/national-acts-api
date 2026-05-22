#!/usr/bin/env sh
set -Eeuo pipefail

DATE="$(date -u +'%Y-%m-%d_%H-%M-%S')"
S3_KEY="mysql/${MYSQL_DATABASE}/${DATE}.sql.gz"

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