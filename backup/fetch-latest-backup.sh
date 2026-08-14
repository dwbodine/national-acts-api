#!/usr/bin/env bash
set -Eeuo pipefail

#######################################
# CONFIG
#######################################
S3_BUCKET="nationalactsvip-mysql-backup"
S3_PREFIX="mysql/nationalacts20"

# Local export directory (inside container or host mount)
OUTPUT_DIR="/backups"

# Presigned URL settings
EXPORT_PREFIX="exports"
PRESIGN_EXPIRES_SECONDS=3600   # 1 hour

#######################################
# PREP
#######################################
mkdir -p "$OUTPUT_DIR"

echo "Locating latest backup in s3://${S3_BUCKET}/${S3_PREFIX}/ ..."

#######################################
# FIND LATEST BACKUP
#######################################
LATEST_KEY=$(aws s3api list-objects-v2 \
  --bucket "$S3_BUCKET" \
  --prefix "$S3_PREFIX/" \
  --query 'sort_by(Contents || `[]`, &LastModified)[-1].Key' \
  --output text)

if [[ -z "$LATEST_KEY" || "$LATEST_KEY" == "None" ]]; then
  echo "ERROR: No backups found." >&2
  exit 1
fi

BACKUP_DATE=$(basename "$LATEST_KEY" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' || date -u +%F)

FILENAME="nationalacts_${BACKUP_DATE}.sql"

LOCAL_SQL="${OUTPUT_DIR}/${FILENAME}"
EXPORT_KEY="${EXPORT_PREFIX}/${FILENAME}"

echo "Latest backup:"
echo "  s3://${S3_BUCKET}/${LATEST_KEY}"
echo

#######################################
# DOWNLOAD + UNZIP
#######################################
echo "Downloading and extracting backup..."
aws s3 cp "s3://${S3_BUCKET}/${LATEST_KEY}" - \
| gunzip > "$LOCAL_SQL"

#######################################
# VALIDATE
#######################################
if [[ ! -s "$LOCAL_SQL" ]]; then
  echo "ERROR: Extracted SQL file is empty" >&2
  exit 1
fi

SQL_SIZE=$(stat -c%s "$LOCAL_SQL")
if (( SQL_SIZE < 1048576 )); then
  echo "ERROR: SQL file too small (${SQL_SIZE} bytes)" >&2
  exit 1
fi

echo "Local export complete:"
ls -lh "$LOCAL_SQL"
echo

#######################################
# UPLOAD EXPORTED SQL (OPTIONAL BUT DEFAULT)
#######################################
echo "Uploading SQL export for download..."
aws s3 cp "$LOCAL_SQL" "s3://${S3_BUCKET}/${EXPORT_KEY}"

#######################################
# GENERATE PRESIGNED URL
#######################################
PRESIGNED_URL=$(aws s3 presign \
  "s3://${S3_BUCKET}/${EXPORT_KEY}" \
  --expires-in "$PRESIGN_EXPIRES_SECONDS")

#######################################
# OUTPUT
#######################################
echo "========================================"
echo "EXPORT READY"
echo
echo "Presigned download URL (expires in $((PRESIGN_EXPIRES_SECONDS / 60)) minutes):"
echo
echo "$PRESIGNED_URL"
echo
echo "Local file:"
echo "  $LOCAL_SQL"
echo "========================================"
