from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from . import models, database, schemas

## Creamos las tablas automaticamente en la base de datos
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="BirdMonitor API", version="1.0")

## PRIMER ENDPOINT --> REGISTRAR UN DISPOSITIVO
@app.post("/devices/", response_model=schemas.DeviceCreate) 
def create_device(device: schemas.DeviceCreate, db: Session = Depends(database.get_db)):
    # primero verificaremos de su existencia
    db_device = db.query(models.Device).filter(models.Device.name == device.name).first()
    if db_device:
        raise HTTPException(status_code=400, detail="Dispositivo ya registrado")

    new_device = models.Device(name=device.name, Location=device.location)
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
        db_device = models.Device(name=detection.device_name, Location="Desconocida")
        db.add(db_device)
        db.commit()
        db.refresh(db_device)

    # guadaremos la deteccion
    new_detection = models.Detection(
        species=detection.species,
        confidence=detection.confidence,
        timestamp=detection.timestamp,
        filename=detection.filename,
        device_id=db_device.id
    )

    db.add(new_detection)
    db.commit()
    db.refresh(new_detection)
    return new_detection

## TERCER ENDPOINT --> OBTENER DETECCIONES TODAS LAS DETECCIONES PARA PODER OBSERVARLAS
@app.get("/detections/")
def read_detections(skip: int = 0, limit: int = 10, db: Session = Depends(database.get_db)):
    detections = db.query(models.Detection).offset(skip).limit(limit).all()
    return detections

@app.get("/")
def read_root():
    return {"message": "Bienvenido al Sistema de Monitoreo de Aves"}

