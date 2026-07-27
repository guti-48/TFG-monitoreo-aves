from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from . import database, models, schemas


router = APIRouter()

UBICACIONES_INVALIDAS = {
    "",
    "Desconocida",
    "Ubicacion_Desconocida",
    "Ubicación_Desconocida",
    "unknown",
}


@router.post("/devices/", response_model=schemas.DeviceCreate)
def create_device(device: schemas.DeviceCreate, db: Session = Depends(database.get_db)):
    db_device = db.query(models.Device).filter(models.Device.name == device.name).first()
    nueva_ubicacion = (device.location or "").strip()

    if db_device:
        if (
            nueva_ubicacion not in UBICACIONES_INVALIDAS
            and db_device.location != nueva_ubicacion
        ):
            print(
                f"Actualizando ubicacion de {device.name}: "
                f"{db_device.location} -> {nueva_ubicacion}"
            )
            db_device.location = nueva_ubicacion

        if device.lat is not None:
            db_device.lat = device.lat

        if device.lon is not None:
            db_device.lon = device.lon

        if device.location_source is not None:
            db_device.location_source = device.location_source
            db_device.location_accuracy_m = device.location_accuracy_m
        elif device.location_accuracy_m is not None:
            db_device.location_accuracy_m = device.location_accuracy_m

        if db.is_modified(db_device):
            db.commit()
            db.refresh(db_device)

        return db_device

    new_device = models.Device(
        name=device.name,
        location=(
            nueva_ubicacion
            if nueva_ubicacion not in UBICACIONES_INVALIDAS
            else "Desconocida"
        ),
        lat=device.lat,
        lon=device.lon,
        location_source=device.location_source or "unknown",
        location_accuracy_m=device.location_accuracy_m,
    )
    db.add(new_device)
    db.commit()
    db.refresh(new_device)
    return new_device


@router.get("/devices/")
def get_devices(db: Session = Depends(database.get_db)):
    """Devuelve la lista de dispositivos reales registrados en la base de datos."""
    return db.query(models.Device).all()