from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ...core.migrations import legacy_deployment_public_id
from ...domain import models, schemas


logger = logging.getLogger(__name__)
INVALID_LOCATIONS = {
    "",
    "desconocida",
    "ubicacion_desconocida",
    "ubicación_desconocida",
    "unknown",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _comparable_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_or_create_device(db: Session, device_name: str) -> models.Device:
    name = (device_name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="device_name no puede estar vacio")

    device = db.query(models.Device).filter(models.Device.name == name).first()
    if device is None:
        device = models.Device(
            name=name,
            location="Desconocida",
            location_source="unknown",
        )
        db.add(device)
        db.flush()
    return device


def get_site_or_404(db: Session, site_id: int) -> models.Site:
    site = db.query(models.Site).filter(models.Site.id == site_id).first()
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


def _site_from_payload(payload: schemas.SiteCreate) -> models.Site:
    return models.Site(
        code=payload.code,
        name=payload.name,
        municipality=payload.municipality,
        region=payload.region,
        country_code=payload.country_code,
        lat=payload.lat,
        lon=payload.lon,
        location_source=payload.location_source,
        location_accuracy_m=payload.location_accuracy_m,
        timezone=payload.timezone,
    )


def create_site(db: Session, payload: schemas.SiteCreate) -> models.Site:
    if db.query(models.Site).filter(models.Site.code == payload.code).first():
        raise HTTPException(status_code=409, detail="El codigo del sitio ya existe")

    site = _site_from_payload(payload)
    db.add(site)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No se pudo crear el sitio por un conflicto de integridad",
        ) from exc
    db.refresh(site)
    return site


def _coordinates_conflict(site: models.Site, payload: schemas.SiteCreate) -> bool:
    if (
        site.lat is None
        or site.lon is None
        or payload.lat is None
        or payload.lon is None
    ):
        return False
    return abs(site.lat - payload.lat) > 0.001 or abs(site.lon - payload.lon) > 0.001


def get_or_create_site_for_activation(
    db: Session,
    payload: schemas.SiteCreate,
) -> models.Site:
    site = db.query(models.Site).filter(models.Site.code == payload.code).first()
    if site is None:
        site = _site_from_payload(payload)
        db.add(site)
        db.flush()
        return site

    if site.archived_at is not None:
        raise HTTPException(status_code=409, detail="El sitio esta archivado")
    if _coordinates_conflict(site, payload):
        raise HTTPException(
            status_code=409,
            detail=(
                "El codigo del sitio ya existe con coordenadas diferentes; "
                "revisa la configuracion antes de activar el nodo"
            ),
        )

    if site.lat is None and payload.lat is not None:
        site.lat = payload.lat
        site.lon = payload.lon
        site.location_source = payload.location_source
        site.location_accuracy_m = payload.location_accuracy_m
    return site


def update_site(
    db: Session,
    site: models.Site,
    payload: schemas.SiteUpdate,
) -> models.Site:
    values = payload.model_dump(exclude_unset=True)
    archived = values.pop("archived", None)

    for field, value in values.items():
        setattr(site, field, value)

    if (site.lat is None) != (site.lon is None):
        raise HTTPException(
            status_code=422,
            detail="El sitio debe conservar latitud y longitud juntas",
        )
    if site.location_accuracy_m is not None and site.lat is None:
        raise HTTPException(
            status_code=422,
            detail="location_accuracy_m requiere coordenadas",
        )

    if archived is True and site.archived_at is None:
        active = db.query(models.Deployment).filter(
            models.Deployment.site_id == site.id,
            models.Deployment.ended_at.is_(None),
        ).first()
        if active:
            raise HTTPException(
                status_code=409,
                detail="No se puede archivar un sitio con un despliegue activo",
            )
        site.archived_at = _utc_now()
    elif archived is False:
        site.archived_at = None

    site.updated_at = _utc_now()
    db.commit()
    db.refresh(site)
    return site


def site_response(db: Session, site: models.Site) -> dict:
    return {
        "id": site.id,
        "code": site.code,
        "name": site.name,
        "municipality": site.municipality,
        "region": site.region,
        "country_code": site.country_code,
        "lat": site.lat,
        "lon": site.lon,
        "location_source": site.location_source or "unknown",
        "location_accuracy_m": site.location_accuracy_m,
        "timezone": site.timezone,
        "created_at": site.created_at,
        "updated_at": site.updated_at,
        "archived_at": site.archived_at,
        "deployment_count": db.query(models.Deployment).filter(
            models.Deployment.site_id == site.id
        ).count(),
        "active_deployment_count": db.query(models.Deployment).filter(
            models.Deployment.site_id == site.id,
            models.Deployment.ended_at.is_(None),
        ).count(),
        "detection_count": db.query(models.Detection).join(
            models.Deployment,
            models.Detection.deployment_id == models.Deployment.id,
        ).filter(models.Deployment.site_id == site.id).count(),
        "audio_metric_count": db.query(models.AudioMetric).join(
            models.Deployment,
            models.AudioMetric.deployment_id == models.Deployment.id,
        ).filter(models.Deployment.site_id == site.id).count(),
    }


def deployment_response(deployment: models.Deployment) -> dict:
    return {
        "id": deployment.id,
        "public_id": deployment.public_id,
        "device_id": deployment.device_id,
        "device_name": deployment.device.name,
        "site_id": deployment.site_id,
        "site_code": deployment.site.code,
        "site_name": deployment.site.name,
        "started_at": deployment.started_at,
        "ended_at": deployment.ended_at,
        "active": deployment.ended_at is None,
        "created_at": deployment.created_at,
        "updated_at": deployment.updated_at,
        "notes": deployment.notes,
    }


def _update_device_compatibility(device: models.Device, site: models.Site) -> None:
    device.location = site.name
    device.lat = site.lat
    device.lon = site.lon
    device.location_source = site.location_source
    device.location_accuracy_m = site.location_accuracy_m


def activate_deployment(
    db: Session,
    payload: schemas.DeploymentActivate,
) -> models.Deployment:
    device = get_or_create_device(db, payload.device_name)
    site = get_or_create_site_for_activation(db, payload.site)
    public_id = str(payload.deployment_public_id)

    existing = db.query(models.Deployment).options(
        joinedload(models.Deployment.device),
        joinedload(models.Deployment.site),
    ).filter(models.Deployment.public_id == public_id).first()
    if existing:
        if existing.device_id != device.id or existing.site_id != site.id:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="El UUID del despliegue ya pertenece a otro contexto",
            )
        # Un reintento de una activacion antigua debe ser idempotente, pero no
        # puede hacer que Device vuelva a mostrar un sitio ya cerrado.
        if existing.ended_at is None:
            _update_device_compatibility(device, site)
        db.commit()
        return existing

    active = db.query(models.Deployment).filter(
        models.Deployment.device_id == device.id,
        models.Deployment.ended_at.is_(None),
    ).first()
    if active:
        if _comparable_datetime(payload.started_at) < _comparable_datetime(
            active.started_at
        ):
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="El nuevo despliegue no puede comenzar antes que el activo",
            )
        active.ended_at = payload.started_at
        active.updated_at = _utc_now()

    deployment = models.Deployment(
        public_id=public_id,
        device_id=device.id,
        site_id=site.id,
        started_at=payload.started_at,
        notes=payload.notes,
    )
    db.add(deployment)
    _update_device_compatibility(device, site)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Conflicto al activar el despliegue",
        ) from exc

    return db.query(models.Deployment).options(
        joinedload(models.Deployment.device),
        joinedload(models.Deployment.site),
    ).filter(models.Deployment.id == deployment.id).one()


def _legacy_site_payload(device: models.Device) -> schemas.SiteCreate:
    location = (device.location or "").strip()
    if location.casefold() in INVALID_LOCATIONS:
        location = ""
    primary_node = os.getenv(
        "BIRDMONITOR_PRIMARY_NODE_NAME",
        "birdmonitor",
    ).strip()
    if device.name == primary_node:
        code = os.getenv(
            "BIRDMONITOR_LEGACY_SITE_CODE",
            "sevilla",
        ).strip().lower()
        location = location or "Sevilla"
    else:
        slug_source = location or device.name
        ascii_text = unicodedata.normalize("NFKD", slug_source).encode(
            "ascii",
            "ignore",
        ).decode("ascii").lower()
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
        code = (slug or f"legacy-{device.id}")[:63].rstrip("-")
        location = location or f"Ubicacion de {device.name}"
    parts = [part.strip() for part in location.split(",") if part.strip()]
    lat, lon = device.lat, device.lon
    if (lat is None) != (lon is None):
        lat, lon = None, None
    source = device.location_source or "unknown"
    if source not in {"manual", "gps", "ip_geolocation", "unknown"}:
        source = "unknown"
    return schemas.SiteCreate(
        code=code,
        name=location,
        municipality=parts[0] if parts else "Sevilla",
        region=parts[1] if len(parts) > 1 else "Andalucia",
        country_code="ES",
        lat=lat,
        lon=lon,
        location_source=source,
        location_accuracy_m=(device.location_accuracy_m if lat is not None else None),
        timezone="Europe/Madrid",
    )


def ensure_legacy_deployment(
    db: Session,
    device: models.Device,
    observed_at: datetime,
) -> models.Deployment:
    payload = _legacy_site_payload(device)
    site = get_or_create_site_for_activation(db, payload)
    public_id = legacy_deployment_public_id(site.code, device.id)
    deployment = db.query(models.Deployment).options(
        joinedload(models.Deployment.site),
        joinedload(models.Deployment.device),
    ).filter(models.Deployment.public_id == public_id).first()
    if deployment:
        observed = _comparable_datetime(observed_at)
        if observed < _comparable_datetime(deployment.started_at) or (
            deployment.ended_at is not None
            and observed > _comparable_datetime(deployment.ended_at)
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "El payload legacy queda fuera del despliegue historico; "
                    "actualiza el nodo para enviar deployment_public_id"
                ),
            )
        return deployment

    active = db.query(models.Deployment).filter(
        models.Deployment.device_id == device.id,
        models.Deployment.ended_at.is_(None),
    ).first()
    if active and active.site_id != site.id:
        raise HTTPException(
            status_code=409,
            detail=(
                "El nodo ya tiene otro sitio activo; el evento debe incluir "
                "deployment_public_id"
            ),
        )
    if active:
        return active

    deployment = models.Deployment(
        public_id=public_id,
        device_id=device.id,
        site_id=site.id,
        started_at=observed_at,
        notes="Compatibilidad temporal para payload legacy",
    )
    db.add(deployment)
    db.flush()
    return deployment


def resolve_event_deployment(
    db: Session,
    *,
    device: models.Device,
    observed_at: datetime,
    site_code: str | None,
    deployment_public_id: UUID | None,
) -> models.Deployment:
    if site_code and deployment_public_id is None:
        raise HTTPException(
            status_code=422,
            detail="site_code requiere deployment_public_id",
        )

    if deployment_public_id is None:
        logger.warning(
            "Payload legacy sin deployment_public_id para el nodo %s; "
            "se asigna al despliegue historico de Sevilla",
            device.name,
        )
        return ensure_legacy_deployment(db, device, observed_at)

    deployment = db.query(models.Deployment).options(
        joinedload(models.Deployment.site),
        joinedload(models.Deployment.device),
    ).filter(
        models.Deployment.public_id == str(deployment_public_id)
    ).first()
    if deployment is None:
        raise HTTPException(
            status_code=409,
            detail="El despliegue no existe; activalo antes de enviar eventos",
        )
    if deployment.device_id != device.id:
        raise HTTPException(
            status_code=409,
            detail="El despliegue no pertenece al dispositivo indicado",
        )
    if site_code and deployment.site.code != site_code:
        raise HTTPException(
            status_code=409,
            detail="site_code no coincide con el despliegue",
        )

    observed = _comparable_datetime(observed_at)
    if observed < _comparable_datetime(deployment.started_at):
        raise HTTPException(
            status_code=409,
            detail="El evento es anterior al inicio del despliegue",
        )
    if deployment.ended_at and observed > _comparable_datetime(deployment.ended_at):
        raise HTTPException(
            status_code=409,
            detail="El evento es posterior al cierre del despliegue",
        )
    return deployment