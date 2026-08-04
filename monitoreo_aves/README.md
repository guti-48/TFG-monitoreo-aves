# Sistema IoT de Monitoreo Acústico de Aves (TFG)

Este proyecto consiste en el diseño, desarrollo e implementación de un sistema distribuido para la detección, clasificación y monitoreo de avifauna mediante análisis acústico pasivo (PAM) e Inteligencia Artificial.

El sistema utiliza nodos de computación en el borde (Edge Computing) basados en Raspberry Pi para procesar audio en tiempo real, implementando una arquitectura híbrida que permite el almacenamiento local de datos científicos (incluyendo análisis de contaminación acústica) y la contribución simultánea a redes de ciencia ciudadana (BirdWeather).

La evolución de autenticación, privacidad y endurecimiento del sistema se
documenta en [`docs/INFORME_SEGURIDAD.md`](docs/INFORME_SEGURIDAD.md).
La organización interna del backend se describe en
[`docs/ARQUITECTURA_CODIGO.md`](docs/ARQUITECTURA_CODIGO.md).
La instalación segura se divide en dos perfiles:
[`red local`](docs/INSTALACION_LOCAL.md) y
[`Tailscale`](docs/INSTALACION_TAILSCALE.md). La política y las limitaciones
de seguridad se recogen en [`SECURITY.md`](SECURITY.md).

## Guia de instalacion y configuracion

El proyecto queda preparado para clonarse y ejecutarse con un servidor central en Windows o macOS. La Raspberry Pi actua como nodo Edge y debe apuntar a la IP real del servidor central, normalmente una IP LAN o una IP/hostname de Tailscale.

### Arquitectura de despliegue

```text
Raspberry Pi / nodo Edge              Servidor central                       Clientes
┌────────────────────────┐           ┌─────────────────────────────┐         ┌────────────────────┐
│ microfono → ALSA       │           │ FastAPI :8000               │────────▶│ navegador / móvil  │
│ ├─ mainNode / BirdNET  │── datos ─▶│ ├─ API, archivos y sesión  │         │ dashboard :8000    │
│ └─ FFmpeg autenticado  │── RTSP ──▶│ └─ proxy HLS autenticado   │────────▶│ escucha HLS        │
│ supervisor.py          │           │ MediaMTX                    │         │ VLC RTSP con clave │
└────────────────────────┘           │ ├─ RTSP :8554 autenticado   │         └────────────────────┘
                                     │ └─ HLS 127.0.0.1:8888      │
                                     └─────────────────────────────┘
```

La Raspberry captura y analiza el microfono, y publica **una sola señal** RTSP.
FastAPI y MediaMTX se ejecutan en el servidor central. MediaMTX transforma esa
señal en HLS y la distribuye a todos los oyentes; abrir dos móviles no duplica
la captura, BirdNET ni el proceso FFmpeg de la Raspberry.

Reglas importantes de red:

* `127.0.0.1` y `localhost` solo sirven desde la misma maquina.
* El backend escucha en `0.0.0.0`, pero el middleware y el Firewall sólo aceptan el modo de red elegido.
* Desde la Raspberry u otro ordenador usa exactamente la IP LAN o Tailscale configurada con `configure_network_mode.py`.
* RTSP se liga a esa IP exacta; HLS sólo escucha en `127.0.0.1` y sale mediante el dashboard autenticado.
* Si cambias el servidor o el modo de red, vuelve a ejecutar el configurador y el aplicador de red; no edites múltiples archivos a mano.
* Varios clientes pueden abrir el mismo dashboard a la vez: Mac, Windows, movil o tablet solo necesitan entrar a `http://IP_DEL_SERVIDOR:8000`.
* Para VLC se usa la URL RTSP con credenciales que muestra el dashboard tras iniciar sesión; nunca la IP de la Raspberry.

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

No hace falta instalar una app móvil. El dashboard web responsive constituye el
cliente oficial tanto en ordenador como en móvil y concentra revisión, escucha,
analítica y exportaciones. El antiguo cliente Flutter se conserva únicamente
como referencia durante la transición y no se amplía con nuevas funciones.
Al entrar desde la misma Wi-Fi se usa la IP LAN del servidor; desde otra red se
usa su IP Tailscale y el móvil también debe tener Tailscale conectado.

Para un stream llamado `birdmonitor-audio`, las direcciones son:

```text
Dashboard y escucha móvil:  http://IP_DEL_SERVIDOR:8000
Manifiesto HLS protegido:    http://IP_DEL_SERVIDOR:8000/stream/hls/birdmonitor-audio/index.m3u8
VLC / RTSP:                  URL autenticada mostrada por el dashboard
```

El puerto HLS 8888 no se abre a otros dispositivos: MediaMTX sólo lo escucha
en `127.0.0.1` y FastAPI entrega los segmentos después de comprobar la sesión.
RTSP exige credenciales diferentes para publicación y lectura.

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

### Seguridad inicial obligatoria

Antes de reiniciar el backend por primera vez, crea la cuenta administradora y
el token exclusivo de la Raspberry:

```powershell
.\venv\Scripts\python.exe scripts\configure_security.py
```

En macOS o Linux:

```bash
./venv/bin/python scripts/configure_security.py
```

El asistente solicita una contraseña de al menos 12 caracteres y muestra una
sola vez `BIRDMONITOR_NODE_API_TOKEN`. Añade esa línea al archivo
`hardware/raspberry_pi/birdmonitor.env` de la Raspberry antes de reiniciar el
nodo. El servidor guarda únicamente hashes de contraseña y token dentro de
`backend/birdmonitor.env`, archivo excluido de Git.

Después, el navegador redirige a `/login`; todas las rutas del dashboard,
audios, exportaciones y operaciones administrativas requieren una sesión. El
token del nodo solo puede registrar el dispositivo, enviar detecciones y
métricas, subir evidencias y comunicar el estado del stream.

Elige de forma explícita cómo se conectarán los dispositivos. Para una red
doméstica privada:

```powershell
.\venv\Scripts\python.exe scripts\configure_network_mode.py `
  --mode local `
  --server-host IP_LAN_SERVIDOR
```

Para ubicaciones distintas:

```powershell
.\venv\Scripts\python.exe scripts\configure_network_mode.py `
  --mode tailscale `
  --server-host IP_TAILSCALE_SERVIDOR
```

Después genera las identidades independientes del streaming:

```powershell
.\venv\Scripts\python.exe scripts\configure_stream_security.py
```

El comando muestra una sola vez la contraseña que FFmpeg usará para publicar.
En la Raspberry se instala sin escribirla en el historial, indicando el mismo
modo y la misma IP:

```bash
sudo python3 scripts/raspberry_pi/configure_stream_publisher.py \
  --network-mode local|tailscale \
  --server-host IP_DEL_SERVIDOR
```

Por último, aplica MediaMTX, el enlace a la interfaz y las reglas de Firewall
desde PowerShell como administrador:

```powershell
.\scripts\windows\apply_network_mode.ps1
```

El recorrido completo y las comprobaciones están en
[`docs/INSTALACION.md`](docs/INSTALACION.md).

Si el dashboard se publica con HTTPS, ejecuta el asistente con `--https` para
marcar la cookie como exclusiva de conexiones cifradas:

```powershell
.\venv\Scripts\python.exe scripts\configure_security.py --https
```

No abras el puerto 8000 en el router. Para acceso desde fuera de la red local,
usa Tailscale o una VPN equivalente.

Si una instalación anterior deja la tarea `BirdMonitor Backend` en estado
`Queued`, reconstruye únicamente esa tarea desde PowerShell como administrador:

```powershell
.\scripts\windows\repair_backend_task.ps1
```

El reparador no modifica MediaMTX, la base de datos ni los audios. Elimina la
instancia anterior antes de registrar el backend con privilegios limitados y
evita acumular arranques simultáneos. También permite que el servidor funcione
cuando Windows está usando batería, sin detenerlo al desconectar el cargador.

### 3. Colocar MediaMTX

MediaMTX no debe subirse a Git como binario. Cada persona debe descargar el binario de su sistema y colocarlo en la ruta esperada:

```text
monitoreo_aves/
└── tools/
    └── mediamtx/
        ├── mediamtx.secure.yml
        ├── mediamtx.exe              # Windows
        └── macos/
            └── mediamtx              # macOS darwin
```

El archivo `tools/mediamtx/mediamtx.secure.yml` sí forma parte de la
configuración del proyecto. No contiene secretos: MediaMTX delega la
autorización en el backend local. Los binarios, logs, credenciales y claves
generadas quedan ignorados por `.gitignore`.

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
| Servicio de streaming de la Raspberry | `scripts/raspberry_pi/configure_stream_publisher.py` adapta `birdstream.service` | Publicación RTSP autenticada hacia `IP_DEL_SERVIDOR:8554`, normalmente con path `birdmonitor-audio` |
| Dashboard web | Normalmente no se edita: `frontend/js/dashboard.js` selecciona nodo y path desde la vista de directo | HLS se consume por `/stream/hls/...` en el mismo puerto 8000 y exige sesión |
| Rutas HLS por nodo | `BIRDMONITOR_STREAM_PATH` o `BIRDMONITOR_STREAM_PATH_TEMPLATE`, leídas por `backend/app/core/config.py` | Ruta fija o plantilla, por ejemplo `{node_name}-audio` |
| HLS interno de MediaMTX | `BIRDMONITOR_MEDIAMTX_HLS_INTERNAL_URL` en `backend/birdmonitor.env` | `http://127.0.0.1:8888`; no se expone al navegador |
| Base RTSP anunciada | `BIRDMONITOR_STREAM_RTSP_BASE_URL` | `rtsp://IP_DEL_SERVIDOR:8554`; el backend añade la credencial sólo para el administrador |
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

La vista web carga los nodos registrados y permite seleccionar el nodo y el
path de MediaMTX desde la pantalla de escucha en directo. Si quieres fijar un
valor por defecto sin tocar `dashboard.js`, puedes definir antes de cargar el
script:

```html
<script>
window.BIRDMONITOR_CONFIG = {
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
* `tools/mediamtx/mediamtx.secure.yml` disponible como configuración versionada.
* `backend/birdmonitor.env` configurado mediante los asistentes de seguridad,
  modo de red y streaming.

Instalar y arrancar servicios:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows\install_birdmonitor_windows.ps1
```

El instalador:

* Detecta la ruta del proyecto.
* Busca `mediamtx.exe` y `mediamtx.secure.yml`.
* Crea scripts internos en `%LOCALAPPDATA%\BirdMonitor`.
* Crea las tareas programadas `BirdMonitor MediaMTX` y `BirdMonitor Backend`.
* Sustituye automaticamente tareas anteriores con esos mismos nombres; no es necesario borrarlas a mano.
* Programa ambas tareas para arrancar al iniciar sesión el usuario que realizó
  la instalación, sin guardar su contraseña de Windows.
* Reintenta el arranque si uno de los procesos termina con error.
* Arranca FastAPI en `8000`, RTSP autenticado en `8554` y HLS interno en
  `127.0.0.1:8888`.

Hay que ejecutar el instalador una vez en cada ordenador servidor y volver a ejecutarlo si cambia la ruta del repositorio, del entorno virtual o de MediaMTX. Actualizar el codigo con Git no registra por si solo las tareas de Windows.

Comprobar estado:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows\check_birdmonitor_windows.ps1
```

Aplicar por primera vez o cambiar el perfil de red y streaming:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\windows\apply_network_mode.ps1
```

Aplicar cambios posteriores del backend o de MediaMTX sin detener procesos
ajenos:

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
* `tools/mediamtx/macos/mediamtx` y `tools/mediamtx/mediamtx.secure.yml` disponibles.

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
http://IP_DEL_SERVIDOR:8000/stream/hls/birdmonitor-audio/index.m3u8
```

El navegador mostrará `/login` antes de cargar el dashboard. No es necesario
instalar un cliente adicional. Abrir directamente el manifiesto sin la cookie
de sesión devuelve `401`.

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
BIRDMONITOR_NODE_API_TOKEN=TOKEN_GENERADO_EN_EL_SERVIDOR
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

Para adaptar una unidad `birdstream.service` ya existente a la publicación
autenticada, ejecuta el instalador y pega la contraseña mostrada por
`configure_stream_security.py` cuando la solicite:

```bash
sudo python3 scripts/raspberry_pi/configure_stream_publisher.py \
  --network-mode local|tailscale \
  --server-host IP_DEL_SERVIDOR
```

El secreto queda fuera del repositorio y con permisos `600`. El instalador crea
una copia de seguridad y restaura la unidad anterior si el reinicio falla.

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
.\scripts\windows\check_birdmonitor_windows.ps1
```

macOS:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:8888 -sTCP:LISTEN
```

Backend:

```text
http://127.0.0.1:8000/health
```

La comprobación debe confirmar que 8000 responde, que 8554 está disponible y
que 8888 escucha sólo en loopback. El manifiesto HLS se valida internamente con
la credencial del proxy; desde un cliente se prueba iniciando sesión y abriendo
la vista **Escucha en directo**.

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
│   │   ├── main.py                 # Composición y arranque de FastAPI
│   │   ├── core/                   # Configuración, base de datos y seguridad
│   │   ├── domain/                 # Modelos SQLAlchemy y esquemas Pydantic
│   │   └── features/               # Routers y servicios por funcionalidad
│   ├── analisisBiodiversidad.py    # Motor matemático (Bioacústica + Ecología)
│   └── birdmonitor.env.example     # Plantilla de secretos del servidor
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
├── scripts/                        # Instalación, reparación y configuración
├── tools/mediamtx/                 # Configuración endurecida de MediaMTX
├── docs/                           # Memoria técnica, seguridad y arquitectura
└── requirements.txt                # Dependencias (FastAPI, scikit-maad...)
```
