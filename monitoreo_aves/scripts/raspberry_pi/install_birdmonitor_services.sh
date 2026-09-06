#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Uso: sudo ./scripts/raspberry_pi/install_birdmonitor_services.sh [opciones]

Opciones:
  --user USUARIO       Usuario que ejecuta captura y FFmpeg (por defecto: SUDO_USER o pi)
  --python RUTA        Python del entorno BirdNET (por defecto: venv/bin/python)
  --alsa-device PCM    Entrada FFmpeg (por defecto: plug:micshared)
  -h, --help           Muestra esta ayuda

Requiere /etc/birdmonitor/birdmonitor.env. Instala las unidades de captura,
supervision del directo y publicacion RTSP sin guardar secretos en ellas.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
SERVICE_USER="${SUDO_USER:-pi}"
PYTHON_BIN="$PROJECT_DIR/venv/bin/python"
ALSA_DEVICE="plug:micshared"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      SERVICE_USER="${2:-}"
      shift 2
      ;;
    --python)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    --alsa-device)
      ALSA_DEVICE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Argumento no reconocido: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${EUID}" -ne 0 ]]; then
  echo "Ejecuta este instalador con sudo." >&2
  exit 1
fi
if [[ "$PROJECT_DIR" =~ [[:space:]] || "$PYTHON_BIN" =~ [[:space:]] ]]; then
  echo "La ruta del proyecto y la del entorno Python no pueden contener espacios." >&2
  exit 1
fi
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "No existe el usuario $SERVICE_USER." >&2
  exit 1
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python no ejecutable: $PYTHON_BIN" >&2
  echo "Crea el venv o indica --python /ruta/al/python." >&2
  exit 1
fi
if [[ ! -f /etc/birdmonitor/birdmonitor.env ]]; then
  echo "Falta /etc/birdmonitor/birdmonitor.env." >&2
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "No se encuentra ffmpeg." >&2
  exit 1
fi
if ! command -v arecord >/dev/null 2>&1; then
  echo "No se encuentra arecord. Instala alsa-utils." >&2
  exit 1
fi
if [[ ! "$ALSA_DEVICE" =~ ^[A-Za-z0-9_.:,+-]+$ ]]; then
  echo "Dispositivo ALSA no valido: $ALSA_DEVICE" >&2
  exit 2
fi
if ! arecord -L 2>/dev/null | grep -Fxq "micshared" && [[ "$ALSA_DEVICE" == *"micshared"* ]]; then
  echo "No existe el PCM micshared. Ejecuta primero configure_shared_microphone.sh." >&2
  exit 1
fi

SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
SERVICE_HOME="$(getent passwd "$SERVICE_USER" | cut -d: -f6)"
if [[ -z "$SERVICE_HOME" || ! -d "$SERVICE_HOME" ]]; then
  echo "No se puede resolver el directorio personal de $SERVICE_USER." >&2
  exit 1
fi
NODE_DIR="$PROJECT_DIR/hardware/raspberry_pi"
for required in "$NODE_DIR/mainNode.py" "$NODE_DIR/supervisor.py"; do
  if [[ ! -f "$required" ]]; then
    echo "No se encuentra $required." >&2
    exit 1
  fi
done

install -d -m 700 /etc/birdmonitor/backups
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
for unit in birdmonitor.service birdstream.service birdmonitor-stream-supervisor.service; do
  if [[ -f "/etc/systemd/system/$unit" ]]; then
    install -m 600 "/etc/systemd/system/$unit" "/etc/birdmonitor/backups/${unit}.${STAMP}"
  fi
done

cat >/etc/systemd/system/birdmonitor.service <<EOF
[Unit]
Description=BirdMonitor Edge Node - captura y analisis BirdNET
Wants=network-online.target
After=network-online.target sound.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$NODE_DIR
EnvironmentFile=/etc/birdmonitor/birdmonitor.env
Environment=HOME=$SERVICE_HOME
Environment=PYTHONUNBUFFERED=1
Environment=MPLBACKEND=Agg
UMask=0077
ExecStart=$PYTHON_BIN $NODE_DIR/mainNode.py
Restart=always
RestartSec=20

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/birdstream.service <<EOF
[Unit]
Description=BirdMonitor - publicacion de audio RTSP
Wants=network-online.target
After=network-online.target sound.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
Environment=HOME=$SERVICE_HOME
EnvironmentFile=/etc/birdmonitor/stream-publisher.env
UMask=0077
ExecStart=/usr/bin/ffmpeg -hide_banner -nostdin -loglevel warning -fflags +genpts -use_wallclock_as_timestamps 1 -f alsa -thread_queue_size 2048 -channels 1 -sample_rate 48000 -i $ALSA_DEVICE -vn -af aresample=async=1000:first_pts=0 -c:a aac -b:a 96k -ar 48000 -ac 1 -f rtsp -rtsp_transport tcp \${BIRDMONITOR_STREAM_PUBLISH_URL}
Restart=always
RestartSec=10
TimeoutStopSec=5
KillMode=control-group

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/birdmonitor-stream-supervisor.service <<EOF
[Unit]
Description=BirdMonitor - supervisor del streaming
Wants=network-online.target
After=network-online.target birdmonitor.service

[Service]
Type=simple
User=root
WorkingDirectory=$NODE_DIR
EnvironmentFile=/etc/birdmonitor/birdmonitor.env
Environment=PYTHONUNBUFFERED=1
ExecStart=$PYTHON_BIN $NODE_DIR/supervisor.py
Restart=always
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

chmod 644 /etc/systemd/system/birdmonitor.service
chmod 644 /etc/systemd/system/birdstream.service
chmod 644 /etc/systemd/system/birdmonitor-stream-supervisor.service
systemctl daemon-reload
systemctl enable --now birdmonitor.service birdmonitor-stream-supervisor.service

if [[ -f /etc/birdmonitor/stream-publisher.env ]]; then
  systemctl enable --now birdstream.service
  echo "birdstream.service habilitado con la credencial existente."
else
  echo "birdstream.service instalado pero pendiente de configurar la credencial RTSP."
fi

echo "Servicios BirdMonitor instalados."
systemctl --no-pager --full status birdmonitor.service birdmonitor-stream-supervisor.service || true
