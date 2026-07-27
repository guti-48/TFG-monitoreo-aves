# Sistema IoT de Monitoreo Acústico de Aves (TFG)

Este proyecto consiste en el diseño, desarrollo e implementación de un sistema distribuido para la detección, clasificación y monitoreo de avifauna mediante análisis acústico pasivo (PAM) e Inteligencia Artificial.

El sistema utiliza nodos de computación en el borde (Edge Computing) basados en Raspberry Pi para procesar audio en tiempo real, implementando una arquitectura híbrida que permite el almacenamiento local de datos científicos (incluyendo análisis de contaminación acústica) y la contribución simultánea a redes de ciencia ciudadana (BirdWeather).

## Guia de instalacion y configuracion

El proyecto queda preparado para clonarse y ejecutarse con un servidor central en Windows o macOS. La Raspberry Pi actua como nodo Edge y debe apuntar a la IP real del servidor central, normalmente una IP LAN o una IP/hostname de Tailscale.

### Arquitectura de despliegue

```text
Raspberry Pi / nodo Edge                  Servidor central                 Clientes
┌────────────────────────┐               ┌────────────────────┐           ┌─────────────────────┐
│ microfono → ALSA       │               │ FastAPI       :8000│──────────▶│ navegador / movil   │
│   ├─ mainNode / BirdNET│── datos ─────▶│ base de datos      │           │ dashboard      :8000│
│   └─ birdstream/FFmpeg │── RTSP ──────▶│ MediaMTX      :8554│── HLS ───▶│ escucha HLS    :8888│
│ supervisor.py          │               │                  │ └── RTSP ──▶│ VLC             :8554│
└────────────────────────┘               └────────────────────┘           └─────────────────────┘
```

La Raspberry captura y analiza el microfono, y publica **una sola señal** RTSP.
FastAPI y MediaMTX se ejecutan en el servidor central. MediaMTX transforma esa
señal en HLS y la distribuye a todos los oyentes; abrir dos móviles no duplica
la captura, BirdNET ni el proceso FFmpeg de la Raspberry.

Reglas importantes de red:

* `127.0.0.1` y `localhost` solo sirven desde la misma maquina.
* El servidor escucha en `0.0.0.0`; normalmente no tienes que escribir su propia IP en el backend.
* Desde la Raspberry, la app movil u otro ordenador, usa la IP LAN o Tailscale del servidor.
* Si cambias el servidor de Windows a Mac, cambia la IP en la Raspberry y en la app movil, no en todos los archivos del backend.
* Varios clientes pueden abrir el mismo dashboard a la vez: Mac, Windows, movil o tablet solo necesitan entrar a `http://IP_DEL_SERVIDOR:8000`.
* Para VLC se usa `rtsp://IP_DEL_SERVIDOR:8554/NOMBRE_DEL_STREAM`; nunca la IP de la Raspberry.

### Servidor central y clientes

La Raspberry no necesita saber desde que ordenador vas a mirar el dashboard. La Raspberry solo envia datos y consulta ordenes en el **servidor central** configurado en `BIRDMONITOR_SERVER_URL`.

Ejemplos:

```text
Raspberry -> http://IP_TAILSCALE_SERVIDOR:8000   # envio de datos y control
Mac       -> http://IP_TAILSCALE_SERVIDOR:8000   # cliente viendo el dashboard
Windows   -> http://IP_TAILSCALE_SERVIDOR:8000   # servidor y cliente local
Movil     -> http://IP_TAILSCALE_SERVIDOR:8000   # navegador, con Tailscale activo
```

Si el servidor central es el Mac, Windows tambien puede entrar al dashboard del Mac. Si el servidor central es Windows, el Mac puede entrar al dashboard de Windows. Lo importante es que todos apunten al mismo backend si quieres ver la misma base de datos y controlar la misma Raspberry.

No hace falta instalar la app móvil para escuchar. El dashboard web es responsive
y constituye el cliente móvil principal. Al entrar desde la misma Wi-Fi se usa
la IP LAN del servidor; desde otra red se usa su IP Tailscale y el móvil también
debe tener Tailscale conectado.

Para un stream llamado `birdmonitor-audio`, las direcciones son:

```text
Dashboard y escucha móvil:  http://IP_DEL_SERVIDOR:8000
Reproductor HLS alternativo: http://IP_DEL_SERVIDOR:8888/birdmonitor-audio/
Manifiesto HLS:              http://IP_DEL_SERVIDOR:8888/birdmonitor-audio/index.m3u8
VLC / RTSP:                  rtsp://IP_DEL_SERVIDOR:8554/birdmonitor-audio
```

El botón **Desconectar este dispositivo** solo para el reproductor de ese
navegador. **Detener emisión para todos**, situado dentro del control global,
detiene `birdstream.service` en la Raspberry y corta a todos los oyentes.

La distribución web usa HLS fMP4 con segmentos de 1 segundo. En condiciones
normales el reproductor se mantiene aproximadamente 3–5 segundos detrás del
directo y vuelve automáticamente al borde al reanudar la pestaña o regresar
desde segundo plano. El dashboard intenta cargar `hls.js` desde el CDN y, si no
hay acceso a Internet, utiliza la copia que sirve el propio MediaMTX. En móvil
se prioriza la salida de audio y se omite el espectro Web Audio para evitar que
las políticas de reproducción del navegador silencien la escucha.

Si reaparece un retraso cercano a 30 segundos, comprueba el manifiesto hijo:
debe indicar `#EXT-X-TARGETDURATION:1` y segmentos de alrededor de 1 segundo.
Un valor próximo a 11 indica que MediaMTX sigue ejecutándose con la variante
MPEG-TS antigua. Después de actualizar, fuerza la recarga del navegador para
obtener la versión nueva de `dashboard.js`.

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
| Ubicacion del nodo | `BIRDMONITOR_NODE_LOCATION`, `BIRDMONITOR_NODE_LAT`, `BIRDMONITOR_NODE_LON` | Lugar y coordenadas manuales/GPS del nodo; necesarias para dibujar el círculo local |
| Geolocalización IP | `BIRDMONITOR_AUTO_GEOLOCATION` | Desactivada por defecto (`0`); si se activa, el mapa avisa de que es aproximada y oculta el círculo |
| Microfono en Raspberry | `BIRDMONITOR_MIC_DEVICE` | Indice del dispositivo de entrada si no quieres usar el predeterminado |
| Ganancia fisica ALSA | `BIRDMONITOR_MIC_ALSA_CARD`, `BIRDMONITOR_MIC_CAPTURE_VOLUME`, `BIRDMONITOR_MIC_AUTO_GAIN` | Ejemplo para un USB en la tarjeta 3: `3`, `50%`, `0` |
| Ciclo de grabacion | `BIRDMONITOR_RECORD_SECONDS`, `BIRDMONITOR_RECORD_INTERVAL_SECONDS` | Duracion e intervalo en segundos, por ejemplo `60`, `300` |
| Umbrales de deteccion | `BIRDMONITOR_BIRD_CONFIDENCE_THRESHOLD`, `BIRDMONITOR_HUMAN_CONFIDENCE_THRESHOLD`, `BIRDMONITOR_MOTOR_CONFIDENCE_THRESHOLD` | Por ejemplo `0.65`, `0.35`, `0.40` |
| Umbral de ruido ambiente | `BIRDMONITOR_HIGH_NOISE_RMS_THRESHOLD` | Por ejemplo `0.02` |
| BirdNET reproducible | `BIRDMONITOR_BIRDNET_MODEL_VERSION`, `BIRDMONITOR_BIRDNET_OVERLAP_SECONDS`, `BIRDMONITOR_BIRDNET_SENSITIVITY` | Por defecto `2.4`, `1.5`, `1.25` |
| Diagnostico del microfono | `BIRDMONITOR_MIC_MIN_RMS`, `BIRDMONITOR_MIC_MAX_CLIPPING_RATIO`, `BIRDMONITOR_MIC_MAX_DC_OFFSET`, `BIRDMONITOR_MIC_CLIPPING_LEVEL` | Los valores por defecto detectan senal baja, clipping y desplazamiento DC sin modificar el WAV |
| Entorno acústico del mapa | `BIRDMONITOR_ACOUSTIC_REFERENCE_RADIUS_M` | `25` m por defecto, siempre rotulado como referencia no calibrada; usa `0` para ocultar el círculo |
| BirdWeather | `BIRDWEATHER_TOKEN_FILE` | Ruta local del token, por ejemplo `/etc/birdmonitor/birdweather_token` |
| Servicio de streaming de la Raspberry | Archivo o servicio `birdstream.service` que publique audio por RTSP hacia MediaMTX | Debe apuntar a `rtsp://IP_DEL_SERVIDOR:8554/PATH`, normalmente `birdmonitor-audio` |
| Dashboard web | Normalmente no se edita: `frontend/js/dashboard.js` carga `/devices/` y permite seleccionar nodo y path MediaMTX desde la vista de directo | Si entras en `http://IP_SERVIDOR:8000`, usara `http://IP_SERVIDOR:8888` |
| Dashboard con MediaMTX en otro host/puerto | `frontend/index.html`, antes de cargar `frontend/js/dashboard.js`, definiendo `window.BIRDMONITOR_CONFIG` | `liveStreamBaseUrl`, `liveStreamRtspBaseUrl`, `streamName`, `streamNodeName` |
| Rutas HLS por nodo | `BIRDMONITOR_STREAM_PATH` o `BIRDMONITOR_STREAM_PATH_TEMPLATE`, leidas por `backend/app/config.py` | Ruta fija o plantilla, por ejemplo `{node_name}-audio` |
| Backend si MediaMTX no esta en el mismo host | `BIRDMONITOR_STREAM_BASE_URL` | `http://IP_DEL_SERVIDOR:8888` |
| RTSP si MediaMTX no esta en el mismo host | `BIRDMONITOR_STREAM_RTSP_BASE_URL` | `rtsp://IP_DEL_SERVIDOR:8554` |
| Origenes web externos | `BIRDMONITOR_CORS_ORIGINS` | Lista separada por comas |
| Arranque del backend | `BIRDMONITOR_BACKEND_HOST`, `BIRDMONITOR_BACKEND_PORT` | `0.0.0.0`, `8000` |
| App movil | Pantalla de conexion de la app | `http://IP_DEL_SERVIDOR:8000`; no usar `127.0.0.1` en un movil real |

El diagnostico del microfono es observacional: no normaliza ni aplica ganancia digital al WAV. Si aparece `low_signal` o `clipping`, ajusta el nivel fijo de captura del dispositivo (por ejemplo con `alsamixer` en Raspberry Pi) y vuelve a observar varias muestras. Amplificar despues de grabar no recupera relacion senal/ruido ni corrige una entrada ya saturada.

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
birdmonitor-norte-audio
birdmonitor-sur-audio
```

La vista web carga los nodos registrados y permite seleccionar el nodo y el path de MediaMTX desde la pantalla de escucha en directo. Si quieres fijar un valor por defecto sin tocar `dashboard.js`, puedes definir antes de cargar el script:

```html
<script>
window.BIRDMONITOR_CONFIG = {
  liveStreamBaseUrl: "http://IP_DEL_SERVIDOR:8888",
  liveStreamRtspBaseUrl: "rtsp://IP_DEL_SERVIDOR:8554",
  streamName: "birdmonitor-norte-audio",
  streamNodeName: "birdmonitor-norte"
};
</script>
```

### 5. Instalacion automatica en Windows

Requisitos:

* PowerShell abierto como administrador.
* Entorno virtual creado en `monitoreo_aves/venv`.
* Dependencias instaladas con `pip install -r requirements.txt`.
* `mediamtx.exe` disponible en `tools/mediamtx/`, en la raiz del proyecto o en `C:\`.
* `tools/mediamtx/mediamtx.yml` disponible como configuracion versionada del proyecto.

Instalar y arrancar servicios:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows\install_birdmonitor_windows.ps1
```

El instalador:

* Detecta la ruta del proyecto.
* Busca `mediamtx.exe` y `mediamtx.yml`.
* Crea scripts internos en `%LOCALAPPDATA%\BirdMonitor`.
* Crea las tareas programadas `BirdMonitor MediaMTX` y `BirdMonitor Backend`.
* Sustituye automaticamente tareas anteriores con esos mismos nombres; no es necesario borrarlas a mano.
* Programa ambas tareas para arrancar con Windows, aunque todavia no se haya abierto sesion.
* Reintenta el arranque si uno de los procesos termina con error.
* Arranca MediaMTX en `8888` y FastAPI en `8000`.

Hay que ejecutar el instalador una vez en cada ordenador servidor y volver a ejecutarlo si cambia la ruta del repositorio, del entorno virtual o de MediaMTX. Actualizar el codigo con Git no registra por si solo las tareas de Windows.

Comprobar estado:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows\check_birdmonitor_windows.ps1
```

Aplicar cambios del backend o de `mediamtx.yml` sin detener procesos ajenos:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows\restart_birdmonitor_streaming.ps1
```

Este reinicio debe ejecutarse desde PowerShell como administrador. Comprueba que
los procesos que escuchan en `8000` y `8888` pertenecen a BirdMonitor antes de
detenerlos, arranca de nuevo ambas tareas y espera a que HLS vuelva a estar listo.

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
BIRDMONITOR_STREAM_SERVICE=birdstream.service
BIRDMONITOR_STREAM_POLL_INTERVAL=5
BIRDMONITOR_STREAM_FAILURE_LIMIT=3
BIRDMONITOR_STREAM_HEALTH_TIMEOUT=5
```

El supervisor no se limita al estado de systemd: tambien comprueba que el manifiesto HLS responda. Si `birdstream.service` figura activo pero deja de publicar despues de reiniciar el servidor central o perder la red, lo reinicia tras el numero de fallos consecutivos configurado.

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

    * * Grabación de audio en ventanas de 60 segundos a una frecuencia de muestreo de 48kHz, ejecutadas en ciclos de 5 minutos para reducir carga térmica y consumo del nodo Edge.
    * Generación automática de espectrogramas de Mel para el archivo científico y de una vista de revisión realzada entre 250 Hz y 10 kHz.
    * Cálculo de energía RMS (Root Mean Square) para la medición objetiva del nivel de ruido ambiental.
    * Diagnóstico de cada captura mediante pico, clipping, desplazamiento DC y suelo de ruido, sin alterar el audio original.
    * Diagnóstico bajo demanda de cada evidencia mediante proporción de graves, prominencia del zumbido de red y contraste de la ventana clasificada.

* **Inteligencia Artificial en el Borde:**

    * Inferencia local mediante **BirdNET-Analyzer V2.4** con `birdnetlib` y TensorFlow Lite.
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
    * **Análisis Ecológico Descriptivo:** Cálculo de Shannon $H'$, Pielou $J'$ y Simpson $1-D$ sobre los eventos de detección válidos. El valor $N$ representa eventos, no individuos, y los índices no estiman por sí solos población, densidad ni salud del ecosistema.
    * **Radar de Bioacústica (Paisaje Sonoro):** Análisis matricial del archivo `.wav` mediante `scikit-maad` para extraer ACI, ADI, AEI, BIO y NDSI. Son descriptores de la señal y se interpretan comparando el mismo nodo, micrófono, configuración y esfuerzo de muestreo; no constituyen por sí solos un diagnóstico de salud ecológica. En la configuración usada, NDSI expresa el balance normalizado de energía entre 0–1 kHz y 1–10 kHz.
    * **Cartografía del punto de muestreo:** Mapa interactivo basado en la ubicación comunicada por el nodo. Con coordenadas manuales o GPS, el círculo representa un entorno local orientativo de 25 m, no calibrado; con geolocalización IP solo se muestra un marcador aproximado. Ninguno de ellos garantiza que todas las aves próximas se detecten ni excluye señales audibles más lejanas.
    * **Evidencia acústica sincronizada:** El histórico permite escuchar un contexto de 20 segundos directamente sobre su espectrograma. Un cursor recorre la imagen durante la reproducción y una franja resalta los 3 segundos que BirdNET utilizó para clasificar la especie.
    * **Revisión acústica enfocada:** El revisor escucha directamente el WAV original dentro de un contexto de 20 segundos, sin copias filtradas que puedan introducir artefactos. La vista muestra solo la confianza, el evento marcado, el reproductor y las acciones humanas; el diagnóstico de graves, zumbido y contraste queda plegado como detalle técnico. El espectrograma resta visualmente el fondo estacionario para facilitar la lectura, sin modificar el audio ni la inferencia de BirdNET.
    * **Exportación científica y visual:** El histórico conserva la descarga CSV interoperable y añade un informe `.xlsx` real generado en el servidor. El libro contiene un resumen con gráficos, detecciones, actividad horaria, especies, índices ecológicos, calidad de audio, revisiones humanas y metadatos de BirdNET, con filtros y formato condicional para facilitar su uso en Excel.
    * **Distribución de especies escalable:** El gráfico principal ordena las especies por número de detecciones y presenta inicialmente las siete más escuchadas. Un control permite desplegar la lista completa dentro de la propia tarjeta sin ocultar nombres ni desbordar lateralmente la interfaz.

Las detecciones creadas desde esta versión conservan en la base de datos los segundos de inicio y fin indicados por BirdNET. Los registros anteriores siguen siendo compatibles, pero muestran los primeros 20 segundos del WAV porque esa marca temporal no se almacenaba todavía.

### Alcance espacial e interpretación científica

El radio de 25 m es una referencia visual conservadora para el despliegue urbano actual, no una especificación universal del micrófono ni un área de inventario exhaustivo. Solo se dibuja cuando el nodo comunica coordenadas manuales o GPS; una posición obtenida por IP se identifica como aproximada y muestra únicamente el marcador. La distancia de detección cambia con la especie y su vocalización, la frecuencia, el nivel de ruido, la vegetación, los edificios, la orientación y la cadena completa de grabación. Darras et al. observaron que el 95 % de las detecciones de su sistema y sus hábitats se concentró dentro de 40 m, pero también remarcaron la necesidad de estimar la detectabilidad para cada configuración ([Methods in Ecology and Evolution, 2018](https://doi.org/10.1111/2041-210X.13031)). Un conjunto urbano reciente con AudioMoth confirma que la cobertura depende de la frecuencia, la amplitud y el entorno construido ([Scientific Data, 2025](https://www.nature.com/articles/s41597-025-05481-z)).

Por ello, para convertir el círculo orientativo en un radio efectivo debe realizarse una calibración de campo con reproducciones conocidas a varias distancias y direcciones, bajo condiciones representativas, documentando el umbral de detección. Hasta entonces, los resultados describen exclusivamente las grabaciones obtenidas en el punto del nodo. Del mismo modo, NDSI se presenta como el balance de las bandas configuradas (0–1 kHz frente a 1–10 kHz) conforme a la [implementación de `soundscape_index` de scikit-maad](https://scikit-maad.github.io/generated/maad.features.soundscape_index.html), sin equiparar automáticamente sus extremos con «urbano» o «natural».

Las métricas acústicas corregidas se guardan con la versión `maad-v2`: ACI, ADI, AEI y BIO se calculan sobre amplitud; NDSI y la entropía frecuencial sobre potencia; Ht sobre la envolvente temporal. El panel utiliza únicamente las últimas 100 muestras `maad-v2` del mismo nodo y muestra el periodo y el número de capturas. Las filas anteriores quedan identificadas como `legacy-v1` y se conservan para trazabilidad, pero no se mezclan con la nueva serie.

En una actualización existente debe desplegarse y reiniciarse primero el backend, comprobando que la respuesta de `/audio-metrics/` conserva `acoustic_metrics_version`; después se actualiza y reinicia la Raspberry. Este orden evita que un backend antiguo acepte los valores nuevos pero descarte su versión de cálculo.

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
