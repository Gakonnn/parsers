#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_BIN="$ROOT_DIR/venv/bin/python"

if [[ ! -x "$PY_BIN" ]]; then
  echo "Python not found: $PY_BIN" >&2
  exit 1
fi

echo "[bootstrap] Using: $PY_BIN"
"$PY_BIN" -m pip install --upgrade pip
"$PY_BIN" -m pip install selenium
"$PY_BIN" -m pip install psycopg2-binary
"$PY_BIN" -m pip install -e "$ROOT_DIR/unified_sources/2gis"

echo "[bootstrap] Unified dependencies installed successfully."
