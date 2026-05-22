#!/bin/sh
set -e

echo "entrypoint running as uid=$(id -u) gid=$(id -g)"

# Ensure tmp dir exists and is writable
mkdir -p /app/tmp
chown -R 5678:5678 /app/tmp

# Copy dotenv from secrets (root-only readable) into /app/.env for appuser
if [ -f /run/secrets/nationalactsapi_env ]; then
  cp /run/secrets/nationalactsapi_env /app/.env
  chown 5678:5678 /app/.env
  chmod 600 /app/.env
fi

# If you also want MYSQL password available in env for the app:
if [ -f /run/secrets/mysql_root_password ]; then
  export MYSQL_PASSWORD="$(cat /run/secrets/mysql_root_password)"
fi

# Drop privileges to appuser and run the main command
exec su-exec 5678:5678 "$@"
