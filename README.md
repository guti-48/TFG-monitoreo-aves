# Sistema IoT de Monitoreo Acústico de Aves (TFG)

Este repositorio contiene un sistema distribuido para la detección, clasificación y monitorización de avifauna mediante análisis acústico pasivo e inteligencia artificial. El proyecto combina un nodo Edge basado en Raspberry Pi, un backend FastAPI y un dashboard web para visualizar detecciones, métricas acústicas y análisis ecológicos.

La arquitectura está pensada para funcionar en escenarios de campo: el nodo graba audio, calcula métricas locales, ejecuta BirdNET, genera espectrogramas, conserva datos si no hay conexión y sincroniza las detecciones cuando recupera acceso al servidor central.

## Estado Del Proyecto

El sistema se encuentra en fase de validación técnica con flujo completo de extremo a extremo:

- Captura de audio en Raspberry Pi.
- Inferencia local con BirdNET.
- Registro automático de dispositivos.
- Envío de detecciones y métricas acústicas al backend.
- Subida de archivos `.wav` y espectrogramas `.png`.
- Persistencia en SQLite.
- Dashboard web servido desde FastAPI.
- Control remoto de streaming HLS mediante el panel web.

## Funcionalidades Principales

### Nodo Edge

- Grabación mono a `48 kHz` en ciclos configurados de `60 s` cada `5 min`.
- Selección automática o manual del micrófono mediante `sounddevice`.
- Generación de archivos WAV y espectrogramas Mel.
- Cálculo de amplitud RMS para estimar nivel de ruido ambiental.
- Cálculo de índices acústicos con `scikit-maad`: `ACI`, `ADI`, `AEI`, `BIO`, `NDSI`, `Ht`, `Hf` y `H`.
- Inferencia con BirdNET mediante `birdnetlib`.
- Filtrado por umbrales diferenciados para aves, humanos, motores y ruido ambiente.
- Geolocalización manual, por IP pública o por caché local.
- Envío opcional de detecciones de aves a BirdWeather.
- Respaldo offline en CSV y resincronización posterior.
- Limpieza automática de audios e imágenes antiguos para limitar el uso de disco.
- Protección ante relojes no sincronizados, evitando datos con fechas inválidas tras cortes de energía.

### Backend

- API REST con FastAPI.
- Base de datos SQLite gestionada con SQLAlchemy.
- Validación de datos con Pydantic.
- Recepción segura de uploads `.wav` y `.png`, con validación de extensión, nombre y tamaño.
- Almacenamiento de detecciones biológicas o acústicas relevantes.
- Almacenamiento independiente de métricas acústicas por ciclo, incluso cuando no hay detección de ave.
- Endpoints de analítica para biodiversidad, mapa e informe diario.
- Servicio de archivos estáticos para el dashboard y espectrogramas.
- Control remoto del estado deseado y real del streaming HLS.

### Dashboard Web

- Interfaz SPA en HTML, CSS y JavaScript.
- Bootstrap 5, Bootstrap Icons, Chart.js, Leaflet y HLS.js.
- Vista de tiempo real con detecciones recientes.
- Vista de escucha en directo con activación y parada del servicio `birdstream.service`.
- Histórico de detecciones.
- Panel de análisis ecológico con índices de biodiversidad.
- Visualización de nodos registrados.
- Informe diario por fecha con curva de actividad por horas.
- Mapa con datos agregados por ubicación.

## Arquitectura

```text
TFG-monitoreo-aves/
├── README.md
└── monitoreo_aves/
    ├── README.md
    ├── requirements.txt
    ├── backend/
    │   ├── analisisBiodiversidad.py
    │   ├── comparativa_biodiversidad.png
    │   └── app/
    │       ├── main.py
    │       ├── models.py
    │       ├── schemas.py
    │       ├── database.py
    │       ├── birdmonitor.db
    │       └── stream_control.json
    ├── frontend/
    │   ├── index.html
    │   ├── css/
    │   │   └── style.css
    │   ├── js/
    │   │   └── dashboard.js
    │   └── assets/
    │       └── placeholder.jpg
    └── hardware/
        └── raspberry_pi/
            ├── mainNode.py
            ├── analyzer.py
            ├── supervisor.py
            ├── backup_data.csv
            ├── model/
            │   ├── birdnet_model.tflite
            │   └── birdnet_labels.txt
            ├── records/
            └── spectrograms/
```

## Componentes

### 1. Nodo Sensor

Ruta: `monitoreo_aves/hardware/raspberry_pi/`

El nodo se ejecuta en Raspberry Pi OS y se encarga de digitalizar el entorno acústico. El flujo principal está en `mainNode.py`:

1. Registra el dispositivo en el servidor.
2. Detecta el micrófono disponible.
3. Graba audio durante el intervalo configurado.
4. Guarda el WAV y genera el espectrograma.
5. Calcula métricas acústicas del paisaje sonoro.
6. Ejecuta BirdNET.
7. Filtra detecciones por umbrales.
8. Envía detecciones, métricas y archivos al backend.
9. Guarda respaldo local si el servidor no está disponible.

`analyzer.py` encapsula el uso de BirdNET. `supervisor.py` controla el servicio de streaming consultando periódicamente el backend.

### 2. Servidor Central

Ruta: `monitoreo_aves/backend/`

El backend expone la API REST, genera la base de datos si no existe y sirve el dashboard desde la carpeta `frontend`. La base de datos se guarda en `monitoreo_aves/backend/app/birdmonitor.db`.

Tablas principales:

- `devices`: nodos registrados.
- `detections`: detecciones de aves, humanos, motores o ruido relevante.
- `audio_metrics`: métricas acústicas agregadas por ciclo de grabación.

### 3. Frontend

Ruta: `monitoreo_aves/frontend/`

El frontend no necesita servidor propio en el despliegue actual. FastAPI monta `frontend/index.html` y sus archivos estáticos en `/`, por lo que el dashboard queda disponible en el mismo puerto que la API.

## Endpoints Principales

| Método | Ruta | Descripción |
| --- | --- | --- |
| `POST` | `/devices/` | Registra o actualiza un nodo. |
| `GET` | `/devices/` | Lista dispositivos registrados. |
| `POST` | `/detections/` | Guarda una detección. |
| `GET` | `/detections/` | Devuelve detecciones recientes. |
| `POST` | `/audio-metrics/` | Guarda métricas acústicas de un ciclo. |
| `GET` | `/audio-metrics/` | Lista métricas acústicas recientes. |
| `POST` | `/upload/` | Sube WAV y/o espectrograma PNG. |
| `GET` | `/analytics/biodiversity` | Devuelve índices ecológicos y acústicos. |
| `GET` | `/analytics/map` | Devuelve datos para el mapa. |
| `GET` | `/analytics/daily-activity` | Devuelve actividad diaria por horas. |
| `GET` | `/stream/control` | Consulta estado deseado y real del streaming. |
| `POST` | `/stream/control` | Activa o desactiva el streaming desde el dashboard. |
| `POST` | `/stream/status` | Recibe estado real reportado por la Raspberry Pi. |

## Instalación

Desde la raíz del repositorio:

```bash
cd monitoreo_aves
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

En Windows PowerShell:

```bash
cd monitoreo_aves
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

En Windows con Git Bash:

```bash
cd monitoreo_aves
python -m venv venv
source ./venv/Scripts/activate
pip install -r requirements.txt
```

## Ejecución Del Servidor

Desde `monitoreo_aves/`:

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Accesos:

```text
Dashboard local: http://localhost:8000
API docs:        http://localhost:8000/docs
```

En el despliegue usado por el proyecto, el servidor Windows queda accesible para la Raspberry Pi mediante Tailscale:

```text
http://100.98.248.58:8000
```

La base de datos SQLite se crea automáticamente si no existe. Solo conviene eliminar `backend/app/birdmonitor.db` cuando se quiera reiniciar completamente el histórico de pruebas.

## Ejecución Del Nodo Edge

En Raspberry Pi:

```bash
cd ~/birdmonitor/monitoreo_aves/hardware/raspberry_pi
source ~/birdmonitor/birdnet-env/bin/activate
python mainNode.py
```

Variables de entorno útiles:

```bash
export BIRDMONITOR_NODE_NAME="birdmonitor"
export BIRDMONITOR_SERVER_URL="http://100.98.248.58:8000"
export BIRDMONITOR_NODE_LOCATION="Sevilla, Andalucía, España"
export BIRDMONITOR_NODE_LAT="37.3891"
export BIRDMONITOR_NODE_LON="-5.9845"
export BIRDMONITOR_MIC_DEVICE="1"
export BIRDWEATHER_ID="token-opcional"
```

Si no se define ubicación manual, el nodo intenta geolocalizarse por IP pública y guarda una caché local en `node_location_cache.json`.

## Servicio Systemd Del Nodo

En despliegue real, el nodo puede ejecutarse como servicio:

```bash
sudo systemctl start birdmonitor.service
sudo systemctl status birdmonitor.service
journalctl -u birdmonitor.service -f
```

Para la escucha en directo, `supervisor.py` consulta el backend y arranca o detiene el servicio configurado en `BIRDMONITOR_STREAM_SERVICE`, por defecto:

```text
birdstream.service
```

Comandos habituales:

```bash
sudo systemctl start birdstream.service
sudo systemctl stop birdstream.service
sudo systemctl status birdstream.service
```

## Configuración Del Streaming

El backend usa estas variables para construir las URLs HLS que muestra el dashboard:

```bash
export BIRDMONITOR_STREAM_BASE_URL="http://100.98.248.58:8888"
export BIRDMONITOR_STREAM_PATH="birdmonitor-audio"
```

El estado del streaming se persiste en:

```text
monitoreo_aves/backend/app/stream_control.json
```

## Acceso Remoto Al Nodo

Para administrar la Raspberry Pi en modo headless:

```bash
ssh usuario@IP_DE_LA_RASPBERRY
```

Si se usa Tailscale, puede emplearse la IP virtual asignada al nodo. Desde SSH se pueden revisar logs, actualizar código, reiniciar servicios o comprobar el estado del micrófono.

## Notas De Desarrollo

- El frontend está integrado en FastAPI; no es necesario ejecutar `python -m http.server` para el dashboard actual.
- Los endpoints del frontend contienen algunas referencias directas a la IP de Tailscale usada en el despliegue. Si cambia el servidor, conviene actualizar `frontend/js/dashboard.js` o sustituirlas por rutas relativas.
- `records/` y `spectrograms/` contienen datos generados por el nodo. En producción deben tratarse como almacenamiento temporal.
- El modelo BirdNET y sus etiquetas están en `hardware/raspberry_pi/model/`.

## Dependencias Principales

- `fastapi`
- `uvicorn`
- `sqlalchemy`
- `pydantic`
- `numpy`
- `scipy`
- `pandas`
- `matplotlib`
- `librosa`
- `sounddevice`
- `soundfile`
- `tensorflow`
- `birdnetlib`
- `scikit-maad`
- `python-multipart`
- `geocoder`
