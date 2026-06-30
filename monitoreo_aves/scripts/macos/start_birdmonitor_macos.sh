#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
STREAM_CONFIG="${MEDIAMTX_CONFIG:-$PROJECT_DIR/tools/mediamtx/mediamtx.yml}"
BACKEND_HOST="${BIRDMONITOR_BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BIRDMONITOR_BACKEND_PORT:-8000}"

cd "$PROJECT_DIR"

if [[ -d "venv" ]]; then
  # shellcheck disable=SC1091
  source "venv/bin/activate"
fi

if command -v mediamtx >/dev/null 2>&1; then
  MEDIAMTX_BIN="${MEDIAMTX_BIN:-mediamtx}"
elif [[ -x "$PROJECT_DIR/tools/mediamtx/mediamtx" ]]; then
  MEDIAMTX_BIN="${MEDIAMTX_BIN:-$PROJECT_DIR/tools/mediamtx/mediamtx}"
else
  echo "No se ha encontrado MediaMTX. Instala mediamtx o define MEDIAMTX_BIN."
  exit 1
fi

if [[ ! -f "$STREAM_CONFIG" ]]; then
  echo "No se ha encontrado mediamtx.yml. Define MEDIAMTX_CONFIG o colocalo en tools/mediamtx/mediamtx.yml."
  exit 1
fi

if ! command -v python >/dev/null 2>&1; then
  echo "No se ha encontrado python en PATH."
  exit 1
fi

cleanup() {
  if [[ -n "${MEDIAMTX_PID:-}" ]]; then
    kill "$MEDIAMTX_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "Arrancando MediaMTX en puerto 8888..."
"$MEDIAMTX_BIN" "$STREAM_CONFIG" &
MEDIAMTX_PID=$!

echo "Arrancando backend en http://$BACKEND_HOST:$BACKEND_PORT"
python -m uvicorn backend.app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"