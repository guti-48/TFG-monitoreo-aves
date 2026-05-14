import os, sys, re
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from . import models, database, schemas
from backend.analisisBiodiversidad import obetenerDatosMapa, obtener_reporte_biodiversidad, obetenerActividadDiaria

current_file = Path(__file__).resolve()
backend_dir = current_file.parent.parent
project_root = current_file.parent.parent.parent

sys.path.append(str(backend_dir)) 

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

app = FastAPI(title="BirdMonitor API", version="1.0")

cors_origins_env = os.getenv("BIRDMONITOR_CORS_ORIGINS", "").strip()

if cors_origins_env:
    cors_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
else:
    cors_origins = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://100.98.248.58:8000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

current_file = Path(__file__).resolve()

#integro el fronted en el backend para tenerlo todo en el mismo servidor
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "../../frontend")

#carpeta montada en la ruta /spectograms
app.mount("/spectrograms", StaticFiles(directory=SPECTOGRAM_DIR), name="spectrograms")

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
            db.commit()
            db.refresh(db_device)

        return db_device

    new_device = models.Device(
        name=device.name,
        location=nueva_ubicacion if nueva_ubicacion not in ubicaciones_invalidas else "Desconocida"
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
@app.get("/detections/")
def read_detections(skip: int = 0, limit: int = 500, db: Session = Depends(database.get_db)):
    detections = db.query(models.Detection).order_by(models.Detection.timestamp.desc()).offset(skip).limit(limit).all()
    return detections

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