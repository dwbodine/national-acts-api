#!/usr/bin/env sh
set -Eeuo pipefail

# use export S3_KEY="mysql/nationalacts20/2025-12-17_19-05-30.sql.gz"

#######################################
# REQUIRED ENVIRONMENT VARIABLES
#######################################
: "${MYSQL_CONTAINER:?Missing MYSQL_CONTAINER}"
: "${MYSQL_USER:?Missing MYSQL_USER}"
: "${MYSQL_PASSWORD:?Missing MYSQL_PASSWORD}"
: "${MYSQL_DATABASE:?Missing MYSQL_DATABASE}"
: "${S3_BUCKET:?Missing S3_BUCKET}"
: "${S3_KEY:?Missing S3_KEY}"
: "${AWS_REGION:?Missing AWS_REGION}"

#######################################
# CONFIRMATION PROMPT (ANTI-OOPS)
#######################################
echo "WARNING: This will restore the following backup:"
echo "  s3://${S3_BUCKET}/${S3_KEY}"
echo "Into database:"
echo "  ${MYSQL_DATABASE}_restore"
echo
printf "Type RESTORE to continue: "
read CONFIRM

if [ "$CONFIRM" != "RESTORE" ]; then
  echo "Restore aborted."
  exit 1
fi

#######################################
# OPTIONAL: RECREATE DATABASE
#######################################
echo "Recreating database ${MYSQL_DATABASE}..."

docker exec "${MYSQL_CONTAINER}" mariadb \
  -u"${MYSQL_USER}" \
  -p"${MYSQL_PASSWORD}" \
  -e "DROP DATABASE IF EXISTS \`"${MYSQL_DATABASE}_restore"\`; CREATE DATABASE \`"${MYSQL_DATABASE}_restore"\`;"

#######################################
# RESTORE FROM S3
#######################################
echo "Restoring backup..."

aws s3 cp "s3://${S3_BUCKET}/${S3_KEY}" - \
| gunzip \
| docker exec -i "${MYSQL_CONTAINER}" mariadb \
    -u"${MYSQL_USER}" \
    -p"${MYSQL_PASSWORD}" \
    "${MYSQL_DATABASE}_restore"

echo "Restore completed successfully."
