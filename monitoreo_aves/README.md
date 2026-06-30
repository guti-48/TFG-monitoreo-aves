# Sistema IoT de Monitoreo Acústico de Aves (TFG)

Este proyecto consiste en el diseño, desarrollo e implementación de un sistema distribuido para la detección, clasificación y monitoreo de avifauna mediante análisis acústico pasivo (PAM) e Inteligencia Artificial.

El sistema utiliza nodos de computación en el borde (Edge Computing) basados en Raspberry Pi para procesar audio en tiempo real, implementando una arquitectura híbrida que permite el almacenamiento local de datos científicos (incluyendo análisis de contaminación acústica) y la contribución simultánea a redes de ciencia ciudadana (BirdWeather).

## Arranque rapido multiplataforma

El servidor central puede ejecutarse en Windows, macOS o Linux. El nodo Raspberry debe apuntar a la URL real de ese servidor central mediante IP LAN o Tailscale.

### Instalacion base

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

macOS o Linux:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

El dashboard queda en `http://localhost:8000`. Desde otro ordenador o movil se debe usar `http://IP_DEL_SERVIDOR:8000`.

### HLS y MediaMTX

BirdMonitor espera MediaMTX en el puerto `8888` y el stream HLS en:

```text
http://IP_DEL_SERVIDOR:8888/birdmonitor-audio/index.m3u8
```

El dashboard web construye esa URL de forma dinamica con el mismo hostname desde el que se abre. Si entras desde un Mac a `http://192.168.1.50:8000`, el reproductor intentara usar `http://192.168.1.50:8888/birdmonitor-audio/index.m3u8`.

En macOS, con `mediamtx` disponible en el `PATH` o en `tools/mediamtx/mediamtx`, puedes arrancar backend y MediaMTX juntos con:

```bash
bash scripts/macos/start_birdmonitor_macos.sh
```

Si el `mediamtx.yml` esta en otra ruta:

```bash
MEDIAMTX_CONFIG=/ruta/a/mediamtx.yml bash scripts/macos/start_birdmonitor_macos.sh
```

### Variables que debe revisar cada persona

| Variable | Donde se usa | Valor de ejemplo |
| --- | --- | --- |
| `BIRDMONITOR_SERVER_URL` | Raspberry (`mainNode.py` y `supervisor.py`) | `http://IP_DEL_SERVIDOR:8000` |
| `BIRDMONITOR_STREAM_BASE_URL` | Backend, si MediaMTX no usa el mismo host que el dashboard | `http://IP_DEL_SERVIDOR:8888` |
| `BIRDMONITOR_STREAM_PATH` | Backend/dashboard HLS | `birdmonitor-audio` |
| `BIRDMONITOR_CORS_ORIGINS` | Backend, si una app web se sirve desde otro origen | `http://IP_DEL_SERVIDOR:8000,http://localhost:8000` |
| `BIRDMONITOR_NODE_NAME` | Raspberry y control de escucha | `birdmonitor` |
| `BIRDMONITOR_NODE_LOCATION`, `BIRDMONITOR_NODE_LAT`, `BIRDMONITOR_NODE_LON` | Ubicacion real del nodo | `Sevilla`, `37.3891`, `-5.9845` |

Regla rapida:

* `127.0.0.1` o `localhost` solo valen para la misma maquina.
* Desde un Mac hacia un servidor Windows, usa `http://IP_DEL_WINDOWS:8000`.
* Desde un movil real, usa IP LAN o Tailscale; nunca `127.0.0.1`.
* Desde la Raspberry, `BIRDMONITOR_SERVER_URL` debe apuntar al servidor central, no a la propia Raspberry.

Si MediaMTX vive en otro host o puerto, define `BIRDMONITOR_STREAM_BASE_URL` en el entorno del backend. En casos especiales del dashboard tambien puedes exponer antes de `dashboard.js`:

```html
<script>
window.BIRDMONITOR_CONFIG = {
  liveStreamBaseUrl: "http://IP_DEL_SERVIDOR:8888",
  streamName: "birdmonitor-audio",
  streamNodeName: "birdmonitor"
};
</script>
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

## Guia de Despliegue

El sistema se despliega con una arquitectura unificada: el backend FastAPI sirve tanto la API REST como el dashboard web mediante archivos estáticos. Por tanto, no es necesario levantar un servidor independiente para el frontend.

El servidor central puede ejecutarse en Windows, macOS o Linux. El nodo Edge se ejecuta en Raspberry Pi OS Lite y debe apuntar a la URL real del servidor central, normalmente una IP LAN o una IP/hostname de Tailscale.

1. Crear y activar el entorno virtual dentro de la carpeta `monitoreo_aves`.

Para Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Para macOS o Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

2. Para instalar las dependencias deberemos ejecutar:

```bash
    pip install -r requirements.txt
```

3. Ejecutar el servidor central desde la carpeta `monitoreo_aves`:

```bash
    uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

El dashboard queda disponible en:

```text
http://localhost:8000
```

Y desde otro dispositivo, mediante la IP LAN o Tailscale del servidor:

```text
http://XXX.XXX.XXX:8000
```

4. La base de datos SQLite se genera automáticamente si no existe. Solo debe eliminarse manualmente en caso de querer reiniciar completamente los datos históricos durante pruebas de desarrollo.

### Despliegue Automático en Windows

Para facilitar el uso del sistema sin depender de terminales abiertas, el proyecto incluye scripts de automatización para Windows. Estos scripts permiten configurar el arranque automático de los servicios necesarios en el servidor central:

* Backend FastAPI en el puerto `8000`.
* MediaMTX en el puerto `8888`, encargado de servir el stream HLS de audio en directo.

De esta forma, una vez configurado, el usuario solo necesita encender el ordenador servidor y abrir la app móvil o el dashboard web. No es necesario lanzar manualmente `uvicorn` ni `mediamtx` desde terminal.

#### Requisitos Previos

Antes de ejecutar los scripts, deben cumplirse estas condiciones:

* Tener Python instalado.
* Tener creado el entorno virtual del proyecto.
* Tener instaladas las dependencias con:

```bash
pip install -r requirements.txt
```

* Tener disponible `mediamtx.exe`.
* Tener disponible el archivo de configuración `mediamtx.yml`.

Se recomienda colocar MediaMTX dentro del repositorio en la siguiente ruta:

```text
monitoreo_aves/
└── tools/
    └── mediamtx/
        ├── mediamtx.exe
        └── mediamtx.yml
```

Si MediaMTX no se encuentra en esa ubicación, el script de instalación solicitará manualmente la ruta completa de `mediamtx.exe` y `mediamtx.yml`.

#### Scripts Disponibles

Los scripts se encuentran en:

```text
scripts/windows/
```

Estructura:

```text
scripts/
└── windows/
    ├── install_birdmonitor_windows.ps1
    ├── check_birdmonitor_windows.ps1
    └── uninstall_birdmonitor_windows.ps1
```

#### Instalación Automática

Para configurar el arranque automático, abrir **PowerShell como administrador** desde la raíz del repositorio y ejecutar:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows\install_birdmonitor_windows.ps1
```

Este script realiza las siguientes acciones:

* Detecta automáticamente la ruta del repositorio.
* Comprueba que existe `backend/app/main.py`.
* Busca `mediamtx.exe` y `mediamtx.yml`.
* Crea scripts internos de arranque en:

```text
%LOCALAPPDATA%\BirdMonitor
```

* Crea una tarea programada para MediaMTX:

```text
BirdMonitor MediaMTX
```

* Crea una tarea programada para el backend FastAPI:

```text
BirdMonitor Backend
```

* Arranca ambos servicios.
* Comprueba que los puertos `8000` y `8888` están activos.

Una vez instalado, los servicios se iniciarán automáticamente al iniciar sesión en Windows.

#### Comprobación del Estado

Para comprobar que el sistema está funcionando correctamente:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows\check_birdmonitor_windows.ps1
```

Este script comprueba:

* Si MediaMTX está en ejecución.
* Si el puerto `8888` está escuchando.
* Si el backend está escuchando en el puerto `8000`.
* El estado de las tareas programadas.
* Si el endpoint `/devices/` responde correctamente.

También muestra la ubicación de los logs generados:

```text
%LOCALAPPDATA%\BirdMonitor
```

#### Desinstalación de las Tareas Automáticas

Para eliminar las tareas programadas y detener MediaMTX:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows\uninstall_birdmonitor_windows.ps1
```

Este script elimina:

```text
BirdMonitor MediaMTX
BirdMonitor Backend
```

y detiene el proceso `mediamtx.exe` si está activo.

No elimina el repositorio, la base de datos ni los archivos de configuración.

#### Comprobación Manual de Puertos

También se puede comprobar manualmente desde PowerShell:

```powershell
netstat -ano | findstr :8000
netstat -ano | findstr :8888
```

Resultado esperado:

```text
0.0.0.0:8000   LISTENING
0.0.0.0:8888   LISTENING
```

#### Acceso al Sistema

Una vez activos los servicios, el dashboard web queda disponible en:

```text
http://localhost:8000
```

Desde otro dispositivo en la misma red o mediante Tailscale:

```text
http://IP_DEL_SERVIDOR:8000
```

El stream HLS queda disponible en:

```text
http://IP_DEL_SERVIDOR:8888/birdmonitor-audio/index.m3u8
```

La app móvil debe configurarse con la IP LAN o Tailscale del servidor. No debe usarse `127.0.0.1` desde un móvil real, ya que esa dirección apunta al propio dispositivo móvil.

### Ejecución del Nodo Edge en Raspberry Pi

En la Raspberry Pi, el nodo puede ejecutarse manualmente para pruebas:

```bash
cd ~/birdmonitor/monitoreo_aves/hardware/raspberry_pi
source ~/birdmonitor/birdnet-env/bin/activate
python mainNode.py
```

En despliegue real, el nodo se ejecuta como servicio `systemd`:

```bash
sudo systemctl start birdmonitor.service
sudo systemctl status birdmonitor.service
journalctl -u birdmonitor.service -f
```

El nodo envía las detecciones al servidor central definido en `SERVER_URL`, actualmente configurado con la IP de Tailscale del servidor Windows.

## Acceso Remoto al Nodo Edge (vía SSH)

En un entorno de producción, la Raspberry Pi operará de forma autónoma (Headless) en la naturaleza o en ubicaciones de difícil acceso. Para gestionar el código, revisar los logs en tiempo real o reiniciar servicios sin necesidad de conectar periféricos físicos, se utiliza el protocolo SSH.

### Pasos para acceder al nodo:

1. **Abre una terminal** en tu equipo principal (Windows, Mac o Linux).
2. **Asegúrate de que tu equipo principal está en la misma red** que la Raspberry Pi (ya sea en la misma red WiFi local o a través de una red virtual privada/VPN como Tailscale).
3. **Ejecuta el comando de conexión SSH** utilizando el nombre de usuario de la Raspberry y su dirección IP asignada:

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
└── requirements.txt                # Dependencias (FastAPI, scikit-maad...)```