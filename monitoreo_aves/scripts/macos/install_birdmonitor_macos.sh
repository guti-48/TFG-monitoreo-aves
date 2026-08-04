#!/usr/bin/env bash
set -euo pipefail

echo ""
echo "======================================"
echo " BirdMonitor macOS Installer"
echo "======================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
START_SCRIPT="$SCRIPT_DIR/start_birdmonitor_macos.sh"
PLIST_LABEL="com.birdmonitor.services"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$PLIST_LABEL.plist"
RUNTIME_DIR="$HOME/Library/Application Support/BirdMonitor"
STREAM_CONFIG="${MEDIAMTX_CONFIG:-$PROJECT_DIR/tools/mediamtx/mediamtx.secure.yml}"
LOCAL_MEDIAMTX="$PROJECT_DIR/tools/mediamtx/macos/mediamtx"

wait_for_tcp_port() {
  local port="$1"
  local label="$2"
  local attempts="${3:-20}"

  for _ in $(seq 1 "$attempts"); do
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "$label escucha en el puerto $port."
      return 0
    fi

    sleep 1
  done

  echo "Aviso: $label no aparece escuchando en el puerto $port todavia."
  return 1
}

echo "Proyecto detectado en:"
echo "$PROJECT_DIR"
echo ""

case "$PROJECT_DIR" in
  "$HOME/Desktop/"*|"$HOME/Documents/"*|"$HOME/Downloads/"*)
    echo "Este proyecto esta dentro de una carpeta protegida por privacidad de macOS:"
    echo "$PROJECT_DIR"
    echo ""
    echo "Un LaunchAgent puede fallar con 'Operation not permitted' en Desktop, Documents o Downloads."
    echo "Mueve el proyecto a una ruta como:"
    echo "$HOME/Projects/TFG-monitoreo-aves"
    echo ""
    echo "Despues vuelve a ejecutar este instalador desde la nueva ruta."
    exit 1
    ;;
esac

if [[ ! -f "$PROJECT_DIR/backend/app/main.py" ]]; then
  echo "No se ha encontrado backend/app/main.py. Revisa la estructura del proyecto."
  exit 1
fi

if [[ ! -f "$START_SCRIPT" ]]; then
  echo "No se ha encontrado start_birdmonitor_macos.sh."
  exit 1
fi

if [[ ! -f "$STREAM_CONFIG" ]]; then
  echo "No se ha encontrado mediamtx.secure.yml en $STREAM_CONFIG."
  exit 1
fi

if [[ "$STREAM_CONFIG" != *"mediamtx.secure.yml" ]]; then
  echo "BirdMonitor no arrancara con una configuracion MediaMTX no endurecida."
  exit 1
fi

BACKEND_ENV="$PROJECT_DIR/backend/birdmonitor.env"
if [[ ! -f "$BACKEND_ENV" ]]; then
  echo "Falta backend/birdmonitor.env."
  echo "Ejecuta primero configure_security.py y configure_stream_security.py."
  exit 1
fi

for required_key in \
  BIRDMONITOR_STREAM_PUBLISH_PASSWORD_HASH \
  BIRDMONITOR_STREAM_READER_PASSWORD \
  BIRDMONITOR_STREAM_PROXY_PASSWORD \
  BIRDMONITOR_NETWORK_MODE \
  BIRDMONITOR_SERVER_HOST; do
  if ! grep -q "^${required_key}=." "$BACKEND_ENV"; then
    echo "Falta $required_key en backend/birdmonitor.env."
    echo "Ejecuta python scripts/configure_stream_security.py."
    exit 1
  fi
done

NETWORK_MODE="$(sed -n 's/^BIRDMONITOR_NETWORK_MODE=//p' "$BACKEND_ENV" | tail -n 1)"
SERVER_HOST="$(sed -n 's/^BIRDMONITOR_SERVER_HOST=//p' "$BACKEND_ENV" | tail -n 1)"
if [[ "$NETWORK_MODE" != "local" && "$NETWORK_MODE" != "tailscale" ]]; then
  echo "Ejecuta primero scripts/configure_network_mode.py."
  exit 1
fi

if [[ -x "$LOCAL_MEDIAMTX" ]]; then
  MEDIAMTX_BIN="$LOCAL_MEDIAMTX"
elif command -v mediamtx >/dev/null 2>&1; then
  MEDIAMTX_BIN="$(command -v mediamtx)"
else
  echo "No se ha encontrado MediaMTX."
  echo "Coloca el binario darwin en tools/mediamtx/macos/mediamtx o define MEDIAMTX_BIN."
  exit 1
fi

if [[ -d "$PROJECT_DIR/venv" ]]; then
  echo "Entorno virtual detectado: $PROJECT_DIR/venv"
else
  echo "Aviso: no se ha encontrado venv. Se usara python del sistema que vea launchd."
fi

mkdir -p "$PLIST_DIR" "$RUNTIME_DIR"
chmod +x "$START_SCRIPT"
if [[ "$MEDIAMTX_BIN" == "$LOCAL_MEDIAMTX" ]]; then
  chmod +x "$MEDIAMTX_BIN"
fi

if launchctl print "gui/$UID/$PLIST_LABEL" >/dev/null 2>&1; then
  echo "Deteniendo LaunchAgent anterior..."
  launchctl bootout "gui/$UID" "$PLIST_PATH" >/dev/null 2>&1 || true
fi

echo "Creando LaunchAgent en:"
echo "$PLIST_PATH"

/usr/libexec/PlistBuddy -c "Clear dict" "$PLIST_PATH" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :Label string $PLIST_LABEL" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :ProgramArguments array" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :ProgramArguments:0 string /bin/bash" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :ProgramArguments:1 string $START_SCRIPT" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :WorkingDirectory string $PROJECT_DIR" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :RunAtLoad bool true" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :KeepAlive bool true" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :StandardOutPath string $RUNTIME_DIR/birdmonitor.out.log" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :StandardErrorPath string $RUNTIME_DIR/birdmonitor.err.log" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables dict" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:MEDIAMTX_BIN string $MEDIAMTX_BIN" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:MEDIAMTX_CONFIG string $STREAM_CONFIG" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:BIRDMONITOR_BACKEND_HOST string ${BIRDMONITOR_BACKEND_HOST:-0.0.0.0}" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:BIRDMONITOR_BACKEND_PORT string ${BIRDMONITOR_BACKEND_PORT:-8000}" "$PLIST_PATH"
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:PATH string /opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" "$PLIST_PATH"

echo "Cargando LaunchAgent..."
launchctl bootstrap "gui/$UID" "$PLIST_PATH"
launchctl kickstart -k "gui/$UID/$PLIST_LABEL"

echo "Esperando a que arranquen los servicios..."
wait_for_tcp_port 8888 "MediaMTX" 20 || true
wait_for_tcp_port "${BIRDMONITOR_BACKEND_PORT:-8000}" "Backend" 30 || true

echo ""
echo "Instalacion completada."
echo "Modo de red: $NETWORK_MODE"
echo "Backend:  http://$SERVER_HOST:8000"
echo "MediaMTX HLS interno: http://127.0.0.1:8888"
echo "HLS autenticado:     http://127.0.0.1:8000/stream/hls/..."
echo "Logs:     $RUNTIME_DIR"
echo ""
echo "Para comprobar el estado:"
echo "bash scripts/macos/check_birdmonitor_macos.sh"
