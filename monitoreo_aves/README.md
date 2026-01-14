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
    * **Persistencia Local:** Almacenamiento de metadatos, niveles de amplitud y espectrogramas en base de datos relacional propia.
    * **Integración Cloud:** Envío selectivo de identificaciones positivas a la API de **BirdWeather** para el mapeo global de biodiversidad.

* **Interfaz de Visualización y Control (Dashboard):**
    * Aplicación web de página única para monitoreo en tiempo real.
    * Integración dinámica con la API de Wikipedia para recuperación de imágenes de especies.
    * Indicadores de calidad acústica basados en análisis RMS.
    * Módulo de exportación de datos históricos en formato CSV para análisis estadístico externo.

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
├── backend/                  # Módulo Servidor
│   ├── app/
│   │   ├── main.py           # Definición de API REST y endpoints
│   │   ├── models.py         # Modelos de Base de Datos (SQLAlchemy)
│   │   ├── schemas.py        # Esquemas de validación de datos
│   │   └── database.py       # Configuración de conexión SQL
│   └── birdmonitor.db        # Archivo de base de datos (Autogenerado)
│
├── frontend/                 # Módulo de Interfaz Web
│   ├── css/                  # Hojas de estilo
│   ├── js/                   # Lógica de cliente (Dashboard dinámico)
│   ├── images/               # Recursos gráficos estáticos
│   └── index.html            # Punto de entrada de la aplicación
│
├── hardware/raspberry_pi/    # Código fuente del Nodo Sensor
│   ├── model/                # Modelo BirdNET (.tflite) y etiquetas
│   ├── records/              # Almacenamiento temporal de audio (.wav)
│   ├── spectrograms/         # Almacenamiento temporal de imágenes
│   ├── analyzer.py           # Clase de abstracción para el modelo IA
│   └── mainNode.py           # Script principal de ejecución y control
│
└── requirements.txt          # Listado de dependencias del proyecto```
