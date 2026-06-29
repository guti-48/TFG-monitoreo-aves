import os, sys, re, json
from datetime import datetime, timezone
from threading import Lock
from pydantic import BaseModel
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload
from . import models, database, schemas

current_file = Path(__file__).resolve()
backend_dir = current_file.parent.parent
project_root = current_file.parent.parent.parent

for path in (project_root, backend_dir):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.append(path_str)

try:
    from backend.analisisBiodiversidad import obetenerDatosMapa, obtener_reporte_biodiversidad, obetenerActividadDiaria
except ModuleNotFoundError:
    from analisisBiodiversidad import obetenerDatosMapa, obtener_reporte_biodiversidad, obetenerActividadDiaria

SPECTOGRAM_DIR = project_root / "hardware" / "raspberry_pi" / "spectrograms"
SERVER_AUDIO_DIR = project_root / "hardware" / "raspberry_pi" / "records"

os.makedirs(SERVER_AUDIO_DIR, exist_ok=True)
os.makedirs(SPECTOGRAM_DIR, exist_ok=True)

# filtro de capacidad permitida de subida
MAX_AUDIO_BYTES = 100 * 1024 * 1024      
MAX_IMAGE_BYTES = 20 * 1024 * 1024       

ALLOWED_AUDIO_EXTENSIONS = {".wav"}
ALLOWED_IMAGE_EXTENSIONS = {".png"}

## Creamos las tablas automaticamente en la base de datos
models.Base.metadata.create_all(bind=database.engine)

def asegurar_esquema_runtime() -> None:
    with database.engine.begin() as conn:
        columnas_devices = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(devices)").fetchall()
        }

        if "lat" not in columnas_devices:
            conn.exec_driver_sql("ALTER TABLE devices ADD COLUMN lat FLOAT")

        if "lon" not in columnas_devices:
            conn.exec_driver_sql("ALTER TABLE devices ADD COLUMN lon FLOAT")

asegurar_esquema_runtime()

app = FastAPI(title="BirdMonitor API", version="1.0")

cors_origins_env = os.getenv("BIRDMONITOR_CORS_ORIGINS", "").strip()

if cors_origins_env:
    cors_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
else:
    cors_origins = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://100.98.248.58:8000",
        "http://localhost",
        "http://127.0.0.1",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"http://localhost:\d+|http://127\.0\.0\.1:\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

current_file = Path(__file__).resolve()

#integro el fronted en el backend para tenerlo todo en el mismo servidor
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "../../frontend")

#carpeta montada en la ruta /spectograms
app.mount("/spectrograms", StaticFiles(directory=SPECTOGRAM_DIR), name="spectrograms")
app.mount("/records", StaticFiles(directory=SERVER_AUDIO_DIR), name="records")

def normalizar_nombre_archivo(filename: str, extensiones_permitidas: set[str]) -> str:
    """
    Añadimos seguridad ante posibles 'ataques'
    """
    if not filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo vacío")

    nombre = Path(filename).name
    nombre = re.sub(r"[^A-Za-z0-9_.-]", "_", nombre)

    extension = Path(nombre).suffix.lower()

    if extension not in extensiones_permitidas:
        raise HTTPException(
            status_code=400,
            detail=f"Extensión no permitida: {extension}"
        )

    if not nombre:
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido")

    return nombre


async def guardar_upload_seguro(
    upload: UploadFile,
    destino_dir: Path,
    extensiones_permitidas: set[str],
    max_bytes: int
) -> str:
    """
    Guarda un UploadFile por bloques, validando nombre, extensión y tamaño.
    """
    nombre_seguro = normalizar_nombre_archivo(upload.filename, extensiones_permitidas)

    destino_dir = destino_dir.resolve()
    destino_path = (destino_dir / nombre_seguro).resolve()

    try:
        destino_path.relative_to(destino_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ruta de archivo no permitida")

    bytes_leidos = 0

    try:
        with open(destino_path, "wb") as buffer:
            while True:
                chunk = await upload.read(1024 * 1024)

                if not chunk:
                    break

                bytes_leidos += len(chunk)

                if bytes_leidos > max_bytes:
                    try:
                        destino_path.unlink()
                    except FileNotFoundError:
                        pass

                    raise HTTPException(
                        status_code=413,
                        detail=f"Archivo demasiado grande: {nombre_seguro}"
                    )

                buffer.write(chunk)

    finally:
        await upload.close()

    return nombre_seguro

## para automatización de la escucha, guardamos el estdo en un json par su mejor control
STREAM_CONTROL_FILE = current_file.parent / "stream_control.json"
stream_lock = Lock()

CONFIGURED_STREAM_BASE_URL = os.getenv("BIRDMONITOR_STREAM_BASE_URL")

DEFAULT_STREAM_PATH = os.getenv(
    "BIRDMONITOR_STREAM_PATH",
    "birdmonitor-audio"
).strip("/")

def _stream_base_url(request: Request | None = None) -> str:
    if CONFIGURED_STREAM_BASE_URL:
        return CONFIGURED_STREAM_BASE_URL.rstrip("/")

    if request is None:
        return f"http://127.0.0.1:8888"

    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    return f"{scheme}://{host}:8888"


def _apply_stream_urls(current: dict, request: Request | None = None) -> dict:
    base_url = _stream_base_url(request)
    current["hls_url"] = f"{base_url}/{DEFAULT_STREAM_PATH}/index.m3u8"
    current["page_url"] = f"{base_url}/{DEFAULT_STREAM_PATH}/"
    return current

class StreamControlUpdate(BaseModel):
    node_name: str = "birdmonitor"
    stream_enabled: bool


class StreamStatusUpdate(BaseModel):
    node_name: str = "birdmonitor"
    running: bool
    detail: str = ""


def _stream_default_state(node_name: str) -> dict:
    return _apply_stream_urls({
        "node_name": node_name,
        "stream_enabled": False,
        "actual_running": False,
        "detail": "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_status_at": None,
    })


def _load_stream_state() -> dict:
    if not STREAM_CONTROL_FILE.exists():
        return {}

    try:
        with open(STREAM_CONTROL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_stream_state(state: dict) -> None:
    with open(STREAM_CONTROL_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

@app.get("/stream/control")
def get_stream_control(request: Request, node_name: str = "birdmonitor"):
    """
    Devuelve el estado deseado y real conocido del streaming para un nodo.
    """
    with stream_lock:
        state = _load_stream_state()

        if node_name not in state:
            state[node_name] = _stream_default_state(node_name)
            _save_stream_state(state)

        state[node_name] = _apply_stream_urls(state[node_name], request)

        return state[node_name]


@app.post("/stream/control")
def set_stream_control(payload: StreamControlUpdate, request: Request):
    """
    Cambia el estado deseado del streaming.
    El dashboard llama a este endpoint.
    La Raspberry lo consulta mediante streamSupervisor.py.
    """
    with stream_lock:
        state = _load_stream_state()

        current = state.get(payload.node_name, _stream_default_state(payload.node_name))
        current["stream_enabled"] = payload.stream_enabled
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        current = _apply_stream_urls(current, request)

        state[payload.node_name] = current
        _save_stream_state(state)

        return current


@app.post("/stream/status")
def set_stream_status(payload: StreamStatusUpdate):
    """
    La Raspberry informa del estado real de birdstream.service.
    """
    with stream_lock:
        state = _load_stream_state()

        current = state.get(payload.node_name, _stream_default_state(payload.node_name))
        current["actual_running"] = payload.running
        current["detail"] = payload.detail
        current["last_status_at"] = datetime.now(timezone.utc).isoformat()

        state[payload.node_name] = current
        _save_stream_state(state)

        return current


@app.post("/upload/")
async def subida_archivos(
    audio: UploadFile | None = File(None),
    specto: UploadFile | None = File(None)
):
    """Recibe audio WAV y espectrogramas PNG desde la Raspberry Pi."""
    saved_files = []

    if audio:
        nombre_audio = await guardar_upload_seguro(
            upload=audio,
            destino_dir=SERVER_AUDIO_DIR,
            extensiones_permitidas=ALLOWED_AUDIO_EXTENSIONS,
            max_bytes=MAX_AUDIO_BYTES
        )
        saved_files.append(nombre_audio)

    if specto:
        nombre_img = await guardar_upload_seguro(
            upload=specto,
            destino_dir=SPECTOGRAM_DIR,
            extensiones_permitidas=ALLOWED_IMAGE_EXTENSIONS,
            max_bytes=MAX_IMAGE_BYTES
        )
        saved_files.append(nombre_img)

    if not saved_files:
        raise HTTPException(status_code=400, detail="No se enviaron archivos")

    print(f"Archivos recibidos desde nodo: {saved_files}")

    return {
        "message": "Archivos subidos correctamente",
        "files": saved_files
    }


## PRIMER ENDPOINT --> REGISTRAR UN DISPOSITIVO
@app.post("/devices/", response_model=schemas.DeviceCreate)
def create_device(device: schemas.DeviceCreate, db: Session = Depends(database.get_db)):
    db_device = db.query(models.Device).filter(models.Device.name == device.name).first()

    nueva_ubicacion = (device.location or "").strip()

    ubicaciones_invalidas = {
        "",
        "Desconocida",
        "Ubicacion_Desconocida",
        "Ubicación_Desconocida",
        "unknown"
    }

    if db_device:
        # Actualiza la ubicación si llega una ubicación válida y distinta
        if nueva_ubicacion not in ubicaciones_invalidas and db_device.location != nueva_ubicacion:
            print(f"Actualizando ubicación de {device.name}: {db_device.location} -> {nueva_ubicacion}")
            db_device.location = nueva_ubicacion

        if device.lat is not None:
            db_device.lat = device.lat

        if device.lon is not None:
            db_device.lon = device.lon

        if db.is_modified(db_device):
            db.commit()
            db.refresh(db_device)

        return db_device

    new_device = models.Device(
        name=device.name,
        location=nueva_ubicacion if nueva_ubicacion not in ubicaciones_invalidas else "Desconocida",
        lat=device.lat,
        lon=device.lon
    )
    db.add(new_device)
    db.commit()
    db.refresh(new_device)
    return new_device

## SEGUNDO ENDPOINT --> SUBIR UNA DETECCION
@app.post("/detections/", response_model=schemas.DetectionResponse)
def create_detection(detection: schemas.DetectionCreate, db: Session = Depends(database.get_db)):
    # primero buscaremos el id del dispositivo por su nombre
    db_device = db.query(models.Device).filter(models.Device.name == detection.device_name).first()

    # su el dispoistivo no existe los creamos automaticamente
    if not db_device:
        db_device = models.Device(name=detection.device_name, location="Desconocida")
        db.add(db_device)
        db.commit()
        db.refresh(db_device)

    existing_detection = (
        db.query(models.Detection)
        .filter(
            models.Detection.device_id == db_device.id,
            models.Detection.timestamp == detection.timestamp,
            models.Detection.species == detection.species,
            models.Detection.filename == detection.filename,
        )
        .first()
    )

    if existing_detection:
        return existing_detection

    # guadaremos la deteccion
    new_detection = models.Detection(
        species=detection.species,
        confidence=detection.confidence,
        timestamp=detection.timestamp,
        filename=detection.filename,
        device_id=db_device.id,
        amplitude=detection.amplitude
    )

    db.add(new_detection)
    db.commit()
    db.refresh(new_detection)
    return new_detection

## TERCER ENDPOINT --> OBTENER DETECCIONES TODAS LAS DETECCIONES PARA PODER OBSERVARLAS
@app.get("/detections/", response_model=list[schemas.DetectionResponse])
def read_detections(skip: int = 0, limit: int = 500, db: Session = Depends(database.get_db)):
    detections = db.query(models.Detection).options(joinedload(models.Detection.review)).order_by(models.Detection.timestamp.desc()).offset(skip).limit(limit).all()
    return detections

## ENDPOINTS relacionados con la revision humana de dettecines
@app.patch("/detections/{detection_id}/review", response_model=schemas.DetectionReviewResponse)
def update_detection_review(
    detection_id: int,
    review_data: schemas.DetectionReviewUpdate,
    db: Session = Depends(database.get_db)
):
    """
    Crea o actualiza la revisión humana de una detección automática.
    No modifica la especie ni la confianza originales generadas por BirdNET.
    """
    detection = (
        db.query(models.Detection)
        .filter(models.Detection.id == detection_id)
        .first()
    )

    if detection is None:
        raise HTTPException(status_code=404, detail="Detection not found")

    if review_data.status == "corrected" and not review_data.corrected_species:
        raise HTTPException(
            status_code=400,
            detail="corrected_species is required when status is corrected"
        )

    review = (
        db.query(models.DetectionReview)
        .filter(models.DetectionReview.detection_id == detection_id)
        .first()
    )

    now = datetime.now(timezone.utc)

    if review is None:
        review = models.DetectionReview(
            detection_id=detection_id,
            status=review_data.status,
            corrected_species=review_data.corrected_species,
            note=review_data.note,
            reviewer=review_data.reviewer,
            reviewed_at=now,
            updated_at=now,
        )
        db.add(review)
    else:
        review.status = review_data.status
        review.corrected_species = review_data.corrected_species
        review.note = review_data.note
        review.reviewer = review_data.reviewer
        review.reviewed_at = now
        review.updated_at = now

    db.commit()
    db.refresh(review)

    return review

@app.get("/detections/{detection_id}/review", response_model=schemas.DetectionReviewResponse)
def get_detection_review(
    detection_id: int,
    db: Session = Depends(database.get_db)
):
    """
    Devuelve la revisión humana asociada a una detección concreta.
    """
    detection = (
        db.query(models.Detection)
        .filter(models.Detection.id == detection_id)
        .first()
    )

    if detection is None:
        raise HTTPException(status_code=404, detail="Detection not found")

    review = (
        db.query(models.DetectionReview)
        .filter(models.DetectionReview.detection_id == detection_id)
        .first()
    )

    if review is None:
        raise HTTPException(status_code=404, detail="Detection review not found")

    return review

@app.get("/species/options")
def get_species_options(db: Session = Depends(database.get_db)):
    """
    Devuelve la lista de especies detectadas hasta ahora.
    Sirve para el selector de especie corregida.
    """
    species_rows = (
        db.query(models.Detection.species)
        .filter(models.Detection.species.isnot(None))
        .distinct()
        .order_by(models.Detection.species.asc())
        .all()
    )

    return [row[0] for row in species_rows if row[0]]

## ENDPOINTS --> relacionados ocn la metrica de escucha
@app.post("/audio-metrics/", response_model=schemas.AudioMetricResponse)
def create_audio_metric(metric: schemas.AudioMetricCreate, db: Session = Depends(database.get_db)):
    """
    Guarda una muestra acústica agregada de un ciclo de grabación.
    No representa una detección de ave, representa el estado acústico del entorno.
    """
    db_device = db.query(models.Device).filter(models.Device.name == metric.device_name).first()

    if not db_device:
        db_device = models.Device(name=metric.device_name, location="Desconocida")
        db.add(db_device)
        db.commit()
        db.refresh(db_device)

    existing_metric = (
        db.query(models.AudioMetric)
        .filter(
            models.AudioMetric.device_id == db_device.id,
            models.AudioMetric.timestamp == metric.timestamp,
            models.AudioMetric.filename == metric.filename,
        )
        .first()
    )

    if existing_metric:
        return existing_metric

    new_metric = models.AudioMetric(
        timestamp=metric.timestamp,
        filename=metric.filename,
        sample_rate=metric.sample_rate,
        duration=metric.duration,
        rms=metric.rms,
        aci=metric.aci,
        adi=metric.adi,
        aei=metric.aei,
        bio=metric.bio,
        ndsi=metric.ndsi,
        ht=metric.ht,
        hf=metric.hf,
        h=metric.h,
        device_id=db_device.id
    )

    db.add(new_metric)
    db.commit()
    db.refresh(new_metric)
    return new_metric


@app.get("/audio-metrics/", response_model=list[schemas.AudioMetricResponse])
def read_audio_metrics(skip: int = 0, limit: int = 500, db: Session = Depends(database.get_db)):
    """Devuelve las métricas acústicas agregadas más recientes."""
    metrics = (
        db.query(models.AudioMetric)
        .order_by(models.AudioMetric.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return metrics

'''
CUARTO ENDPOINT --> OBTENER REPORTE DE BIODIVERSIDAD
Esta API nos devolvera el reporte de biodeiversidad generado con los datos almacenados en la base de datos,
es el siguiente paso de todo el proyecto.
'''
@app.get("/analytics/biodiversity")
def get_biodiversity_report():
    '''
    Calculamos los indices ecologicos en tiempo real basado en las detecciones almacenadas en la base de datos
    '''
    try:
        reporte = obtener_reporte_biodiversidad()
        return reporte
    except Exception as e:
        print(f"Error al obtener el reporte de biodiversidad: {e}")
        return []
    
'''QUINTO ENDPOINT --> OBTENER DATOS PARA EL MAPA DE CALOR'''
@app.get("/analytics/map")
def get_map_data():
    try:
        return obetenerDatosMapa()
    except Exception as e:
        print(f"Error en mapa: {e}")
        return {"error": str(e)}
    

'''SEXTO ENDPOINT --> OBTENEMOS ACTIVIDAD DIARIA POR HORAS'''
@app.get("/analytics/daily-activity")
def get_daily_activity(date: str):
    """
    Recibe una fecha en formato YYYY-MM-DD y devuelve el recuento de aves por cada hora del día para la generación de gráficas y CSV.
    """
    try:
        return obetenerActividadDiaria(date)
    except Exception as e:
        print(f"Error generando informe diario: {e}")
        return []
    
@app.get("/devices/")
def get_devices(db: Session = Depends(database.get_db)):
    """Devuelve la lista de dispositivos reales registrados en la base de datos"""
    return db.query(models.Device).all()

'''
@app.get("/")
def read_root():
    return {"message": "Bienvenido al Sistema de Monitoreo de Aves"}
'''

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")