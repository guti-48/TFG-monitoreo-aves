from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import joinedload

from ...domain import models, schemas
from .protocol import Context, Page, Record, event_key, naive_utc

MODELS = {"detections": models.Detection, "audio_metrics": models.AudioMetric}


class ReplicaConflict(ValueError):
    pass


def replica_id(db) -> str:
    existing = db.get(models.ReplicaIdentity, 1)
    if existing is not None:
        return existing.public_id
    db.execute(insert(models.ReplicaIdentity).values(id=1, public_id=str(uuid4())).on_conflict_do_nothing())
    db.commit()
    return db.get(models.ReplicaIdentity, 1).public_id


def export_page(db, kind: str, after: int, limit: int) -> Page:
    identity = replica_id(db)
    model = MODELS[kind]
    rows = db.scalars(select(model).where(model.id > after).order_by(model.id).limit(limit).options(
        joinedload(model.device), joinedload(model.deployment).joinedload(models.Deployment.site),
    )).all()
    records = []
    schema = schemas.DetectionCreate if kind == "detections" else schemas.AudioMetricCreate
    for row in rows:
        deployment = row.deployment
        if deployment is None or row.device is None:
            raise ReplicaConflict("Hay registros sin despliegue; completa la migracion de ubicaciones")
        data = {name: getattr(row, name) for name in schema.model_fields
                if name not in {"device_name", "site_code", "deployment_public_id"}}
        data.update(device_name=row.device.name, site_code=deployment.site.code,
                    deployment_public_id=deployment.public_id)
        # Las columnas antiguas pueden contener NULL donde el esquema actual tiene un valor inicial.
        for name, field in schema.model_fields.items():
            if data.get(name) is None and not field.is_required() and field.default is not None:
                data[name] = field.default
        data = schema.model_validate(data).model_dump(mode="json")
        context = Context(device_name=row.device.name, public_id=deployment.public_id,
                          site={name: getattr(deployment.site, name) for name in schemas.SiteCreate.model_fields},
                          started_at=deployment.started_at, ended_at=deployment.ended_at, notes=deployment.notes)
        records.append(Record(sequence=row.id, event_id=event_key(kind, data), context=context, data=data))
    return Page(source_id=identity, kind=kind, after=after, records=records)


def import_context(db, context: Context):
    device = db.scalar(select(models.Device).where(models.Device.name == context.device_name))
    if device is None:
        device = models.Device(name=context.device_name, location=context.site.name)
        db.add(device)
        db.flush()
    site = db.scalar(select(models.Site).where(models.Site.code == context.site.code))
    if site is None:
        site = models.Site(**context.site.model_dump())
        db.add(site)
        db.flush()
    elif (site.lat, site.lon, site.timezone) != (context.site.lat, context.site.lon, context.site.timezone):
        raise ReplicaConflict("El sitio tiene coordenadas o zona horaria distintas; requiere reconciliacion")
    deployment = db.scalar(select(models.Deployment).where(models.Deployment.public_id == str(context.public_id)))
    if deployment is not None:
        if deployment.device_id != device.id or deployment.site_id != site.id or deployment.started_at != context.started_at:
            raise ReplicaConflict("El UUID del despliegue pertenece a otro contexto")
        return deployment
    active = db.scalar(select(models.Deployment).where(
        models.Deployment.device_id == device.id, models.Deployment.ended_at.is_(None)))
    ended = context.ended_at
    if active:
        if context.started_at < active.started_at:
            ended = min(ended, active.started_at) if ended else active.started_at
        else:
            active.ended_at = context.started_at
            db.flush()
    deployment = models.Deployment(public_id=str(context.public_id), device_id=device.id, site_id=site.id,
                                   started_at=context.started_at, ended_at=ended, notes=context.notes)
    db.add(deployment)
    db.flush()
    if ended is None:
        for attr in ("lat", "lon", "location_source", "location_accuracy_m"):
            setattr(device, attr, getattr(site, attr))
        device.location = site.name
    return deployment


def import_page(db, page: Page) -> int:
    source = str(page.source_id)
    if source == replica_id(db):
        raise ReplicaConflict("No se puede importar la propia replica")
    key = (source, page.kind)
    cursor = db.get(models.ReplicaCursor, key)
    position = cursor.position if cursor else 0
    if page.after != position:
        raise ReplicaConflict("El cursor ha cambiado; vuelve a solicitar la pagina")
    added = 0
    try:
        for record in page.records:
            data = record.validate_data(page.kind)
            deployment = import_context(db, record.context)
            data.pop("device_name")
            data.pop("site_code")
            data.pop("deployment_public_id")
            data["timestamp"] = naive_utc(data["timestamp"])
            model = MODELS[page.kind]
            query = select(model).where(model.deployment_id == deployment.id, model.filename == data["filename"])
            if page.kind == "detections":
                query = query.where(model.species == data["species"])
            existing = next((row for row in db.scalars(query).all()
                             if naive_utc(row.timestamp) == data["timestamp"]), None)
            if existing is None:
                db.add(model(**data, device_id=deployment.device_id, deployment_id=deployment.id))
                db.flush()
                added += 1
            else:
                for name, value in data.items():
                    local = getattr(existing, name)
                    if name == "timestamp" and local is not None:
                        local = naive_utc(local)
                    if local is not None and value is not None and local != value:
                        raise ReplicaConflict("Un evento existente tiene valores diferentes; no se sobrescribe")
            stem = Path(data["filename"]).stem
            audio_name = data["filename"] if data["filename"].lower().endswith(".wav") else f"{stem}.wav"
            for media_kind, extension in (("audio", ".wav"), ("spectrogram", ".png")):
                media_name = audio_name if media_kind == "audio" else f"{stem}{extension}"
                db.execute(insert(models.ReplicaMedia).values(
                    source_id=source, kind=page.kind, record_id=record.sequence, media_kind=media_kind,
                    relative_path=f"{record.context.site.code}/{record.context.public_id}/{media_name}",
                    attempts=0, completed=False,
                ).on_conflict_do_nothing())
        if cursor is None:
            cursor = models.ReplicaCursor(source_id=source, kind=page.kind, position=position)
            db.add(cursor)
        if page.records:
            cursor.position = page.records[-1].sequence
        cursor.updated_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return added