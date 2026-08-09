import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from ...core import database
from ...core.config import (
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    MAX_AUDIO_BYTES,
    MAX_IMAGE_BYTES,
    SERVER_AUDIO_DIR,
    SPECTOGRAM_DIR,
)
from ...domain import models


router = APIRouter()


def normalizar_nombre_archivo(filename: str, extensiones_permitidas: set[str]) -> str:
    if not filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo vacio")

    nombre = Path(filename).name
    nombre = re.sub(r"[^A-Za-z0-9_.-]", "_", nombre)
    extension = Path(nombre).suffix.lower()

    if extension not in extensiones_permitidas:
        raise HTTPException(
            status_code=400,
            detail=f"Extension no permitida: {extension}",
        )

    return nombre


async def guardar_upload_seguro(
    upload: UploadFile,
    destino_dir: Path,
    extensiones_permitidas: set[str],
    max_bytes: int,
) -> str:
    nombre_seguro = normalizar_nombre_archivo(
        upload.filename,
        extensiones_permitidas,
    )

    destino_dir.mkdir(parents=True, exist_ok=True)
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
                        detail=f"Archivo demasiado grande: {nombre_seguro}",
                    )

                buffer.write(chunk)

    finally:
        await upload.close()

    return nombre_seguro


def _deployment_from_upload_context(
    db: Session,
    *,
    audio: UploadFile | None,
    specto: UploadFile | None,
    deployment_public_id: str | None,
    site_code: str | None,
    device_name: str | None,
) -> models.Deployment | None:
    public_id = (deployment_public_id or "").strip()
    requested_site = (site_code or "").strip()
    requested_device = (device_name or "").strip()

    if public_id:
        deployment = db.query(models.Deployment).options(
            joinedload(models.Deployment.site),
            joinedload(models.Deployment.device),
        ).filter(models.Deployment.public_id == public_id).first()
        if deployment is None:
            raise HTTPException(status_code=409, detail="Deployment not found")
        if requested_site and deployment.site.code != requested_site:
            raise HTTPException(
                status_code=409,
                detail="site_code no coincide con el despliegue",
            )
        if requested_device and deployment.device.name != requested_device:
            raise HTTPException(
                status_code=409,
                detail="device_name no coincide con el despliegue",
            )
        return deployment

    if requested_site or requested_device:
        raise HTTPException(
            status_code=422,
            detail=(
                "site_code y device_name requieren deployment_public_id "
                "durante la subida"
            ),
        )

    upload_name = audio.filename if audio else specto.filename if specto else ""
    safe_name = Path(upload_name or "").name
    stem = Path(safe_name).stem
    variants = {safe_name, stem, f"{stem}.wav"}
    deployment_ids = [
        row[0]
        for row in (
            db.query(models.Detection.deployment_id)
            .filter(models.Detection.filename.in_(variants))
            .filter(models.Detection.deployment_id.isnot(None))
            .distinct()
            .limit(2)
            .all()
        )
    ]
    if len(deployment_ids) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "El nombre del archivo existe en varios despliegues; "
                "envia deployment_public_id"
            ),
        )
    if not deployment_ids:
        return None

    return db.query(models.Deployment).options(
        joinedload(models.Deployment.site),
        joinedload(models.Deployment.device),
    ).filter(models.Deployment.id == deployment_ids[0]).first()


@router.post("/upload/")
async def subida_archivos(
    audio: UploadFile | None = File(None),
    specto: UploadFile | None = File(None),
    deployment_public_id: str | None = Form(None),
    site_code: str | None = Form(None),
    device_name: str | None = Form(None),
    db: Session = Depends(database.get_db),
):
    """Recibe audio WAV y espectrogramas PNG desde la Raspberry Pi."""
    saved_files = []
    deployment = _deployment_from_upload_context(
        db,
        audio=audio,
        specto=specto,
        deployment_public_id=deployment_public_id,
        site_code=site_code,
        device_name=device_name,
    )
    audio_dir = SERVER_AUDIO_DIR
    spectrogram_dir = SPECTOGRAM_DIR
    if deployment is not None:
        audio_dir = audio_dir / deployment.site.code / deployment.public_id
        spectrogram_dir = (
            spectrogram_dir / deployment.site.code / deployment.public_id
        )

    if audio:
        nombre_audio = await guardar_upload_seguro(
            upload=audio,
            destino_dir=audio_dir,
            extensiones_permitidas=ALLOWED_AUDIO_EXTENSIONS,
            max_bytes=MAX_AUDIO_BYTES,
        )
        saved_files.append(nombre_audio)

    if specto:
        nombre_img = await guardar_upload_seguro(
            upload=specto,
            destino_dir=spectrogram_dir,
            extensiones_permitidas=ALLOWED_IMAGE_EXTENSIONS,
            max_bytes=MAX_IMAGE_BYTES,
        )
        saved_files.append(nombre_img)

    if not saved_files:
        raise HTTPException(status_code=400, detail="No se enviaron archivos")

    print(f"Archivos recibidos desde nodo: {saved_files}")

    return {
        "message": "Archivos subidos correctamente",
        "files": saved_files,
        "deployment_id": deployment.id if deployment else None,
        "site_code": deployment.site.code if deployment else None,
    }