import hashlib
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core import database
from ...domain import models, schemas
from ..detections import media
from .protocol import Context, Kind, MediaKind, PAGE_SIZE, PROTOCOL_VERSION
from .service import MODELS, ReplicaConflict, export_page, import_context, replica_id

router = APIRouter(prefix="/replication/v1", tags=["replication"])
status_router = APIRouter()


@status_router.post("/node/deployments/register")
def register_deployment(payload: schemas.DeploymentActivate,
                        db: Session = Depends(database.get_db)):
    try:
        context = Context(device_name=payload.device_name, public_id=payload.deployment_public_id,
                          site=payload.site, started_at=payload.started_at, notes=payload.notes)
        deployment = import_context(db, context)
        db.commit()
        return {"deployment_public_id": deployment.public_id}
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="El despliegue no coincide con el contexto guardado") from exc


@router.get("/info")
def info(db: Session = Depends(database.get_db)):
    return {"protocol": PROTOCOL_VERSION, "source_id": replica_id(db)}


@router.get("/records/{kind}")
def records(kind: Kind, after: int = Query(default=0, ge=0),
            limit: int = Query(default=PAGE_SIZE, ge=1, le=PAGE_SIZE),
            db: Session = Depends(database.get_db)):
    try:
        return export_page(db, kind, after, limit)
    except (ValueError, ReplicaConflict) as exc:
        raise HTTPException(status_code=409, detail="Historico no exportable; revisa contextos y formatos") from exc


@router.get("/media/{kind}/{record_id}/{media_kind}")
def download_media(kind: Kind, record_id: int, media_kind: MediaKind,
                   db: Session = Depends(database.get_db)):
    record = db.get(MODELS[kind], record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    resolver = media.resolve_audio_path if media_kind == "audio" else media.resolve_spectrogram_path
    try:
        path = resolver(record.filename, record.deployment)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Archivo aun no disponible") from exc
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return FileResponse(path, headers={"X-BirdMonitor-SHA256": digest, "Cache-Control": "no-store"})


@status_router.get("/sync/status")
def sync_status(db: Session = Depends(database.get_db)):
    cursors = db.query(models.ReplicaCursor).all()
    pending_query = db.query(models.ReplicaMedia).filter_by(completed=False)
    pending_count = pending_query.count()
    pending = pending_query.order_by(models.ReplicaMedia.attempts.desc()).limit(50).all()
    return {
        "source_id": replica_id(db),
        "cursors": [{"source_id": row.source_id, "kind": row.kind,
                     "position": row.position, "updated_at": row.updated_at} for row in cursors],
        "pending_media": pending_count,
        "media_errors": [{"source_id": row.source_id, "kind": row.kind, "record_id": row.record_id,
                          "media_kind": row.media_kind, "attempts": row.attempts,
                          "last_error": row.last_error} for row in pending[:50]],
    }