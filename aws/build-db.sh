#!/bin/bash
set -Eeuo pipefail
if [[ "${CONFIRM_DATABASE_REBUILD:-}" != "DELETE_DATABASE_AND_RESTORE" ]]; then
  echo "Destructive database rebuild refused. Use release-api.sh for deployments." >&2
  exit 1
fi
docker compose stop nationalactsdb
docker compose rm -fsv nationalactsdb
docker rmi 804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/nationalactsdb:latest
docker volume rm nationalactsvip_db_data
docker pull 804363746695.dkr.ecr.us-east-1.amazonaws.com/nationalactsvip/nationalactsdb:latest
aws s3 cp s3://nationalactsvip-mysql-seeds/nationalacts20.sql ./seeds/nationalacts20.sql
docker compose -p nationalactsvip up -d nationalactsdb
