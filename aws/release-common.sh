#!/usr/bin/env bash
# Sourced by release-api.sh and rollback-api.sh. Run beside production compose.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
STATE_DIR="${RELEASE_STATE_DIR:-.releases}"
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
exec 9>"$STATE_DIR/deploy.lock"
flock -n 9 || { echo "Another release/rollback is running" >&2; exit 1; }
if [[ -z "${API_IMAGE:-}" && -f "$STATE_DIR/current-image" ]]; then
  export API_IMAGE="$(cat "$STATE_DIR/current-image")"
fi
compose() { docker compose -f docker-compose.yml "$@"; }
migrate() { compose --profile migration run --rm --no-deps migrate python -m tools.migrate "$@"; }
wait_ready() {
  for attempt in $(seq 1 30); do
    # Inline check also works when rolling back to an image predating this tooling.
    if compose exec -T nationalactsapi python -c '
import os
from urllib.request import urlopen
from dotenv import load_dotenv
import mariadb
load_dotenv("/app/.env", override=False)
with urlopen("http://127.0.0.1:5000/", timeout=5) as response:
    assert response.status == 200
connection = mariadb.connect(host=os.environ["DB_HOST"], user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"], database=os.environ["DB_DB"], connect_timeout=5)
cursor = connection.cursor()
cursor.execute("SELECT 1 FROM Users LIMIT 1")
cursor.fetchall()
connection.close()
'; then return 0; fi
    sleep 2
  done
  echo "API readiness failed; use rollback-api.sh after reviewing migration results" >&2
  return 1
}
