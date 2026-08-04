#!/usr/bin/env bash
set -u

PLIST_LABEL="com.birdmonitor.services"
RUNTIME_DIR="$HOME/Library/Application Support/BirdMonitor"
STREAM_NODE_NAME="${BIRDMONITOR_NODE_NAME:-birdmonitor}"
STREAM_NAME="${BIRDMONITOR_STREAM_PATH:-${BIRDMONITOR_STREAM_NAME:-${STREAM_NODE_NAME}-audio}}"
HLS_URL="http://127.0.0.1:8888/$STREAM_NAME/index.m3u8"
BACKEND_ENV="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." &&
  pwd
)/backend/birdmonitor.env"
NETWORK_MODE="$(sed -n 's/^BIRDMONITOR_NETWORK_MODE=//p' "$BACKEND_ENV" | tail -n 1)"
SERVER_HOST="$(sed -n 's/^BIRDMONITOR_SERVER_HOST=//p' "$BACKEND_ENV" | tail -n 1)"

wait_for_tcp_port() {
  local port="$1"
  local attempts="${2:-5}"

  for _ in $(seq 1 "$attempts"); do
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      return 0
    fi

    sleep 1
  done

  return 1
}

echo ""
echo "======================================"
echo " BirdMonitor macOS Status Check"
echo "======================================"
echo ""

echo "LaunchAgent:"
if launchctl print "gui/$UID/$PLIST_LABEL" >/dev/null 2>&1; then
  launchctl print "gui/$UID/$PLIST_LABEL" | sed -n '1,35p'
else
  echo "No esta cargado: $PLIST_LABEL"
fi

echo ""
echo "Procesos MediaMTX:"
pgrep -fl mediamtx || echo "MediaMTX no esta en ejecucion."

echo ""
echo "Procesos uvicorn/python:"
pgrep -fl "uvicorn|backend.app.main" || echo "Backend no detectado por proceso."

echo ""
echo "Perfil de red:"
echo "Modo: ${NETWORK_MODE:-no configurado}"
echo "IP servidor: ${SERVER_HOST:-no configurada}"

echo ""
echo "Puerto 8554 RTSP:"
if [[ -n "$SERVER_HOST" ]] &&
  lsof -nP -iTCP@"$SERVER_HOST":8554 -sTCP:LISTEN >/dev/null 2>&1; then
  lsof -nP -iTCP@"$SERVER_HOST":8554 -sTCP:LISTEN
  echo "RTSP limitado a ${SERVER_HOST}:8554."
else
  echo "ALERTA: RTSP no coincide con la IP del perfil de red."
fi

echo ""
echo "Puerto 8888 MediaMTX:"
wait_for_tcp_port 8888 5 || true
if lsof -nP -iTCP@127.0.0.1:8888 -sTCP:LISTEN >/dev/null 2>&1; then
  lsof -nP -iTCP@127.0.0.1:8888 -sTCP:LISTEN
  echo "HLS limitado correctamente a loopback."
else
  echo "ALERTA: HLS no esta limitado a 127.0.0.1:8888."
fi

echo ""
echo "Puerto 8000 Backend:"
wait_for_tcp_port 8000 10 || true
lsof -nP -iTCP:8000 -sTCP:LISTEN || echo "No hay escucha en 8000."

echo ""
echo "Prueba backend /health:"
HEALTH_RESPONSE="$(curl -fsS --max-time 5 \
  "http://127.0.0.1:8000/health" 2>/dev/null || true)"
if [[ "$HEALTH_RESPONSE" == *'"status":"ok"'* ]] &&
  [[ "$HEALTH_RESPONSE" == *"\"network_mode\":\"$NETWORK_MODE\""* ]] &&
  [[ "$HEALTH_RESPONSE" == *'"network_configured":true'* ]]; then
  echo "Backend y modo de red confirmados."
else
  echo "El backend no confirma el modo de red configurado."
  [[ -n "$HEALTH_RESPONSE" ]] && echo "$HEALTH_RESPONSE"
fi

echo ""
echo "Prueba HLS interno MediaMTX:"
echo "$HLS_URL"
PROXY_USER="$(sed -n 's/^BIRDMONITOR_STREAM_PROXY_USER=//p' "$BACKEND_ENV" | head -n 1)"
PROXY_PASSWORD="$(sed -n 's/^BIRDMONITOR_STREAM_PROXY_PASSWORD=//p' "$BACKEND_ENV" | head -n 1)"
if curl -fsS --max-time 5 \
  --user "$PROXY_USER:$PROXY_PASSWORD" \
  "$HLS_URL" >/dev/null; then
  echo "Manifest HLS disponible."
else
  echo "MediaMTX puede estar levantado, pero el manifest HLS no esta disponible."
  echo "Esto suele significar que la Raspberry todavia no esta publicando en '$STREAM_NAME'."
fi

echo ""
echo "Logs:"
echo "$RUNTIME_DIR"
if [[ -d "$RUNTIME_DIR" ]]; then
  ls -la "$RUNTIME_DIR"
fi
