from datetime import datetime
import hashlib
from pathlib import Path
import threading
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core import database, security
from backend.app.domain import models
from backend.app.features.detections import media
from backend.app.features.replication import routes, worker
from backend.app.features.replication.config import Peer
from backend.app.features.replication.protocol import Page
from backend.app.features.replication.service import export_page, import_page, replica_id, ReplicaConflict
from scripts.configure_replication import configure

TOKEN = "replication-test-token-01234567890123456789"


@pytest.fixture
def stores(tmp_path):
    factories = []
    engines = []
    for name in ("mac", "windows", "third"):
        engine = create_engine(f"sqlite:///{tmp_path / (name + '.db')}", connect_args={"check_same_thread": False})
        models.Base.metadata.create_all(engine)
        factories.append(sessionmaker(bind=engine, autoflush=False))
        engines.append(engine)
    yield factories
    for engine in engines:
        engine.dispose()


def add_capture(sessions, *, number=1, deployment_uuid=None, site_code="field", device_name="birdmonitor",
                started_at=datetime(2026, 1, 1), ended_at=None):
    with sessions() as db:
        device = db.scalar(select(models.Device).where(models.Device.name == device_name))
        if device is None:
            device = models.Device(name=device_name, location="Field")
            db.add(device)
        site = db.scalar(select(models.Site).where(models.Site.code == site_code))
        if site is None:
            site = models.Site(code=site_code, name="Field", lat=37.0, lon=-6.0,
                               timezone="Europe/Madrid", location_source="manual", country_code="ES")
            db.add(site)
        db.flush()
        deployment = db.scalar(select(models.Deployment).where(models.Deployment.device_id == device.id))
        if deployment is None:
            deployment = models.Deployment(public_id=deployment_uuid or str(uuid4()), device_id=device.id,
                                           site_id=site.id, started_at=started_at, ended_at=ended_at)
            db.add(deployment)
            db.flush()
        filename = f"record_2026-10-{number:02d}_12-00-00.wav"
        timestamp = datetime(2026, 10, number, 12)
        detection = models.Detection(device_id=device.id, deployment_id=deployment.id, timestamp=timestamp,
                                     species="Passer domesticus", filename=filename, confidence=.9, amplitude=.01)
        metric = models.AudioMetric(device_id=device.id, deployment_id=deployment.id, timestamp=timestamp,
                                    filename=filename, sample_rate=48000, duration=60, rms=.01,
                                    aci=1, adi=2, aei=.3, bio=4, ndsi=.2, ht=.4, hf=.5, h=.2)
        db.add_all([detection, metric])
        db.commit()
        return deployment.public_id, filename


def source_client(sessions, monkeypatch, audio_root, image_root):
    monkeypatch.setenv("BIRDMONITOR_REPLICATION_TOKEN_HASH", security.hash_node_token(TOKEN))
    monkeypatch.setattr(media, "SERVER_AUDIO_DIR", audio_root)
    monkeypatch.setattr(media, "SPECTOGRAM_DIR", image_root)
    app = FastAPI()
    app.middleware("http")(security.security_middleware)
    app.include_router(routes.router)
    def get_db():
        with sessions() as db:
            yield db
    app.dependency_overrides[database.get_db] = get_db
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})


def peer():
    return Peer(name="mac", url="http://100.92.197.59:8000", token=TOKEN)


def test_duplicate_legacy_rows_in_one_page_are_imported_once(stores):
    source, destination, _ = stores
    add_capture(source)
    with source() as db:
        page = export_page(db, "detections", 0, 100)
    first = page.records[0]
    page.records.append(first.model_copy(update={"sequence": first.sequence + 1}))
    with destination() as db:
        assert import_page(db, page) == 1
        assert db.query(models.Detection).count() == 1
        assert db.get(models.ReplicaCursor, (str(page.source_id), "detections")).position == first.sequence + 1


def test_legacy_timestamp_text_format_does_not_create_duplicate(stores):
    source, destination, _ = stores
    deployment, _ = add_capture(source)
    add_capture(destination, deployment_uuid=deployment)
    from sqlalchemy import text
    with destination() as db:
        db.execute(text("UPDATE detections SET timestamp='2026-10-01T12:00:00'"))
        db.commit()
    with source() as db:
        page = export_page(db, "detections", 0, 100)
    with destination() as db:
        assert import_page(db, page) == 0
        assert db.query(models.Detection).count() == 1


def test_late_computer_catches_up_files_without_pi_and_can_forward(stores, tmp_path, monkeypatch):
    mac, windows, third = stores
    deployment, filename = add_capture(mac)
    add_capture(windows, number=2, device_name="other-device", site_code="other-site")
    audio = tmp_path / "mac-audio"
    images = tmp_path / "mac-images"
    source_audio = audio / "field" / deployment / filename
    source_audio.parent.mkdir(parents=True)
    source_audio.write_bytes(b"RIFF-old-recording-on-mac")
    source_image = images / "field" / deployment / Path(filename).with_suffix(".png")
    source_image.parent.mkdir(parents=True)
    source_image.write_bytes(b"PNG-old-spectrogram-on-mac")
    with source_client(mac, monkeypatch, audio, images) as client:
        count = worker.sync_peer(peer(), windows, client, audio_root=tmp_path / "windows-audio", image_root=tmp_path / "windows-images")
        assert count == 2
        assert worker.sync_peer(peer(), windows, client, audio_root=tmp_path / "windows-audio", image_root=tmp_path / "windows-images") == 0
    assert (tmp_path / "windows-audio/field" / deployment / filename).read_bytes() == source_audio.read_bytes()
    with windows() as db:
        assert db.query(models.Detection).count() == 2
        imported = db.scalar(select(models.Detection).where(models.Detection.filename == filename))
        assert imported.device.name == "birdmonitor"
        assert imported.device_id != 1
        assert db.query(models.ReplicaMedia).filter_by(completed=False).count() == 0
    with source_client(windows, monkeypatch, tmp_path / "windows-audio", tmp_path / "windows-images") as client:
        assert worker.sync_peer(peer(), third, client, audio_root=tmp_path / "third-audio", image_root=tmp_path / "third-images") == 4
        assert worker.sync_peer(peer(), mac, client, audio_root=audio, image_root=images) == 2
    with mac() as db:
        assert db.query(models.Detection).count() == 2
    assert (tmp_path / "third-audio/field" / deployment / filename).is_file()


def test_unavailable_peer_does_not_advance_cursor(stores):
    def offline(request):
        raise httpx.ConnectError("offline")
    with httpx.Client(transport=httpx.MockTransport(offline), base_url=peer().url) as client:
        with pytest.raises(httpx.ConnectError):
            worker.sync_peer(peer(), stores[1], client)
    with stores[1]() as db:
        assert db.query(models.ReplicaCursor).count() == 0


def test_delayed_media_remains_pending_and_retries(stores, tmp_path, monkeypatch):
    mac, windows, _ = stores
    deployment, filename = add_capture(mac)
    audio, images = tmp_path / "a", tmp_path / "i"
    with source_client(mac, monkeypatch, audio, images) as client:
        worker.sync_peer(peer(), windows, client, audio_root=tmp_path / "dest", image_root=tmp_path / "dest-img")
        with windows() as db:
            assert db.query(models.Detection).count() == 1
            for pending in db.query(models.ReplicaMedia):
                assert not pending.completed
                assert pending.last_error == "HTTP 404"
                pending.next_attempt_at = None
            db.commit()
        source = audio / "field" / deployment / filename
        source.parent.mkdir(parents=True)
        source.write_bytes(b"RIFF-arrived-later")
        assert worker.sync_peer(peer(), windows, client, audio_root=tmp_path / "dest", image_root=tmp_path / "dest-img") == 0
    assert (tmp_path / "dest/field" / deployment / filename).read_bytes() == b"RIFF-arrived-later"


def test_conflicting_context_rolls_back_whole_page_and_cursor(stores):
    public_id = str(uuid4())
    add_capture(stores[0], deployment_uuid=public_id)
    add_capture(stores[1], deployment_uuid=public_id, device_name="different-device")
    with stores[0]() as db:
        page = export_page(db, "detections", 0, 100)
    with stores[1]() as db:
        with pytest.raises(ReplicaConflict):
            import_page(db, page)
        assert db.query(models.ReplicaCursor).count() == 0
        assert db.query(models.Detection).count() == 1
        assert db.query(models.Device).count() == 1


def test_old_deployment_does_not_replace_new_active_location(stores):
    add_capture(stores[0], ended_at=None, started_at=datetime(2025, 1, 1))
    new, _ = add_capture(stores[1], site_code="new-site", started_at=datetime(2026, 1, 1))
    with stores[0]() as db:
        page = export_page(db, "detections", 0, 100)
    with stores[1]() as db:
        import_page(db, page)
        active = db.scalar(select(models.Deployment).where(models.Deployment.ended_at.is_(None)))
        assert active.public_id == new
        assert db.query(models.Deployment).count() == 2


def test_page_identity_order_and_paths_are_validated(stores):
    add_capture(stores[0])
    with stores[0]() as db:
        data = export_page(db, "detections", 0, 100).model_dump(mode="json")
    data["records"][0]["data"]["filename"] = "../../secret.wav"
    with pytest.raises(ValueError):
        Page.model_validate(data)


def test_corrupt_or_interrupted_download_leaves_no_partial_file(tmp_path):
    item = models.ReplicaMedia(kind="detections", record_id=1, media_kind="audio", relative_path="field/file.wav")
    digest = hashlib.sha256(b"expected").hexdigest()
    def corrupt(request):
        return httpx.Response(200, headers={"X-BirdMonitor-SHA256": digest}, content=b"corrupt")
    with httpx.Client(transport=httpx.MockTransport(corrupt), base_url=peer().url) as client:
        with pytest.raises(ValueError):
            worker.save_media(client, item, tmp_path, tmp_path)
    assert not (tmp_path / "field/file.wav").exists()
    assert list((tmp_path / "field").iterdir()) == []


def test_existing_different_file_is_not_overwritten(tmp_path):
    (tmp_path / "file.wav").write_bytes(b"local")
    item = models.ReplicaMedia(kind="detections", record_id=1, media_kind="audio", relative_path="file.wav")
    def remote(request):
        return httpx.Response(200, headers={"X-BirdMonitor-SHA256": hashlib.sha256(b"remote").hexdigest()}, content=b"remote")
    with httpx.Client(transport=httpx.MockTransport(remote), base_url=peer().url) as client:
        with pytest.raises(ValueError):
            worker.save_media(client, item, tmp_path, tmp_path)
    assert (tmp_path / "file.wav").read_bytes() == b"local"


def test_replication_requires_its_own_token_even_without_dashboard_auth(stores, tmp_path, monkeypatch):
    with source_client(stores[0], monkeypatch, tmp_path, tmp_path) as client:
        assert client.get('/replication/v1/info').status_code == 200
        assert client.get('/replication/v1/info', headers={"Authorization": "Bearer node-token"}).status_code == 403
        assert client.post('/replication/v1/info').status_code == 403
        client.headers.pop("Authorization")
        assert client.get('/replication/v1/info').status_code == 403


def test_cursor_survives_restart_and_replayed_page_cannot_advance_it(stores):
    add_capture(stores[0])
    with stores[0]() as db:
        page = export_page(db, "detections", 0, 100)
    with stores[1]() as db:
        assert import_page(db, page) == 1
    with stores[1]() as db:
        with pytest.raises(ReplicaConflict):
            import_page(db, page)
        assert db.get(models.ReplicaCursor, (str(page.source_id), "detections")).position == 1
        assert db.query(models.Detection).count() == 1


@pytest.mark.parametrize("url", ["https://example.com", "http://8.8.8.8", "http://user:pw@100.64.0.1", "http://100.64.0.1/path", "http://100.64.0.1?token=secret"])
def test_peer_rejects_public_urls_and_credentials(url):
    with pytest.raises(ValueError):
        Peer(name="peer", url=url, token=TOKEN)


def test_configurator_preserves_credentials_and_does_not_rotate(tmp_path):
    env = tmp_path / "birdmonitor.env"
    env.write_text("BIRDMONITOR_ADMIN_PASSWORD_HASH=existing\nBIRDMONITOR_NODE_TOKEN_HASH=existing-node\n")
    configure(tmp_path)
    initial = (tmp_path / "replication-access.secret").read_text()
    configure(tmp_path, "mac", peer().url, TOKEN)
    configure(tmp_path)
    assert (tmp_path / "replication-access.secret").read_text() == initial
    assert "BIRDMONITOR_ADMIN_PASSWORD_HASH=existing" in env.read_text()
    assert "BIRDMONITOR_NODE_TOKEN_HASH=existing-node" in env.read_text()


def test_multiple_pages_resume_without_skipping(stores, tmp_path, monkeypatch):
    add_capture(stores[0])
    with stores[0]() as db:
        first = db.scalar(select(models.Detection))
        for index in range(120):
            db.add(models.Detection(device_id=first.device_id, deployment_id=first.deployment_id,
                                    timestamp=first.timestamp, filename=first.filename,
                                    species=f"species-{index}", confidence=.8, amplitude=.02))
        db.commit()
    with source_client(stores[0], monkeypatch, tmp_path, tmp_path) as client:
        assert worker.sync_peer(peer(), stores[1], client, page_budget=1, media_budget=0) == 101
        assert worker.sync_peer(peer(), stores[1], client, page_budget=1, media_budget=0) == 21
        assert worker.sync_peer(peer(), stores[1], client, page_budget=1, media_budget=0) == 0
    with stores[1]() as db:
        assert db.query(models.Detection).count() == 121


def test_invalid_peer_does_not_change_config_or_expose_token(tmp_path, monkeypatch):
    from backend.app.features.replication.config import load_peers
    env = tmp_path / "birdmonitor.env"
    env.write_text("BIRDMONITOR_ADMIN_PASSWORD_HASH=existing\n")
    with pytest.raises(ValueError):
        configure(tmp_path, "mac", "https://public.example.com", TOKEN)
    assert not (tmp_path / "replication-access.secret").exists()
    assert env.read_text() == "BIRDMONITOR_ADMIN_PASSWORD_HASH=existing\n"
    peers = tmp_path / "peers.secret"
    peers.write_text('{"token":"' + TOKEN + '"}')
    monkeypatch.setenv("BIRDMONITOR_REPLICATION_PEERS_FILE", str(peers))
    with pytest.raises(ValueError) as caught:
        load_peers()
    assert TOKEN not in str(caught.value)


def test_background_worker_retries_offline_cycle_and_stops(monkeypatch):
    calls = []
    stop = threading.Event()

    def cycle(peers, stop_event):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("offline")
        stop_event.set()

    monkeypatch.setattr(worker, "sync_cycle", cycle)
    worker.run_worker([peer()], stop, .001)
    assert len(calls) == 2


def test_lifespan_starts_and_joins_worker(monkeypatch):
    import asyncio
    started, exited = threading.Event(), threading.Event()

    def run(peers, stop, interval):
        started.set()
        stop.wait(2)
        exited.set()

    monkeypatch.setattr(worker, "load_peers", lambda: [peer()])
    monkeypatch.setattr(worker, "run_worker", run)

    async def exercise():
        async with worker.replication_lifespan(None):
            assert started.wait(1)
        assert exited.is_set()

    asyncio.run(exercise())


def test_replica_token_cannot_use_dashboard_or_mutation_api(stores, tmp_path, monkeypatch):
    monkeypatch.setenv("BIRDMONITOR_SECURITY_MODE", "required")
    monkeypatch.setenv("BIRDMONITOR_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("BIRDMONITOR_ADMIN_PASSWORD_HASH", "scrypt$configured")
    monkeypatch.setenv("BIRDMONITOR_NODE_TOKEN_HASH", security.hash_node_token("separate-node-token"))
    monkeypatch.setenv("BIRDMONITOR_SESSION_SECRET", "session-secret" * 4)
    with source_client(stores[0], monkeypatch, tmp_path, tmp_path) as client:
        assert client.get('/replication/v1/info').status_code == 200
        assert client.get('/detections/').status_code == 401
        assert client.post('/stream/control', json={"stream_enabled": True}).status_code == 401


def test_filename_case_survives_replication(stores):
    add_capture(stores[0])
    with stores[0]() as db:
        record = db.scalar(select(models.Detection))
        record.filename = "Historic.WAV"
        db.commit()
        page = export_page(db, "detections", 0, 100)
    with stores[1]() as db:
        import_page(db, page)
        pending = db.scalar(select(models.ReplicaMedia).where(models.ReplicaMedia.media_kind == "audio"))
        assert pending.relative_path.endswith('/Historic.WAV')