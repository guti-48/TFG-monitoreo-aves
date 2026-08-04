#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
STREAM_CONFIG_TEMPLATE="${MEDIAMTX_CONFIG:-$PROJECT_DIR/tools/mediamtx/mediamtx.secure.yml}"
BACKEND_ENV="$PROJECT_DIR/backend/birdmonitor.env"
RUNTIME_DIR="$HOME/Library/Application Support/BirdMonitor"
STREAM_CONFIG="$RUNTIME_DIR/mediamtx.secure.runtime.yml"
BACKEND_HOST="${BIRDMONITOR_BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BIRDMONITOR_BACKEND_PORT:-8000}"

cd "$PROJECT_DIR"

if [[ -d "venv" ]]; then
  # shellcheck disable=SC1091
  source "venv/bin/activate"
fi

if [[ -n "${MEDIAMTX_BIN:-}" ]]; then
  :
elif [[ -x "$PROJECT_DIR/tools/mediamtx/macos/mediamtx" ]]; then
  MEDIAMTX_BIN="${MEDIAMTX_BIN:-$PROJECT_DIR/tools/mediamtx/macos/mediamtx}"
elif command -v mediamtx >/dev/null 2>&1; then
  MEDIAMTX_BIN="${MEDIAMTX_BIN:-mediamtx}"
else
  echo "No se ha encontrado MediaMTX. Instala mediamtx o define MEDIAMTX_BIN."
  exit 1
fi

if [[ ! -f "$STREAM_CONFIG_TEMPLATE" ]]; then
  echo "No se ha encontrado tools/mediamtx/mediamtx.secure.yml."
  exit 1
fi
if [[ "$STREAM_CONFIG_TEMPLATE" != *"mediamtx.secure.yml" ]]; then
  echo "BirdMonitor no arrancara con una configuracion MediaMTX no endurecida."
  exit 1
fi
if [[ ! -f "$BACKEND_ENV" ]]; then
  echo "Falta backend/birdmonitor.env."
  echo "Ejecuta configure_security.py y configure_stream_security.py."
  exit 1
fi

NETWORK_MODE="$(sed -n 's/^BIRDMONITOR_NETWORK_MODE=//p' "$BACKEND_ENV" | tail -n 1)"
SERVER_HOST="$(sed -n 's/^BIRDMONITOR_SERVER_HOST=//p' "$BACKEND_ENV" | tail -n 1)"
if [[ "$NETWORK_MODE" != "local" && "$NETWORK_MODE" != "tailscale" ]]; then
  echo "Falta seleccionar el modo local o Tailscale."
  exit 1
fi
if [[ ! "$SERVER_HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "BIRDMONITOR_SERVER_HOST debe ser una IPv4 valida."
  exit 1
fi
mkdir -p "$RUNTIME_DIR"
sed \
  "s/^rtspAddress: :8554$/rtspAddress: ${SERVER_HOST}:8554/" \
  "$STREAM_CONFIG_TEMPLATE" > "$STREAM_CONFIG"
if ! grep -q "^rtspAddress: ${SERVER_HOST}:8554$" "$STREAM_CONFIG"; then
  echo "No se pudo limitar RTSP a la IP del modo de red."
  exit 1
fi
STREAM_CONFIG_DIR="$(cd "$(dirname "$STREAM_CONFIG")" && pwd)"

if [[ -x "$PROJECT_DIR/venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_DIR/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "No se ha encontrado python. Crea el venv o instala Python 3."
  exit 1
fi

cleanup() {
  if [[ -n "${MEDIAMTX_PID:-}" ]]; then
    kill "$MEDIAMTX_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "Arrancando MediaMTX: RTSP ${SERVER_HOST}:8554 y HLS interno 127.0.0.1:8888..."
(cd "$STREAM_CONFIG_DIR" && exec "$MEDIAMTX_BIN" "$STREAM_CONFIG") &
MEDIAMTX_PID=$!

echo "Arrancando backend en http://$BACKEND_HOST:$BACKEND_PORT"
"$PYTHON_BIN" -m uvicorn backend.app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
