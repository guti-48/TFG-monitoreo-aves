# Sistema IoT de Monitoreo Acústico de Aves (TFG)

Este proyecto consiste en el diseño, desarrollo e implementación de un sistema distribuido para la detección, clasificación y monitoreo de avifauna mediante análisis acústico pasivo (PAM) e Inteligencia Artificial.

El sistema utiliza nodos de computación en el borde (Edge Computing) basados en Raspberry Pi para procesar audio en tiempo real, implementando una arquitectura híbrida que permite el almacenamiento local de datos científicos (incluyendo análisis de contaminación acústica) y la contribución simultánea a redes de ciencia ciudadana (BirdWeather).

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

El servidor central se ejecuta en Windows 11 y el nodo Edge se ejecuta en Raspberry Pi OS Lite. Ambos dispositivos se comunican mediante Tailscale.

1. Crear y activar el entorno virtual dentro de la carpeta `monitoreo_aves`.

Para Windows PowerShell:

```bash
    python -m venv venv
    source ./venv/Scripts/activate
```

2. Para instalar las dependencias deberemos ejecutar:

```bash
    pip install -r requirements.txt
```

3. Ejecutar el servidor central desde la carpeta 'monitoreo de aves':

```bash
    uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

El dashboard queda disponible en:

```text
http://localhost:8000
```

Y desde la Raspberry Pi, mediante la IP de Tailscale del servidor Windows:

```text
http://100.98.248.58:8000
```

4. La base de datos SQLite se genera automáticamente si no existe. Solo debe eliminarse manualmente en caso de querer reiniciar completamente los datos históricos durante pruebas de desarrollo.

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
