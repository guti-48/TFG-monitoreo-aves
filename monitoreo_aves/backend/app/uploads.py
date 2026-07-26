import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from .config import (
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_IMAGE_EXTENSIONS,
    MAX_AUDIO_BYTES,
    MAX_IMAGE_BYTES,
    SERVER_AUDIO_DIR,
    SPECTOGRAM_DIR,
)


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


@router.post("/upload/")
async def subida_archivos(
    audio: UploadFile | None = File(None),
    specto: UploadFile | None = File(None),
):
    """Recibe audio WAV y espectrogramas PNG desde la Raspberry Pi."""
    saved_files = []

    if audio:
        nombre_audio = await guardar_upload_seguro(
            upload=audio,
            destino_dir=SERVER_AUDIO_DIR,
            extensiones_permitidas=ALLOWED_AUDIO_EXTENSIONS,
            max_bytes=MAX_AUDIO_BYTES,
        )
        saved_files.append(nombre_audio)

    if specto:
        nombre_img = await guardar_upload_seguro(
            upload=specto,
            destino_dir=SPECTOGRAM_DIR,
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
    }