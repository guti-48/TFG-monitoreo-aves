import os, sys, shutil
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from . import models, database, schemas
from backend.analisisBiodiversidad import obetenerDatosMapa, obtener_reporte_biodiversidad

current_file = Path(__file__).resolve()
backend_dir = current_file.parent.parent
sys.path.append(str(backend_dir)) 


## Creamos las tablas automaticamente en la base de datos
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="BirdMonitor API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite conexiones desde cualquier origen
    allow_credentials=True,
    allow_methods=["*"],  # Permite GET, POST...
    allow_headers=["*"],
)

current_file = Path(__file__).resolve()
# Subimos 3 niveles: app -> backend -> monitoreo_aves
project_root = current_file.parent.parent.parent
#Construimos la ruta bajando a hardware
SPECTOGRAM_DIR = project_root / "hardware" / "raspberry_pi" / "spectrograms"
SERVER_AUDIO_DIR = os.path.join(project_root, "hardware", "raspberry_pi", "records")

os.makedirs(SERVER_AUDIO_DIR, exist_ok=True)
os.makedirs(SPECTOGRAM_DIR, exist_ok=True) #creamos carpeta si no existe

#carpeta montada en la ruta /spectograms
app.mount("/spectrograms", StaticFiles(directory=SPECTOGRAM_DIR), name="spectrograms")

@app.post('/upload/')
async def subida_archivos(audio: UploadFile = File(None), specto: UploadFile = File(None)):
    '''Endpoints para poder recibir audio y espectrogramas desde la raspberry pi'''
    saved_files = []
    
    if audio:
        audio_path = os.path.join(SERVER_AUDIO_DIR, audio.filename)
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)
        saved_files.append(audio.filename)
        
    if specto:
        img_path = os.path.join(SPECTOGRAM_DIR, specto.filename)
        with open(img_path, "wb") as buffer:
            shutil.copyfileobj(specto.file, buffer)
        saved_files.append(specto.filename)

    if not saved_files:
        raise HTTPException(status_code=400, detail="No se enviaron archivos")
        
    return {"message": "Archivos subidos correctamente", "files": saved_files}


## PRIMER ENDPOINT --> REGISTRAR UN DISPOSITIVO
@app.post("/devices/", response_model=schemas.DeviceCreate) 
def create_device(device: schemas.DeviceCreate, db: Session = Depends(database.get_db)):
    # primero verificaremos de su existencia
    db_device = db.query(models.Device).filter(models.Device.name == device.name).first()
    if db_device:
        if not db_device.location:
            db_device.location = device.location
            db.commit()
            db.refresh(db_device)
        return db_device

    new_device = models.Device(name=device.name, location=device.location)
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
def read_detections(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
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

@app.get("/")
def read_root():
    return {"message": "Bienvenido al Sistema de Monitoreo de Aves"}

