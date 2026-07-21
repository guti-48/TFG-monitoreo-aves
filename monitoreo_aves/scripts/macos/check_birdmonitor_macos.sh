#!/usr/bin/env bash
set -u

PLIST_LABEL="com.birdmonitor.services"
RUNTIME_DIR="$HOME/Library/Application Support/BirdMonitor"
STREAM_NODE_NAME="${BIRDMONITOR_NODE_NAME:-birdmonitor}"
STREAM_NAME="${BIRDMONITOR_STREAM_PATH:-${BIRDMONITOR_STREAM_NAME:-${STREAM_NODE_NAME}-audio}}"
HLS_URL="http://127.0.0.1:8888/$STREAM_NAME/index.m3u8"
STREAM_CONTROL_URL="http://127.0.0.1:8000/stream/control?node_name=$STREAM_NODE_NAME"

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
echo "Puerto 8888 MediaMTX:"
wait_for_tcp_port 8888 5 || true
lsof -nP -iTCP:8888 -sTCP:LISTEN || echo "No hay escucha en 8888."

echo ""
echo "Puerto 8000 Backend:"
wait_for_tcp_port 8000 10 || true
lsof -nP -iTCP:8000 -sTCP:LISTEN || echo "No hay escucha en 8000."

echo ""
echo "Prueba backend /devices/:"
if curl -fsS --max-time 5 "http://127.0.0.1:8000/devices/" >/dev/null; then
  echo "Backend responde correctamente."
else
  echo "No se pudo conectar con el backend."
fi

echo ""
echo "Prueba backend /stream/control para nodo '$STREAM_NODE_NAME':"
if curl -fsS --max-time 5 "$STREAM_CONTROL_URL" >/dev/null; then
  echo "Control de stream responde correctamente."
else
  echo "No se pudo consultar /stream/control para '$STREAM_NODE_NAME'."
fi

echo ""
echo "Prueba HLS MediaMTX:"
echo "$HLS_URL"
if curl -fsS --max-time 5 "$HLS_URL" >/dev/null; then
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
