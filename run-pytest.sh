#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_ROOT="$ROOT_DIR/test_runtime/tmp"

mkdir -p "$TMP_ROOT"

export TMPDIR="$TMP_ROOT"
export TMP="$TMP_ROOT"
export TEMP="$TMP_ROOT"

"$ROOT_DIR/.venv/Scripts/python.exe" -m pytest "$@"
