#!/usr/bin/env bash
set -euo pipefail
umask 077
# Usage: sudo bash install_independent_stream.sh BUNDLE USER PYTHON MEDIAMTX
[[ "$EUID" -eq 0 ]] || { echo "Ejecuta con sudo" >&2; exit 1; }
BUNDLE="$(realpath "${1:?Falta directorio de configuracion}")"
SERVICE_USER="${2:-pi}"
PYTHON_BIN="$(realpath "${3:?Falta Python del nodo}")"
MTX_BIN="$(realpath "${4:?Falta binario MediaMTX verificado}")"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE_HOME="$(getent passwd "$SERVICE_USER" | cut -d: -f6)"
SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
for value in "$ROOT" "$PYTHON_BIN" "$MTX_BIN" "$SERVICE_HOME"; do
  [[ "$value" != *[[:space:]]* ]] || { echo "Rutas con espacios no admitidas" >&2; exit 1; }
done
[[ -x "$MTX_BIN" && -x "$PYTHON_BIN" && -d "$SERVICE_HOME" ]]
[[ -f "$BUNDLE/source.env" && -f "$BUNDLE/mediamtx-source.yml" ]]
command -v ffmpeg >/dev/null
command -v arecord >/dev/null
# Validate Python before touching existing services.
"$PYTHON_BIN" -m py_compile "$ROOT/hardware/raspberry_pi/node/stream_source.py"
install -d -m 755 /usr/local/lib/birdmonitor
install -m 755 "$MTX_BIN" /usr/local/lib/birdmonitor/mediamtx
MTX_BIN=/usr/local/lib/birdmonitor/mediamtx
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/etc/birdmonitor/backups/independent-$STAMP"
install -d -m 700 "$BACKUP"
for unit in birdstream.service birdmonitor-stream-supervisor.service birdstream-source.service birdstream-origin.service; do
  systemctl is-enabled "$unit" >"$BACKUP/$unit.enabled" 2>/dev/null || true
  systemctl is-active "$unit" >"$BACKUP/$unit.active" 2>/dev/null || true
  [[ ! -f "/etc/systemd/system/$unit" ]] || cp -a "/etc/systemd/system/$unit" "$BACKUP/"
done
rollback() {
  trap - ERR
  systemctl disable --now birdstream-source.service birdstream-origin.service || true
  for unit in birdstream.service birdmonitor-stream-supervisor.service birdstream-source.service birdstream-origin.service; do
    if [[ -f "$BACKUP/$unit" ]]; then
      cp -a "$BACKUP/$unit" "/etc/systemd/system/$unit"
    elif [[ "$unit" == birdstream-source.service || "$unit" == birdstream-origin.service ]]; then
      rm -f "/etc/systemd/system/$unit"
    fi
  done
  for file in source.env mediamtx-source.yml; do
    if [[ -f "$BACKUP/$file" ]]; then cp -a "$BACKUP/$file" "/etc/birdmonitor/$file"; fi
  done
  systemctl daemon-reload
  for unit in birdstream.service birdmonitor-stream-supervisor.service birdstream-source.service birdstream-origin.service; do
    if grep -qx enabled "$BACKUP/$unit.enabled"; then systemctl enable "$unit" || true; fi
    if grep -qx active "$BACKUP/$unit.active"; then systemctl restart "$unit" || true; fi
  done
  echo "Instalacion fallida; se ha intentado restaurar el estado anterior. Copia: $BACKUP" >&2
}
# Save configuration before installing it, so partial writes can be rolled back.
for file in source.env mediamtx-source.yml; do
  [[ ! -f "/etc/birdmonitor/$file" ]] || cp -a "/etc/birdmonitor/$file" "$BACKUP/"
done
trap rollback ERR
for file in source.env mediamtx-source.yml; do
  [[ ! -f "/etc/birdmonitor/$file" ]] || cp -a "/etc/birdmonitor/$file" "$BACKUP/"
  install -m 600 "$BUNDLE/$file" "/etc/birdmonitor/$file"
done
cat >/etc/systemd/system/birdstream-origin.service <<EOF
[Unit]
Description=BirdMonitor independent RTSP origin
After=network-online.target tailscaled.service
Wants=network-online.target
StartLimitIntervalSec=0
[Service]
DynamicUser=true
LoadCredential=mediamtx.yml:/etc/birdmonitor/mediamtx-source.yml
ExecStart=$MTX_BIN %d/mediamtx.yml
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
EOF
cat >/etc/systemd/system/birdstream-source.service <<EOF
[Unit]
Description=BirdMonitor bounded USB publisher
After=birdstream-origin.service sound.target
Wants=birdstream-origin.service
StartLimitIntervalSec=0
[Service]
User=$SERVICE_USER
Group=$SERVICE_GROUP
Environment=HOME=$SERVICE_HOME
EnvironmentFile=/etc/birdmonitor/source.env
ExecStart=$PYTHON_BIN $ROOT/hardware/raspberry_pi/node/stream_source.py
Restart=always
RestartSec=5
KillMode=control-group
TimeoutStopSec=5
NoNewPrivileges=true
UMask=0077
[Install]
WantedBy=multi-user.target
EOF
systemd-analyze verify /etc/systemd/system/birdstream-origin.service /etc/systemd/system/birdstream-source.service
# The legacy supervisor must not control the independent origin.
systemctl disable --now birdmonitor-stream-supervisor.service birdstream.service
systemctl daemon-reload
systemctl enable --now birdstream-origin.service birdstream-source.service
sleep 3
systemctl --no-pager status birdstream-origin.service birdstream-source.service
trap - ERR
printf 'Copia de recuperacion: %s\n' "$BACKUP"
