from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from ...core import database
from ...domain import models, schemas
from ..locations import service as locations


router = APIRouter()


def _serialize_metric(metric: models.AudioMetric) -> dict:
    deployment = metric.deployment
    site = deployment.site if deployment else None
    return {
        column.name: getattr(metric, column.name)
        for column in models.AudioMetric.__table__.columns
    } | {
        "deployment_public_id": deployment.public_id if deployment else None,
        "site_id": site.id if site else None,
        "site_code": site.code if site else None,
        "site_name": site.name if site else None,
    }


@router.post("/audio-metrics/", response_model=schemas.AudioMetricResponse)
def create_audio_metric(
    metric: schemas.AudioMetricCreate,
    db: Session = Depends(database.get_db),
):
    db_device = locations.get_or_create_device(db, metric.device_name)
    deployment = locations.resolve_event_deployment(
        db,
        device=db_device,
        observed_at=metric.timestamp,
        site_code=metric.site_code,
        deployment_public_id=metric.deployment_public_id,
    )

    existing_metric = (
        db.query(models.AudioMetric)
        .filter(
            models.AudioMetric.deployment_id == deployment.id,
            models.AudioMetric.timestamp == metric.timestamp,
            models.AudioMetric.filename == metric.filename,
        )
        .first()
    )

    if existing_metric:
        if (
            metric.acoustic_metrics_version == "maad-v2"
            and existing_metric.acoustic_metrics_version != "maad-v2"
        ):
            existing_metric.sample_rate = metric.sample_rate
            existing_metric.duration = metric.duration
            existing_metric.rms = metric.rms
            existing_metric.peak = metric.peak
            existing_metric.clipping_ratio = metric.clipping_ratio
            existing_metric.dc_offset = metric.dc_offset
            existing_metric.noise_floor_rms = metric.noise_floor_rms
            existing_metric.quality_status = metric.quality_status
            existing_metric.quality_detail = metric.quality_detail
            existing_metric.mic_device = metric.mic_device
            existing_metric.birdnet_model = metric.birdnet_model
            existing_metric.birdnet_model_version = metric.birdnet_model_version
            existing_metric.birdnetlib_version = metric.birdnetlib_version
            existing_metric.acoustic_metrics_version = "maad-v2"
            existing_metric.aci = metric.aci
            existing_metric.adi = metric.adi
            existing_metric.aei = metric.aei
            existing_metric.bio = metric.bio
            existing_metric.ndsi = metric.ndsi
            existing_metric.ht = metric.ht
            existing_metric.hf = metric.hf
            existing_metric.h = metric.h
            db.commit()
            db.refresh(existing_metric)
        return _serialize_metric(existing_metric)

    new_metric = models.AudioMetric(
        timestamp=metric.timestamp,
        filename=metric.filename,
        sample_rate=metric.sample_rate,
        duration=metric.duration,
        rms=metric.rms,
        peak=metric.peak,
        clipping_ratio=metric.clipping_ratio,
        dc_offset=metric.dc_offset,
        noise_floor_rms=metric.noise_floor_rms,
        quality_status=metric.quality_status,
        quality_detail=metric.quality_detail,
        mic_device=metric.mic_device,
        birdnet_model=metric.birdnet_model,
        birdnet_model_version=metric.birdnet_model_version,
        birdnetlib_version=metric.birdnetlib_version,
        acoustic_metrics_version=metric.acoustic_metrics_version,
        aci=metric.aci,
        adi=metric.adi,
        aei=metric.aei,
        bio=metric.bio,
        ndsi=metric.ndsi,
        ht=metric.ht,
        hf=metric.hf,
        h=metric.h,
        device_id=db_device.id,
        deployment_id=deployment.id,
    )

    db.add(new_metric)
    db.commit()
    db.refresh(new_metric)
    return _serialize_metric(new_metric)


@router.get("/audio-metrics/", response_model=list[schemas.AudioMetricResponse])
def read_audio_metrics(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=2000),
    site_id: int | None = Query(default=None, ge=1),
    deployment_id: int | None = Query(default=None, ge=1),
    device_id: int | None = Query(default=None, ge=1),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(database.get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail="date_from no puede ser posterior a date_to",
        )

    query = (
        db.query(models.AudioMetric)
        .options(
            joinedload(models.AudioMetric.deployment).joinedload(
                models.Deployment.site
            )
        )
    )
    if site_id is not None:
        query = query.filter(
            models.AudioMetric.deployment.has(
                models.Deployment.site_id == site_id
            )
        )
    if deployment_id is not None:
        query = query.filter(models.AudioMetric.deployment_id == deployment_id)
    if device_id is not None:
        query = query.filter(models.AudioMetric.device_id == device_id)
    if date_from is not None:
        query = query.filter(models.AudioMetric.timestamp >= date_from)
    if date_to is not None:
        query = query.filter(models.AudioMetric.timestamp <= date_to)

    metrics = query.order_by(models.AudioMetric.timestamp.desc()).offset(
        skip
    ).limit(limit).all()
    return [_serialize_metric(metric) for metric in metrics]