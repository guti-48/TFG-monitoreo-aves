# Nodo edge de BirdMonitor

Esta carpeta contiene el software que se ejecuta en la Raspberry Pi. El nodo captura audio, analiza BirdNET localmente, calcula métricas, conserva una cola cuando el servidor no responde y publica el directo mediante FFmpeg.

## Procesos del nodo

| Archivo o servicio | Responsabilidad |
|---|---|
| `mainNode.py` / `birdmonitor.service` | Captura, análisis, evidencias, sincronización y BirdWeather opcional |
| `supervisor.py` | Sincroniza el estado deseado del directo y recupera `birdstream.service` si deja de publicar |
| `birdstream.service` | Captura la entrada ALSA y publica RTSP autenticado en MediaMTX |
| `node_sync.py` | Cola SQLite persistente e idempotencia de envíos |
| `configure_site.py` | Crea o activa de forma atómica el contexto de sitio/despliegue |
| `deployment_state.json` | Estado operativo local generado; no editar ni versionar |

## Requisitos previos

- Raspberry Pi OS con red operativa.
- Python y un entorno virtual compatible con BirdNET/birdnetlib.
- FFmpeg y ALSA instalados.
- Micrófono visible en `arecord -l`.
- Servicios base `birdmonitor.service` y `birdstream.service` creados.
- Token de nodo y credencial de publicación generados previamente en el servidor.
- `tailscaled.service` activo si se usa el modo `tailscale`.

El configurador RTSP **protege una unidad `birdstream.service` existente**; no crea desde cero la ruta ALSA ni instala BirdNET.

## 1. Instalar la configuración privada

En el ejemplo, el repositorio está en `/home/pi/birdmonitor/monitoreo_aves`:

```bash
sudo install -d -m 700 /etc/birdmonitor
sudo cp \
  /home/pi/birdmonitor/monitoreo_aves/hardware/raspberry_pi/birdmonitor.env.example \
  /etc/birdmonitor/birdmonitor.env
sudo chmod 600 /etc/birdmonitor/birdmonitor.env
sudo nano /etc/birdmonitor/birdmonitor.env
```

Completa, como mínimo:

```dotenv
BIRDMONITOR_NETWORK_MODE=tailscale
BIRDMONITOR_SERVER_URL=http://IP_PRIVADA_DEL_SERVIDOR:8000
BIRDMONITOR_NODE_API_TOKEN=TOKEN_GENERADO_EN_EL_SERVIDOR
BIRDMONITOR_NODE_NAME=birdmonitor-01

BIRDMONITOR_MIC_ALSA_CARD=3
BIRDMONITOR_MIC_CAPTURE_VOLUME=50%
BIRDMONITOR_MIC_AUTO_GAIN=0
```

No copies valores reales a Git, capturas o documentos públicos. Comprueba que `birdmonitor.service` contiene:

```ini
[Service]
EnvironmentFile=/etc/birdmonitor/birdmonitor.env
```

## 2. Crear el primer despliegue

Primero valida sin escribir:

```bash
sudo python3 \
  /home/pi/birdmonitor/monitoreo_aves/hardware/raspberry_pi/configure_site.py \
  --site-code codigo-del-sitio \
  --site-name "Nombre legible del sitio" \
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

Repite el comando sin `--dry-run` cuando los datos sean correctos. El script genera un UUID para la campaña, conserva los secretos del archivo y crea una copia previa bajo `/etc/birdmonitor/backups/`.

> No borres la base central al mover la caja. Cada nuevo despliegue separa las observaciones mediante `site_code` y `deployment_id`; los sitios históricos siguen disponibles en el dashboard.

## 3. Proteger la publicación de audio

Usa el mismo modo y la misma IP configurados en el servidor:

```bash
cd /home/pi/birdmonitor/monitoreo_aves
sudo python3 scripts/raspberry_pi/configure_stream_publisher.py \
  --network-mode tailscale \
  --server-host IP_TAILSCALE_DEL_SERVIDOR
```

La contraseña se solicita de forma interactiva. El resultado queda en `/etc/birdmonitor/stream-publisher.env` con permisos `600`; la unidad utiliza `${BIRDMONITOR_STREAM_PUBLISH_URL}` en vez de contener el secreto.

Para red local cambia `tailscale` por `local` y usa la IPv4 LAN del servidor.

## 4. Arrancar y validar

```bash
sudo systemctl daemon-reload
sudo systemctl restart birdmonitor.service
sudo systemctl restart birdstream.service

sudo systemctl is-active birdmonitor.service
sudo systemctl is-active birdstream.service
sudo systemctl is-active tailscaled.service
```

Los dos primeros deben devolver `active`; el tercero sólo es obligatorio en modo Tailscale.

```bash
sudo systemctl show birdmonitor.service \
  -p ActiveState -p SubState -p NRestarts -p ExecMainStatus
sudo systemctl show birdstream.service \
  -p ActiveState -p SubState -p NRestarts -p ExecMainStatus
```

Comprueba después en el servidor que `/health` responde, el nodo aparece en el dashboard y una nueva captura conserva el sitio/despliegue activo.

## 5. Operación habitual

```bash
# Estado resumido
sudo systemctl status birdmonitor.service birdstream.service --no-pager

# Últimos eventos del análisis
sudo journalctl -u birdmonitor.service -n 100 --no-pager

# Diagnóstico del directo
sudo journalctl -u birdstream.service -n 100 --no-pager

# Reinicio controlado del análisis
sudo systemctl restart birdmonitor.service
```

El directo y BirdNET son procesos distintos. Reiniciar `birdmonitor.service` no debería cerrar la publicación de `birdstream.service`.

## Cambio de ubicación desde el dashboard

1. Inicia sesión y elige el sitio físico donde se instalará la Raspberry.
2. Confirma la orden administrativa.
3. El nodo la consulta con su token y la aplica entre dos ciclos.
4. `deployment_state.json` se reemplaza atómicamente y el servidor recibe la confirmación.
5. BirdNET y BirdWeather recargan las nuevas coordenadas.

Si no hay red, la orden permanece pendiente. No asignes observaciones a un sitio futuro de forma retroactiva.

## Captura y calidad

| Variable | Valor inicial recomendado | Nota |
|---|---:|---|
| `BIRDMONITOR_RECORD_SECONDS` | `60` | Duración del WAV |
| `BIRDMONITOR_RECORD_INTERVAL_SECONDS` | `300` | Evita una carga continua innecesaria |
| `BIRDMONITOR_BIRD_CONFIDENCE_THRESHOLD` | `0.65` | Debe calibrarse con datos locales revisados |
| `BIRDMONITOR_BIRDNET_OVERLAP_SECONDS` | `1.5` | Reduce pérdidas en límites de ventana a cambio de más cómputo |
| `BIRDMONITOR_BIRDNET_SENSITIVITY` | `1.25` | Sensibilidad reproducible del análisis |
| `BIRDMONITOR_RETENTION_DAYS` | `9` | Limpieza local de medios antiguos |

La ganancia debe fijarse en hardware/ALSA antes de evaluar filtros. Una señal con clipping no se puede recuperar, y amplificar digitalmente una grabación débil amplifica también el ruido.

## Cola offline y archivos

- Las detecciones pendientes se conservan localmente y se reintentan sin crear duplicados.
- Cada elemento guarda una instantánea del sitio y despliegue vigentes al capturarse.
- Los WAV y espectrogramas se eliminan según la retención configurada cuando ya no son necesarios.
- `deployment_state.json`, la cola local, `records/`, `spectrograms/` y los archivos de `/etc/birdmonitor/` no deben versionarse.

## Diagnóstico rápido

| Problema | Acción |
|---|---|
| `birdmonitor.service` reinicia | Revisar token, dispositivo de entrada, entorno Python y `journalctl` |
| `birdstream.service` devuelve código 8 | Verificar entrada ALSA y repetir `configure_stream_publisher.py` con la credencial vigente |
| El nodo no llega al backend | Comprobar `BIRDMONITOR_SERVER_URL`, Tailscale/LAN y `/health` desde la Raspberry |
| El sitio del dashboard no cambia | Comprobar que el servicio puede escribir `deployment_state.json` y revisar la orden pendiente |
| Hay zumbido o ruido grave | Separar alimentación USB, evitar contacto rígido con la caja, fijar ganancia y revisar varias muestras |

Volver al [README principal](../../README.md).
