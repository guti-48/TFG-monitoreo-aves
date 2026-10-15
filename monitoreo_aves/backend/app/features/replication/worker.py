from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
import asyncio
import hashlib
import logging
import os
from pathlib import Path
import re
import tempfile
import threading
from uuid import UUID

import httpx
from sqlalchemy import or_, select

from ...core import database
from ...core.config import MAX_AUDIO_BYTES, MAX_IMAGE_BYTES, SERVER_AUDIO_DIR, SPECTOGRAM_DIR
from ...domain import models
from .config import load_peers, interval_seconds
from .protocol import PAGE_SIZE, Page
from .service import import_page, replica_id, ReplicaConflict

logger = logging.getLogger(__name__)


@contextmanager
def process_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            if not lock.read(1):
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                yield False
                return
        else:
            import fcntl
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
        try:
            yield True
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def read_json(client, path, **kwargs):
    with client.stream("GET", path, **kwargs) as response:
        response.raise_for_status()
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > 4 * 1024 * 1024:
                raise ValueError("Respuesta de replica demasiado grande")
    import json
    return json.loads(body)


def save_media(client, item, audio_root, image_root, stopped=lambda: False):
    root = Path(audio_root if item.media_kind == "audio" else image_root).resolve()
    destination = (root / item.relative_path).resolve()
    destination.relative_to(root)
    max_bytes = MAX_AUDIO_BYTES if item.media_kind == "audio" else MAX_IMAGE_BYTES
    path = f"/replication/v1/media/{item.kind}/{item.record_id}/{item.media_kind}"
    with client.stream("GET", path) as response:
        response.raise_for_status()
        expected = response.headers.get("X-BirdMonitor-SHA256", "")
        if not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError("Falta la huella SHA256 del archivo")
        if int(response.headers.get("content-length", "0")) > max_bytes:
            raise ValueError("Archivo demasiado grande")
        if destination.is_file():
            with destination.open("rb") as existing:
                if hashlib.file_digest(existing, "sha256").hexdigest() == expected:
                    return
            raise ValueError("Archivo local diferente; se conserva sin sobrescribir")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".replica-", delete=False) as output:
                temporary = Path(output.name)
                digest = hashlib.sha256()
                size = 0
                for chunk in response.iter_bytes(1024 * 1024):
                    if stopped():
                        raise InterruptedError("Sincronizacion detenida")
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Archivo demasiado grande")
                    digest.update(chunk)
                    output.write(chunk)
                if digest.hexdigest() != expected:
                    raise ValueError("El archivo recibido no coincide con su huella")
                output.flush()
                os.fsync(output.fileno())
            # El enlace publica un archivo completo y falla si otro escritor ya creo el destino.
            try:
                os.link(temporary, destination)
            except FileExistsError:
                with destination.open("rb") as existing:
                    if hashlib.file_digest(existing, "sha256").hexdigest() != expected:
                        raise ValueError("Otro escritor creo un archivo diferente")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def sync_peer(peer, sessions, client, *, audio_root=SERVER_AUDIO_DIR, image_root=SPECTOGRAM_DIR,
              stopped=lambda: False, page_budget=10, media_budget=20):
    info = read_json(client, "/replication/v1/info")
    if info.get("protocol") != 1:
        raise ValueError("Version de replicacion incompatible")
    source = str(UUID(info["source_id"]))
    with sessions() as db:
        if source == replica_id(db):
            raise ValueError("La direccion apunta a esta misma replica")
    added = 0
    for kind in ("detections", "audio_metrics"):
        for _ in range(page_budget):
            if stopped():
                return added
            with sessions() as db:
                cursor = db.get(models.ReplicaCursor, (source, kind))
                after = cursor.position if cursor else 0
            page = Page.model_validate(read_json(client, f"/replication/v1/records/{kind}",
                                                params={"after": after, "limit": PAGE_SIZE}))
            if str(page.source_id) != source or page.kind != kind or page.after != after:
                raise ValueError("Respuesta de replica inconsistente")
            with sessions() as db:
                added += import_page(db, page)
            if len(page.records) < PAGE_SIZE:
                break
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with sessions() as db:
        items = db.scalars(select(models.ReplicaMedia).where(
            models.ReplicaMedia.source_id == source, models.ReplicaMedia.completed.is_(False),
            or_(models.ReplicaMedia.next_attempt_at.is_(None), models.ReplicaMedia.next_attempt_at <= now),
        ).order_by(models.ReplicaMedia.attempts, models.ReplicaMedia.record_id).limit(media_budget)).all()
        for item in items:
            if stopped():
                break
            try:
                save_media(client, item, audio_root, image_root, stopped)
                item.completed = True
                item.last_error = None
            except (httpx.HTTPError, OSError, ValueError) as exc:
                item.attempts += 1
                item.last_error = (f"HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError)
                                   else type(exc).__name__)
                item.next_attempt_at = now + timedelta(seconds=min(3600, 30 * 2 ** min(item.attempts, 7)))
            db.commit()
    return added


def sync_cycle(peers, stop):
    with process_lock(str(database.DB_PATH) + ".replication.lock") as acquired:
        if not acquired:
            return
        for peer in peers:
            if stop.is_set():
                return
            try:
                with httpx.Client(base_url=peer.url, headers={"Authorization": f"Bearer {peer.token.get_secret_value()}"},
                                  timeout=httpx.Timeout(10, connect=3), follow_redirects=False, trust_env=False) as client:
                    count = sync_peer(peer, database.SessionLocal, client, stopped=stop.is_set)
                logger.info("Replica %s: %s registros nuevos", peer.name, count)
            except Exception as exc:
                detail = type(exc).__name__
                if isinstance(exc, ReplicaConflict):
                    detail = str(exc)
                elif isinstance(exc, httpx.HTTPStatusError):
                    detail = f"HTTP {exc.response.status_code}"
                logger.warning("Replica %s pendiente: %s", peer.name, detail)


def run_worker(peers, stop, interval):
    while not stop.is_set():
        try:
            sync_cycle(peers, stop)
        except Exception as exc:
            logger.error("No se pudo ejecutar la sincronizacion: %s", type(exc).__name__)
        stop.wait(interval)


@asynccontextmanager
async def replication_lifespan(app):
    peers = load_peers()
    stop = threading.Event()
    worker = None
    if peers:
        worker = threading.Thread(target=run_worker, args=(peers, stop, interval_seconds()),
                                  name="birdmonitor-replication", daemon=True)
        worker.start()
    try:
        yield
    finally:
        stop.set()
        if worker:
            await asyncio.to_thread(worker.join, 15)