#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/release-common.sh"
RELEASE="$(cat "$STATE_DIR/rollback-release")"
[[ "$RELEASE" =~ ^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{64}$ ]] || { echo "Invalid rollback record" >&2; exit 1; }
export API_IMAGE="$(cat "$STATE_DIR/$RELEASE/previous-image")"
# Preceding application code must support the expanded schema.
if [[ "$API_IMAGE" != sha256:* ]]; then compose pull nationalactsapi; fi
compose up -d --no-deps nationalactsapi
wait_ready
printf '%s\n' "$API_IMAGE" > "$STATE_DIR/current-image.tmp"
mv "$STATE_DIR/current-image.tmp" "$STATE_DIR/current-image"
printf 'application-rolled-back\n' > "$STATE_DIR/$RELEASE/status"
echo "Previous API restored. Schema and live data retained."
