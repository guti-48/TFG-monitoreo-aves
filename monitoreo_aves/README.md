# Sistema IoT de Monitoreo Acústico de Aves (TFG)

Este proyecto consiste en el diseño y desarrollo de un sistema distribuido para la detección, clasificación y monitoreo de aves mediante análisis acústico e Inteligencia Artificial (Deep Learning).

El sistema utiliza nodos de grabación basados en **Raspberry Pi** que ejecutan modelos ligeros de IA en el borde (Edge Computing) y envían los datos a un servidor central para su almacenamiento y visualización.

---

## Estado del Proyecto

Actualmente se han completado las fases de **Captura, Análisis, Backend e Integración**.

### Funcionalidades Implementadas
* **Captura de Audio:** Grabación continua en chunks de 10 segundos a 48kHz.
* **Preprocesamiento:** Generación automática de espectrogramas de Mel para visualización.
* **IA en el Borde (Edge AI):** Implementación del modelo **BirdNET-Lite (TFLite)** para inferencia offline.
    * Detección de +6,000 especies.
    * Filtrado por umbral de confianza (>50%).
* **Backend (API REST):** Servidor desarrollado con **FastAPI**.
    * Gestión de dispositivos (Nodos).
    * Recepción y validación de detecciones.
* **Persistencia de Datos:** Base de datos relacional (**SQLite** con SQLAlchemy) para almacenar histórico de detecciones.
* **Comunicación:** Sincronización automática Nodo --> Servidor mediante peticiones HTTP POST.

---

##  Arquitectura Técnica

El proyecto se divide en dos módulos principales:

### 1. Hardware Node (Cliente)
Ejecutado en Raspberry Pi (o PC para simulación).
* **Lenguaje:** Python 3.
* **Librerías Clave:** `librosa` (audio), `tensorflow-cpu` (IA), `requests` (comunicación).
* **Flujo:** Grabar -> Guardar WAV -> Inferencia TFLite -> JSON -> POST al Servidor.

### 2. Backend (Servidor)
* **Framework:** FastAPI.
* **ORM:** SQLAlchemy.
* **Base de Datos:** SQLite (Migrable a PostgreSQL).
* **Estándar de Datos:** Pydantic (Validación de esquemas y tipos).

---

##  Estructura del Proyecto

```text
monitoreo_aves/
├── backend/                  # Servidor Central
│   ├── app/
│   │   ├── main.py           # Endpoints de la API
│   │   ├── models.py         # Tablas de Base de Datos
│   │   ├── schemas.py        # Validación de datos (Pydantic)
│   │   └── database.py       # Conexión SQL
│   └── birdmonitoring.db     # Base de datos (Ignorada en git)
│
├── hardware/raspberry_pi/    # Código del Nodo Sensor
│   ├── model/                # Archivos del modelo BirdNET (.tflite y labels)
│   ├── records/              # Grabaciones .wav (Ignoradas en git)
│   ├── spectrograms/         # Imágenes .png (Ignoradas en git)
│   ├── analyzer.py           # Clase de inferencia (IA)
│   └── mainNode.py           # Script principal de ejecución
│
├── frontend/                 # Interfaz Web (En desarrollo)
└── requirements.txt          # Dependencias globales