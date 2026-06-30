# Sistema IoT de Monitoreo Acústico de Aves (TFG)

Este proyecto consiste en el diseño, desarrollo e implementación de un sistema distribuido para la detección, clasificación y monitoreo de avifauna mediante análisis acústico pasivo (PAM) e Inteligencia Artificial.

El sistema utiliza nodos de computación en el borde (Edge Computing) basados en Raspberry Pi para procesar audio en tiempo real, implementando una arquitectura híbrida que permite el almacenamiento local de datos científicos (incluyendo análisis de contaminación acústica) y la contribución simultánea a redes de ciencia ciudadana (BirdWeather).

## Guia de instalacion y configuracion

El proyecto queda preparado para clonarse y ejecutarse con un servidor central en Windows o macOS. La Raspberry Pi actua como nodo Edge y debe apuntar a la IP real del servidor central, normalmente una IP LAN o una IP/hostname de Tailscale.

### Arquitectura de despliegue

```text
Raspberry Pi / nodos Edge  --->  Servidor central Windows o macOS  --->  Dashboard web / app movil
        mainNode.py                  FastAPI :8000                         http://IP_SERVIDOR:8000
        supervisor.py                MediaMTX :8888                        HLS :8888
        birdstream.service
```

Reglas importantes de red:

* `127.0.0.1` y `localhost` solo sirven desde la misma maquina.
* El servidor escucha en `0.0.0.0`; normalmente no tienes que escribir su propia IP en el backend.
* Desde la Raspberry, la app movil u otro ordenador, usa la IP LAN o Tailscale del servidor.
* Si cambias el servidor de Windows a Mac, cambia la IP en la Raspberry y en la app movil, no en todos los archivos del backend.
* Varios clientes pueden abrir el mismo dashboard a la vez: Mac, Windows, movil o tablet solo necesitan entrar a `http://IP_DEL_SERVIDOR:8000`.

### Servidor central y clientes

La Raspberry no necesita saber desde que ordenador vas a mirar el dashboard. La Raspberry solo envia datos y consulta ordenes en el **servidor central** configurado en `BIRDMONITOR_SERVER_URL`.

Ejemplos:

```text
Raspberry -> http://100.80.10.25:8000      # servidor central por Tailscale
Mac       -> http://100.80.10.25:8000      # cliente viendo el dashboard
Windows   -> http://100.80.10.25:8000      # otro cliente viendo el mismo dashboard
Movil     -> http://100.80.10.25:8000      # app o navegador
```

Si el servidor central es el Mac, Windows tambien puede entrar al dashboard del Mac. Si el servidor central es Windows, el Mac puede entrar al dashboard de Windows. Lo importante es que todos apunten al mismo backend si quieres ver la misma base de datos y controlar la misma Raspberry.

No hace falta cambiar el codigo visual para esto. La URL se introduce en el navegador o en la pantalla de conexion de la app movil.

### 1. Clonar el repositorio

```bash
git clone https://github.com/guti-48/TFG-monitoreo-aves.git
cd TFG-monitoreo-aves/monitoreo_aves
```

En macOS se recomienda clonar o mover el repositorio fuera de `Desktop`, `Documents` o `Downloads`, porque los `LaunchAgent` pueden no tener permiso para leer esas carpetas. Una ruta recomendada es:

```bash
mkdir -p ~/Projects
cd ~/Projects
git clone https://github.com/guti-48/TFG-monitoreo-aves.git
cd TFG-monitoreo-aves/monitoreo_aves
```

### 2. Crear entorno virtual e instalar dependencias

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS o Linux:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Colocar MediaMTX

MediaMTX no debe subirse a Git como binario. Cada persona debe descargar el binario de su sistema y colocarlo en la ruta esperada:

```text
monitoreo_aves/
└── tools/
    └── mediamtx/
        ├── mediamtx.yml
        ├── mediamtx.exe              # Windows
        └── macos/
            └── mediamtx              # macOS darwin
```

El archivo `tools/mediamtx/mediamtx.yml` sí forma parte de la configuracion del proyecto. Los binarios, logs y claves generadas quedan ignorados por `.gitignore`.

Si macOS bloquea el binario descargado, se puede quitar la cuarentena localmente:

```bash
xattr -dr com.apple.quarantine tools/mediamtx/macos/mediamtx
chmod +x tools/mediamtx/macos/mediamtx
```

### 4. Donde cambiar IPs, nodos y rutas

La IP que normalmente hay que cambiar es la del servidor central vista desde cada cliente o nodo.

| Caso | Donde se configura | Que poner |
| --- | --- | --- |
| Raspberry envia detecciones al servidor | Variable `BIRDMONITOR_SERVER_URL`, usada por `hardware/raspberry_pi/mainNode.py` y `hardware/raspberry_pi/supervisor.py` | `http://IP_DEL_SERVIDOR:8000` |
| Nombre de cada Raspberry/nodo | `BIRDMONITOR_NODE_NAME` | Un nombre unico por nodo, por ejemplo `birdmonitor-norte`, `birdmonitor-sur` |
| Ubicacion del nodo | `BIRDMONITOR_NODE_LOCATION`, `BIRDMONITOR_NODE_LAT`, `BIRDMONITOR_NODE_LON` | Lugar y coordenadas reales del nodo |
| Microfono en Raspberry | `BIRDMONITOR_MIC_DEVICE` | Indice del dispositivo de entrada si no quieres usar el predeterminado |
| Servicio de streaming de la Raspberry | Archivo o servicio `birdstream.service` que publique audio hacia MediaMTX | Debe apuntar a la IP del servidor y al path HLS/MediaMTX elegido, normalmente `birdmonitor-audio` |
| Dashboard web | Normalmente no se edita: `frontend/js/dashboard.js` carga `/devices/` y permite seleccionar nodo y path MediaMTX desde la vista de directo | Si entras en `http://IP_SERVIDOR:8000`, usara `http://IP_SERVIDOR:8888` |
| Dashboard con MediaMTX en otro host/puerto | `frontend/index.html`, antes de cargar `frontend/js/dashboard.js`, definiendo `window.BIRDMONITOR_CONFIG` | `liveStreamBaseUrl`, `streamName`, `streamNodeName` |
| Backend si MediaMTX no esta en el mismo host | Variables de entorno usadas por `backend/app/main.py` | `BIRDMONITOR_STREAM_BASE_URL`, `BIRDMONITOR_STREAM_PATH` |
| App movil | Pantalla de conexion de la app | `http://IP_DEL_SERVIDOR:8000`; no usar `127.0.0.1` en un movil real |

Ejemplo para una Raspberry que apunta a un Mac por Tailscale:

```bash
export BIRDMONITOR_SERVER_URL="http://100.80.10.25:8000"
export BIRDMONITOR_NODE_NAME="birdmonitor-maceta-01"
export BIRDMONITOR_NODE_LOCATION="Sevilla"
export BIRDMONITOR_NODE_LAT="37.3891"
export BIRDMONITOR_NODE_LON="-5.9845"
```

Si usas varios dispositivos, repite la misma URL del servidor y cambia al menos `BIRDMONITOR_NODE_NAME` y la ubicacion de cada Raspberry. El backend guarda los dispositivos por nombre, separa detecciones por nodo y mantiene el estado de streaming por `node_name`.

Puedes tener Windows y macOS encendidos a la vez, pero conviene elegir uno como servidor central para que la base de datos, el dashboard y MediaMTX sean los mismos. Si arrancas dos servidores centrales independientes, cada uno tendra su propia base de datos y las Raspberry tendran que apuntar a uno u otro mediante `BIRDMONITOR_SERVER_URL`.

Para el directo HLS de varios nodos, cada stream debe tener un path distinto en MediaMTX. El backend genera por defecto `{node_name}-audio`, por ejemplo:

```text
birdmonitor-audio-norte
birdmonitor-audio-sur
```

La vista web carga los nodos registrados y permite seleccionar el nodo y el path de MediaMTX desde la pantalla de escucha en directo. Si quieres fijar un valor por defecto sin tocar `dashboard.js`, puedes definir antes de cargar el script:

```html
<script>
window.BIRDMONITOR_CONFIG = {
  liveStreamBaseUrl: "http://IP_DEL_SERVIDOR:8888",
  streamName: "birdmonitor-audio-norte",
  streamNodeName: "birdmonitor-norte"
};
</script>
```

### 5. Instalacion automatica en Windows

Requisitos:

* PowerShell abierto como administrador.
* Entorno virtual creado en `monitoreo_aves/venv`.
* Dependencias instaladas con `pip install -r requirements.txt`.
* `tools/mediamtx/mediamtx.exe` y `tools/mediamtx/mediamtx.yml` disponibles.

Instalar y arrancar servicios:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows\install_birdmonitor_windows.ps1
```

El instalador:

* Detecta la ruta del proyecto.
* Busca `mediamtx.exe` y `mediamtx.yml`.
* Crea scripts internos en `%LOCALAPPDATA%\BirdMonitor`.
* Crea las tareas programadas `BirdMonitor MediaMTX` y `BirdMonitor Backend`.
* Arranca MediaMTX en `8888` y FastAPI en `8000`.

Comprobar estado:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows\check_birdmonitor_windows.ps1
```

Desinstalar automatizacion:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows\uninstall_birdmonitor_windows.ps1
```

Esto elimina las tareas programadas y detiene procesos, pero no borra el repositorio ni la base de datos.

### 6. Instalacion automatica en macOS

Requisitos:

* Repositorio fuera de `Desktop`, `Documents` y `Downloads`, por ejemplo en `~/Projects`.
* Entorno virtual creado en `monitoreo_aves/venv`.
* Dependencias instaladas con `pip install -r requirements.txt`.
* `tools/mediamtx/macos/mediamtx` y `tools/mediamtx/mediamtx.yml` disponibles.

Instalar y arrancar servicios:

```bash
bash scripts/macos/install_birdmonitor_macos.sh
```

El instalador crea este `LaunchAgent` de usuario:

```text
~/Library/LaunchAgents/com.birdmonitor.services.plist
```

Tambien deja logs en:

```text
~/Library/Application Support/BirdMonitor
```

Comprobar estado:

```bash
bash scripts/macos/check_birdmonitor_macos.sh
```

Desinstalar automatizacion:

```bash
bash scripts/macos/uninstall_birdmonitor_macos.sh
```

Esto elimina el `LaunchAgent` y detiene procesos, pero no borra el repositorio, MediaMTX ni los logs.

### 7. Arranque manual para desarrollo

Si no quieres instalar automatizacion, puedes arrancar el backend y MediaMTX manualmente.

macOS:

```bash
bash scripts/macos/start_birdmonitor_macos.sh
```

Windows o cualquier sistema con el entorno activo:

```bash
python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

En manual, si MediaMTX no esta arrancado, el dashboard abrira pero el directo HLS no estara disponible.

### 8. Acceso al dashboard y al stream

Desde el propio servidor:

```text
http://127.0.0.1:8000
```

Desde otro ordenador, movil o Raspberry en LAN/Tailscale:

```text
http://IP_DEL_SERVIDOR:8000
```

Stream HLS esperado:

```text
http://IP_DEL_SERVIDOR:8888/birdmonitor-audio/index.m3u8
```

En la app movil, introduce la URL del backend en la pantalla de conexion. Ejemplo:

```text
http://100.80.10.25:8000
```

### 9. Raspberry Pi y varios nodos

Para pruebas manuales en Raspberry:

```bash
cd ~/birdmonitor/monitoreo_aves/hardware/raspberry_pi
source ~/birdmonitor/birdnet-env/bin/activate
export BIRDMONITOR_SERVER_URL="http://IP_DEL_SERVIDOR:8000"
export BIRDMONITOR_NODE_NAME="birdmonitor-01"
python mainNode.py
```

El supervisor del directo usa las mismas variables:

```bash
export BIRDMONITOR_SERVER_URL="http://IP_DEL_SERVIDOR:8000"
export BIRDMONITOR_NODE_NAME="birdmonitor-01"
python supervisor.py
```

En despliegue real, estas variables pueden quedar en el servicio `systemd` mediante `Environment=` o `EnvironmentFile=`. Ademas, `mainNode.py` y `supervisor.py` cargan automaticamente un archivo local llamado `hardware/raspberry_pi/birdmonitor.env` si existe.

Ese archivo esta ignorado por Git para que cada Raspberry pueda tener su propia configuracion sin tocar codigo. Hay una plantilla versionada en:

```text
hardware/raspberry_pi/birdmonitor.env.example
```

Para configurar una Raspberry:

```bash
cd hardware/raspberry_pi
cp birdmonitor.env.example birdmonitor.env
nano birdmonitor.env
```

Ejemplo de variables para `birdmonitor.env`:

```bash
BIRDMONITOR_SERVER_URL=http://IP_DEL_SERVIDOR:8000
BIRDMONITOR_NODE_NAME=birdmonitor-01
BIRDMONITOR_NODE_LOCATION=Sevilla
BIRDMONITOR_NODE_LAT=37.3891
BIRDMONITOR_NODE_LON=-5.9845
BIRDMONITOR_MIC_DEVICE=1
```

Comandos utiles con `systemd`:

```bash
sudo systemctl start birdmonitor.service
sudo systemctl status birdmonitor.service
journalctl -u birdmonitor.service -f

sudo systemctl start birdstream.service
sudo systemctl status birdstream.service
journalctl -u birdstream.service -f
```

### 10. Comprobaciones rapidas

Windows:

```powershell
netstat -ano | findstr :8000
netstat -ano | findstr :8888
```

macOS:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:8888 -sTCP:LISTEN
```

Backend:

```text
http://127.0.0.1:8000/devices/
```

HLS:

```text
http://127.0.0.1:8888/birdmonitor-audio/index.m3u8
```

## Estado del Proyecto

El sistema se encuentra en fase de validación técnica con funcionalidad completa "End-to-End".

### Funcionalidades Implementadas

* **Captura y Procesamiento de Señal:**

    * * Grabación de audio en ventanas de 60 segundos a una frecuencia de muestreo de 48kHz, ejecutadas en ciclos de 5 minutos para reducir carga térmica y consumo del nodo Edge..
    * Generación automática de espectrogramas de Mel para validación visual de las detecciones.
    * Cálculo de energía RMS (Root Mean Square) para la medición objetiva del nivel de ruido ambiental.

* **Inteligencia Artificial en el Borde:**

    * Inferencia local mediante el modelo **BirdNET-Lite** (framework TensorFlow Lite).
    * Capacidad de clasificación de más de 6,000 especies de aves.
    * Filtrado de falsos positivos mediante umbrales de confianza configurables.
    * Clasificación de fuentes de ruido antropogénico (voces humanas, motores).

* **Arquitectura de Datos Híbrida:**

    * **Upload Activo de Archivos:** La Raspberry Pi envía el JSON de inferencia junto con los archivos `.wav` y `.png` a la API central para su análisis bioacústico en profundidad.
    * **Tolerancia a Fallos (Offline Sync):** Si el servidor central cae o hay pérdida de red, el nodo encola las detecciones y audios localmente en la MicroSD. Al recuperar la conexión, el nodo sincroniza automáticamente el backlog histórico.
    * **Rotación de Logs y Limpieza (Wear Leveling):** Algoritmo automatizado que elimina audios mayores a 48-72h para preservar la vida útil de la MicroSD.
    * **Protección RTC (Real Time Clock):** Rutina de bloqueo pre-arranque que evita la generación de datos corruptos ('Síndrome de 1970') tras cortes de luz en entornos sin internet.

* **Interfaz de Visualización y Control (Dashboard):**

    * **Telemetría en Tiempo Real:** Interfaz SPA con actualizaciones sin recarga (Polling) y evasión inteligente de caché HTTP.
    * **Análisis Ecológico:** Cálculo automático de Índices de Biodiversidad (Shannon $H'$, Pielou $J'$, Simpson $1-D$).
    * **Radar de Bioacústica (Paisaje Sonoro):** Análisis matricial del archivo `.wav` en el servidor utilizando `scikit-maad` para extraer los índices ACI, ADI, AEI, BIO y NDSI, midiendo la salud acústica del entorno y dibujando una huella sonora en gráfico de radar.
    * **Cartografía Dinámica:** Generación automática de mapas interactivos (Leaflet.js) basados en la geolocalización IP del nodo, mostrando radios de cobertura ponderados por el índice de Shannon local.

## Arquitectura Técnica

El proyecto se estructura en tres módulos principales desacoplados:

### 1. Nodo Sensor (Hardware)

Ejecutado sobre plataforma ARM (Raspberry Pi 4 / 3B+). Responsable de la digitalización del entorno acústico.

* **Lenguaje:** Python 3.
* **Librerías Principales:** `librosa` (análisis DSP), `sounddevice` (captura), `tflite-runtime` (inferencia neuronal).
* **Lógica de Negocio:** Algoritmo de decisión basado en geolocalización IP y niveles de confianza.

### 2. Backend (Servidor Central)

Responsable de la orquestación, validación y persistencia de los datos recibidos de los nodos distribuidos.

* **Framework:** FastAPI.
* **Base de Datos:** SQLite (archivo `birdmonitor.db`).
* **ORM:** SQLAlchemy.
* **Validación de Esquemas:** Pydantic.

### 3. Frontend (Interfaz de Usuario)

Interfaz gráfica para la visualización de telemetría y gestión de históricos.

* **Tecnologías:** HTML5, CSS3, JavaScript (Vanilla).
* **Estilado:** Bootstrap 5.
* **Visualización de Datos:** Chart.js.

## Acceso Remoto al Nodo Edge (vía SSH)

En un entorno de producción, la Raspberry Pi operará de forma autónoma (Headless) en la naturaleza o en ubicaciones de difícil acceso. Para gestionar el código, revisar los logs en tiempo real o reiniciar servicios sin necesidad de conectar periféricos físicos, se utiliza el protocolo SSH.

### Pasos para acceder al nodo:

1. **Abre una terminal** en tu equipo principal (Windows, Mac o Linux).
2. **Asegúrate de que tu equipo principal está en la misma red** que la Raspberry Pi (ya sea en la misma red WiFi local o a través de una red virtual privada/VPN como Tailscale).
3. **Ejecuta el comando de conexión SSH** utilizando el nombre de usuario de la Raspberry y su dirección IP asignada:

```bash
ssh pi@IP_DE_LA_RASPBERRY
```

Si usas Tailscale, puedes utilizar la IP de Tailscale o el hostname MagicDNS de la Raspberry:

```bash
ssh pi@NOMBRE_RASPBERRY
```

## Estructura del Repositorio

```text
monitoreo_aves/
├── backend/                        # Módulo Servidor
│   ├── app/
│   │   ├── main.py                 # Definición de API REST y endpoints (Uploads/JSON)
│   │   ├── models.py               # Modelos de BBDD (SQLAlchemy)
│   │   ├── schemas.py              # Esquemas de validación (Pydantic)
│   │   └── database.py             # Configuración SQL
│   ├── analisisBiodiversidad.py    # Motor matemático (Bioacústica + Ecología)
│   └── birdmonitor.db              # Base de datos local (Autogenerado)
│
├── frontend/                       # Módulo de Interfaz Web
│   ├── css/                        # Hojas de estilo y UI oscura
│   ├── js/                         # Lógica de cliente y Fetchers
│   ├── assets/                     # Imágenes estáticas y placeholders
│   └── index.html                  # Punto de entrada
│
├── hardware/raspberry_pi/          # Código fuente del Nodo Edge
│   ├── model/                      # Modelo BirdNET TFLite y etiquetas
│   ├── records/                    # Buffer de audio (.wav) local y remoto
│   ├── spectrograms/               # Buffer de imágenes (.png)
│   ├── analyzer.py                 # Abstracción para el modelo IA
│   └── mainNode.py                 # Orquestador del nodo y gestor Offline
│
└── requirements.txt                # Dependencias (FastAPI, scikit-maad...)
```
