#!/bin/bash
set -Eeuo pipefail
if [[ "${CONFIRM_DATABASE_REBUILD:-}" != "DELETE_DATABASE_AND_RESTORE" ]]; then
  echo "Destructive rebuild refused. Use release-api.sh for deployments." >&2
  exit 1
fi
docker compose down -v
aws s3 cp s3://nationalactsvip-mysql-seeds/nationalacts20.sql ./seeds/nationalacts20.sql
docker compose up -d
docker compose -f docker-compose-import.yml run --rm db-import
