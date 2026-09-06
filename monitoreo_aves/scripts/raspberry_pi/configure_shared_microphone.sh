#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Uso: sudo ./scripts/raspberry_pi/configure_shared_microphone.sh --card NUM [--device NUM]

Configura un PCM ALSA "micshared" con dsnoop para que BirdNET y FFmpeg puedan
leer simultaneamente el mismo microfono USB. Se crea una copia de seguridad de
/etc/asound.conf antes de modificarlo.
EOF
}

CARD=""
DEVICE="0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --card)
      CARD="${2:-}"
      shift 2
      ;;
    --device)
      DEVICE="${2:-}"
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
  echo "Ejecuta este script con sudo." >&2
  exit 1
fi
if [[ ! "$CARD" =~ ^[0-9]+$ || ! "$DEVICE" =~ ^[0-9]+$ ]]; then
  echo "--card y --device deben ser numeros de ALSA." >&2
  exit 2
fi
if ! command -v arecord >/dev/null 2>&1; then
  echo "No se encuentra arecord. Instala alsa-utils." >&2
  exit 1
fi
if ! arecord -l 2>/dev/null | grep -Eq "card ${CARD}:"; then
  echo "ALSA no muestra la tarjeta ${CARD}. Ejecuta arecord -l y revisa el numero." >&2
  exit 1
fi

install -d -m 700 /etc/birdmonitor/backups
ORIGINAL_EXISTS=0
BACKUP=""
if [[ -f /etc/asound.conf ]]; then
  ORIGINAL_EXISTS=1
  BACKUP="/etc/birdmonitor/backups/asound.conf.$(date -u +%Y%m%dT%H%M%SZ)"
  install -m 600 /etc/asound.conf "$BACKUP"
  echo "Copia de seguridad: $BACKUP"
fi

TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT
cat >"$TMP_FILE" <<EOF
# Generado por BirdMonitor. Captura compartida para BirdNET y FFmpeg.
pcm.micshared {
    type dsnoop
    ipc_key 2048
    ipc_key_add_uid true
    ipc_perm 0600
    slave {
        pcm "hw:${CARD},${DEVICE}"
        channels 1
        rate 48000
        format S16_LE
        period_size 1024
        buffer_size 8192
    }
}

pcm.!default {
    type plug
    slave.pcm "micshared"
}

ctl.!default {
    type hw
    card ${CARD}
}
EOF
install -m 644 "$TMP_FILE" /etc/asound.conf

echo "Validando una captura de un segundo..."
if ! arecord -q -D plug:micshared -f S16_LE -r 48000 -c 1 -d 1 /dev/null; then
  if [[ "$ORIGINAL_EXISTS" -eq 1 ]]; then
    install -m 644 "$BACKUP" /etc/asound.conf
    echo "La validacion fallo; se ha restaurado /etc/asound.conf." >&2
  else
    rm -f /etc/asound.conf
    echo "La validacion fallo; se ha retirado la configuracion no valida." >&2
  fi
  exit 1
fi

echo "PCM micshared configurado para hw:${CARD},${DEVICE}."
echo "Deja BIRDMONITOR_MIC_DEVICE vacio para que PortAudio use el PCM por defecto."
