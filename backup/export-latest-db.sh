#!/usr/bin/env bash
set -euo pipefail

CONTAINER="mysql-backup"
SCRIPT="/fetch-latest-backup.sh"

docker exec "$CONTAINER" "$SCRIPT"