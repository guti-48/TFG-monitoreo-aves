# Sistema IoT de Monitoreo Acústico de Aves (TFG)

Este proyecto consiste en el diseño, desarrollo e implementación de un sistema distribuido para la detección, clasificación y monitoreo de avifauna mediante análisis acústico pasivo (PAM) e Inteligencia Artificial.

El sistema utiliza nodos de computación en el borde (Edge Computing) basados en Raspberry Pi para procesar audio en tiempo real, implementando una arquitectura híbrida que permite el almacenamiento local de datos científicos (incluyendo análisis de contaminación acústica) y la contribución simultánea a redes de ciencia ciudadana (BirdWeather).

## Estado del Proyecto

El sistema se encuentra en fase de validación técnica con funcionalidad completa "End-to-End".

### Funcionalidades Implementadas

* **Captura y Procesamiento de Señal:**
    * Grabación de audio en bucles continuos de 10 segundos a una frecuencia de muestreo de 48kHz.
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
Para ejecutar este proyecto e instalar todas las dependencias necesarias, es necesario que sea creado un entorno virtual.
Este entorno debera ser creado para 3 terminales distintos.
Los siguientes pasos serviran para inciar todo tanto desde Windows como desde Mac.

1. Crearemos y activaremos un Entorno Virtual, en mi caso dentro de la carpeta /monitoreo_aves:
    Para Linux/Mac:

```bash
    python3 -m venv venv
    source venv/bin/activate
```
    
    Para Windows:
```bash
    python -m venv venv
    source ./venv/Scripts/activate
```

2. Para instalar las dependencias deberemos ejecutar:

```bash
    pip install -r requirements.txt
```

3. Aqui cada linea que pondre sera para acceder a un terminal distinto en donde tendremos que correr distintas cosas:

```bash
    uvicorn backend.app.main:app --reload --host 127.0.0.1
    cd /hardware/raspbery_py/
        python mainNode.py
    cd /frontend/
        python -m http.server 5500
```

4. Es importante tener eliminada previamente nuestra base de datos que se encuentra dentro de /backend/app para que podamos ver
desde nuestro navegador.

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
