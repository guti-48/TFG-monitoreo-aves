# Nodo Raspberry Pi de BirdMonitor

Esta carpeta contiene el nodo *edge*: graba el micrófono, ejecuta BirdNET en
local, conserva una cola si el servidor no responde y publica el audio en
directo. Los WAV no se envían a servicios de IA externos.

## Procesos instalados

| Unidad | Función |
|---|---|
| `birdmonitor.service` | Captura, análisis BirdNET, evidencias y sincronización |
| `birdstream.service` | Publicación RTSP autenticada mediante FFmpeg |
| `birdmonitor-stream-supervisor.service` | Aplica el botón de emisión y recupera el directo |

`mainNode.py` realiza el análisis, `supervisor.py` controla el streaming,
`node_sync.py` mantiene la cola persistente y `configure_site.py` activa el
sitio/despliegue. `deployment_state.json` se genera localmente y no se debe
editar ni versionar.

## Requisitos

- Raspberry Pi OS de 64 bits y Python compatible con TensorFlow/BirdNET.
- `ffmpeg`, `alsa-utils`, `libportaudio2` y `libsndfile1`.
- Micrófono visible en `arecord -l`.
- Servidor BirdMonitor ya configurado para modo `local` o `tailscale`.
- Token de nodo y contraseña RTSP de publicación generados por el servidor.

Los comandos siguientes suponen un clon en `/home/pi/birdmonitor`.

## 1. Instalar software

```bash
sudo apt update
sudo apt install -y ffmpeg alsa-utils libportaudio2 libsndfile1 python3-venv

cd /home/pi/birdmonitor
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements-node.txt
```

Comprueba antes que la versión de TensorFlow indicada por el sistema es
compatible con la arquitectura de la Raspberry.

## 2. Crear el entorno privado

```bash
sudo install -d -m 700 /etc/birdmonitor
sudo install -m 600 \
  /home/pi/birdmonitor/hardware/raspberry_pi/birdmonitor.env.example \
  /etc/birdmonitor/birdmonitor.env
sudo nano /etc/birdmonitor/birdmonitor.env
```

Completa al menos:

```dotenv
BIRDMONITOR_NETWORK_MODE=tailscale
BIRDMONITOR_SERVER_URL=http://IP_PRIVADA_DEL_SERVIDOR:8000
BIRDMONITOR_NODE_API_TOKEN=TOKEN_GENERADO_EN_EL_SERVIDOR
BIRDMONITOR_NODE_NAME=birdmonitor-01

BIRDMONITOR_MIC_ALSA_CARD=3
BIRDMONITOR_MIC_CAPTURE_VOLUME=50%
BIRDMONITOR_MIC_AUTO_GAIN=0
```

No copies valores reales a Git, capturas o documentos públicos.

## 3. Configurar sitio y campaña

Primero valida sin modificar el estado:

```bash
sudo /home/pi/birdmonitor/venv/bin/python \
  /home/pi/birdmonitor/hardware/raspberry_pi/configure_site.py \
  --site-code codigo-del-sitio \
  --site-name "Nombre legible" \
  --municipality "Municipio" \
  --region "Provincia o región" \
  --country-code ES \
  --timezone Europe/Madrid \
  --location-source manual \
  --lat LATITUD \
  --lon LONGITUD \
  --accuracy-m 50 \
  --new-deployment \
  --dry-run
```

Repite sin `--dry-run` cuando sea correcto. Al mover la caja no se borra la
base central: cada campaña queda separada por `site_code` y `deployment_id`.

## 4. Compartir el micrófono

BirdNET y el directo leen el mismo dispositivo. ALSA `dsnoop` evita que un
proceso bloquee al otro y reduce los cortes producidos por competir por el USB.
Sustituye `3` por la tarjeta mostrada en `arecord -l`:

```bash
cd /home/pi/birdmonitor
sudo bash scripts/raspberry_pi/configure_shared_microphone.sh --card 3
```

El script prueba una captura y, si falla, restaura automáticamente
`/etc/asound.conf`. Deja `BIRDMONITOR_MIC_DEVICE` vacío para usar el PCM por
defecto.

## 5. Instalar los servicios

```bash
sudo bash scripts/raspberry_pi/install_birdmonitor_services.sh \
  --user pi \
  --python /home/pi/birdmonitor/venv/bin/python
```

Las unidades se crean sin secretos embebidos, se habilitan al arranque y se
reinician si terminan de forma inesperada. Una unidad anterior se copia a
`/etc/birdmonitor/backups/`.

## 6. Autorizar la publicación RTSP

Usa el mismo modo y la IP configurados en el servidor:

```bash
sudo /home/pi/birdmonitor/venv/bin/python \
  /home/pi/birdmonitor/scripts/raspberry_pi/configure_stream_publisher.py \
  --network-mode tailscale \
  --server-host IP_TAILSCALE_DEL_SERVIDOR
```

En una LAN privada usa `--network-mode local` y la IPv4 local del servidor.
La contraseña se solicita sin mostrarla y queda en
`/etc/birdmonitor/stream-publisher.env` con permisos `600`. El configurador
habilita `birdstream.service` para los siguientes reinicios.

## 7. Validar

```bash
sudo systemctl is-active birdmonitor.service
sudo systemctl is-active birdstream.service
sudo systemctl is-active birdmonitor-stream-supervisor.service

sudo systemctl status \
  birdmonitor.service \
  birdstream.service \
  birdmonitor-stream-supervisor.service --no-pager
```

Las tres unidades deben indicar `active`. En modo Tailscale verifica también:

```bash
sudo systemctl is-active tailscaled.service
tailscale ping IP_TAILSCALE_DEL_SERVIDOR
```

## Operación y diagnóstico

```bash
# Análisis BirdNET
sudo journalctl -u birdmonitor.service -n 100 --no-pager

# Audio en directo
sudo journalctl -u birdstream.service -n 100 --no-pager

# Órdenes del dashboard y recuperación del directo
sudo journalctl -u birdmonitor-stream-supervisor.service -n 100 --no-pager
```

| Problema | Comprobación |
|---|---|
| El análisis se reinicia | Token, entorno Python, entrada ALSA y primer log |
| El directo se corta | Estado de `birdstream`, conectividad y `micshared` |
| FFmpeg sale con código 8 | Credencial RTSP, URL del servidor y entrada ALSA |
| El nodo no sincroniza | `BIRDMONITOR_SERVER_URL`, token y `/health` |
| No cambia de ubicación | Orden pendiente, permisos del estado y log del nodo |

Reiniciar `birdmonitor.service` no debería detener el directo, ya que son
procesos independientes. Si se expone una credencial RTSP, rótala desde el
servidor y repite únicamente el paso 6.

## Calidad y retención

| Variable | Inicio recomendado | Efecto |
|---|---:|---|
| `BIRDMONITOR_RECORD_SECONDS` | `60` | Duración de cada WAV |
| `BIRDMONITOR_RECORD_INTERVAL_SECONDS` | `300` | Descanso y carga del nodo |
| `BIRDMONITOR_BIRD_CONFIDENCE_THRESHOLD` | `0.65` | Umbral que debe calibrarse localmente |
| `BIRDMONITOR_BIRDNET_OVERLAP_SECONDS` | `1.5` | Reduce pérdidas entre ventanas |
| `BIRDMONITOR_BIRDNET_SENSITIVITY` | `1.25` | Sensibilidad reproducible |
| `BIRDMONITOR_RETENTION_DAYS` | `9` | Retención de medios locales |

Primero ajusta la ganancia física/ALSA. El filtrado no recupera una señal
recortada y amplificar una señal débil también amplifica el ruido.

Volver al [README principal](../../README.md).
