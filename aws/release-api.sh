#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/release-common.sh"
IMAGE="${1:?Usage: bash release-api.sh repository@sha256:digest}"
[[ "$IMAGE" =~ ^804363746695\.dkr\.ecr\.us-east-1\.amazonaws\.com/nationalactsvip/nationalactsapi@sha256:[a-f0-9]{64}$ ]] || {
  echo "Supply the immutable API image digest printed by deploy.sh" >&2; exit 1;
}
: "${BACKUP_S3_PREFIX:?Set BACKUP_S3_PREFIX=s3://bucket/pre-deploy}"
[[ "$BACKUP_S3_PREFIX" == s3://* ]] || { echo "Backup destination must be S3" >&2; exit 1; }
export API_IMAGE="$IMAGE"
compose pull nationalactsapi migrate
OLD_ID="$(docker inspect --format '{{.Image}}' nationalactsapi)"
OLD_IMAGE="$(docker image inspect --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{end}}' "$OLD_ID")"
OLD_IMAGE="${OLD_IMAGE:-$OLD_ID}"
RELEASE="$(date -u +%Y%m%dT%H%M%SZ)-${IMAGE##*:}"
DIRECTORY="$STATE_DIR/$RELEASE"
mkdir "$DIRECTORY"
chmod 700 "$DIRECTORY"
printf '%s\n' "$OLD_IMAGE" > "$DIRECTORY/previous-image"
printf '%s\n' "$IMAGE" > "$DIRECTORY/image"
migrate current > "$DIRECTORY/schema-before"
if grep -qx unversioned "$DIRECTORY/schema-before"; then
  echo "Adopt the verified baseline first; see docs/database-releases.md" >&2; exit 1
fi
compose exec -T nationalactsdb sh -ec '
  export MYSQL_PWD="$(cat /run/secrets/mysql_root_password)"
  exec mariadb-dump -uroot --single-transaction --quick --routines --events --triggers "$MYSQL_DATABASE"
' | gzip > "$DIRECTORY/database.sql.gz"
gzip -t "$DIRECTORY/database.sql.gz"
sha256sum "$DIRECTORY/database.sql.gz" > "$DIRECTORY/database.sha256"
BACKUP_URI="${BACKUP_S3_PREFIX%/}/$RELEASE.sql.gz"
aws s3 cp "$DIRECTORY/database.sql.gz" "$BACKUP_URI" --only-show-errors
aws s3 cp "$DIRECTORY/database.sha256" "$BACKUP_URI.sha256" --only-show-errors
aws s3 cp "$BACKUP_URI" "$DIRECTORY/backup-verification.sql.gz" --only-show-errors
cmp "$DIRECTORY/database.sql.gz" "$DIRECTORY/backup-verification.sql.gz"
rm "$DIRECTORY/backup-verification.sql.gz"
printf '%s\n' "$BACKUP_URI" > "$DIRECTORY/backup-uri"
printf '%s\n' "$RELEASE" > "$STATE_DIR/rollback-release.tmp"
mv "$STATE_DIR/rollback-release.tmp" "$STATE_DIR/rollback-release"
printf 'migrating\n' > "$DIRECTORY/status"
migrate upgrade
migrate check
migrate current > "$DIRECTORY/schema-after"
printf 'deploying\n' > "$DIRECTORY/status"
compose up -d --no-deps nationalactsapi
wait_ready
printf 'successful\n' > "$DIRECTORY/status"
printf '%s\n' "$IMAGE" > "$STATE_DIR/current-image.tmp"
mv "$STATE_DIR/current-image.tmp" "$STATE_DIR/current-image"
echo "Release $RELEASE successful; backup: $BACKUP_URI"
