from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from . import database, models, schemas


router = APIRouter()


@router.post("/audio-metrics/", response_model=schemas.AudioMetricResponse)
def create_audio_metric(
    metric: schemas.AudioMetricCreate,
    db: Session = Depends(database.get_db),
):
    db_device = db.query(models.Device).filter(
        models.Device.name == metric.device_name
    ).first()

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
        device_id=db_device.id,
    )

    db.add(new_metric)
    db.commit()
    db.refresh(new_metric)
    return new_metric


@router.get("/audio-metrics/", response_model=list[schemas.AudioMetricResponse])
def read_audio_metrics(
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(database.get_db),
):
    return (
        db.query(models.AudioMetric)
        .order_by(models.AudioMetric.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )