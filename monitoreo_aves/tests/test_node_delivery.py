from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import pytest
import requests

from deployment_context import getCurrentDeploymentContext
import node_delivery
import node_sync


MAC = node_delivery.Target("mac", "http://100.92.197.59:8000", "mac-token-" + "x" * 32)
WINDOWS = node_delivery.Target("windows", "http://100.98.248.58:8000", "win-token-" + "y" * 32)


def response(status=200, data=None):
    return SimpleNamespace(status_code=status, json=lambda: data or {})


def detection():
    context = getCurrentDeploymentContext()
    return {
        **context.event_fields(), "species": "Passer domesticus", "confidence": .9,
        "amplitude": .01, "timestamp": "2026-10-16T10:00:00", "filename": "capture.wav",
        node_delivery.CONTEXT_KEY: context.activation_payload(),
    }


@pytest.fixture
def local_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("BIRDMONITOR_INGEST_TARGETS_FILE", str(tmp_path / "targets.secret"))
    monkeypatch.setattr(node_sync, "OUTBOX_DB", str(tmp_path / "outbox.db"))
    monkeypatch.setattr(node_sync, "OUTPUT_FOLDER_AUDIO", str(tmp_path / "audio"))
    monkeypatch.setattr(node_sync, "OUTPUT_FOLDER_IMG", str(tmp_path / "images"))
    for name in ("audio", "images"):
        (tmp_path / name).mkdir()
    (tmp_path / "audio/capture.wav").write_bytes(b"full-wav")
    (tmp_path / "images/capture.png").write_bytes(b"full-png")
    node_sync.inicializarOutboxOffline()
    return tmp_path


def pending():
    with sqlite3.connect(node_sync.OUTBOX_DB) as db:
        return db.execute("SELECT event_type, payload FROM outbox_events ORDER BY id").fetchall()


def test_offline_queue_survives_restart_then_windows_receives_whole_event(local_queue, monkeypatch):
    calls = []
    online = False

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if not online or url.startswith(MAC.url):
            raise requests.ConnectionError("unavailable")
        if url.endswith("/upload/"):
            assert kwargs["timeout"] == (60, 60)
            assert kwargs["files"]["audio"][1].read() == b"full-wav"
            assert kwargs["files"]["specto"][1].read() == b"full-png"
        else:
            assert kwargs["timeout"] == (3, 60)
        return response()

    def new_delivery():
        return node_delivery.Delivery([MAC, WINDOWS], session=SimpleNamespace(post=post),
                                      audio_dir=local_queue / "audio", image_dir=local_queue / "images")

    delivery = new_delivery()
    monkeypatch.setattr(node_delivery, "get_delivery", lambda: delivery)
    node_sync.enviarDatosServidor("Passer domesticus", .9, "capture", "2026-10-16T10:00:00", .01)
    assert len(pending()) == 1
    assert json.loads(pending()[0][1])[node_delivery.CONTEXT_KEY] == getCurrentDeploymentContext().activation_payload()
    assert len(calls) == 2
    node_sync.sincronizarRespaldo()
    assert len(calls) == 2
    old = 1
    for path in (local_queue / "audio/capture.wav", local_queue / "images/capture.png"):
        os.utime(path, (old, old))
    node_sync.limpiarArchivosAntiguos()
    assert (local_queue / "audio/capture.wav").exists()

    online = True
    delivery = new_delivery()
    node_sync.sincronizarRespaldo()
    assert pending() == []
    assert any(url == WINDOWS.url + "/detections/" for url, _ in calls)
    assert any(url == WINDOWS.url + "/upload/" for url, _ in calls)
    for url, kwargs in calls:
        target = WINDOWS if url.startswith(WINDOWS.url) else MAC
        assert kwargs["headers"]["Authorization"] == f"Bearer {target.token}"
        assert kwargs["allow_redirects"] is False
        assert node_delivery.CONTEXT_KEY not in kwargs.get("json", {})


def test_upload_failure_keeps_metadata_and_retries_complete_event_on_other_pc(local_queue, monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        if url == MAC.url + "/upload/":
            assert kwargs["files"]["audio"][1].read(3) == b"ful"
            raise requests.ConnectionError()
        if url == WINDOWS.url + "/upload/":
            assert kwargs["files"]["audio"][1].read() == b"full-wav"
            return response(500)
        return response()

    delivery = node_delivery.Delivery([MAC, WINDOWS], session=SimpleNamespace(post=post),
                                     audio_dir=local_queue / "audio", image_dir=local_queue / "images")
    monkeypatch.setattr(node_delivery, "get_delivery", lambda: delivery)
    node_sync.guardarEventoOffline("detection", detection())
    node_sync.sincronizarRespaldo()
    assert pending()[0][0] == "detection"
    assert calls.index(WINDOWS.url + "/detections/") < calls.index(WINDOWS.url + "/upload/")
    assert node_sync.obtenerFilenameBasesPendientes() == {"capture"}


def test_missing_wav_never_acknowledges_delivery(local_queue):
    (local_queue / "audio/capture.wav").unlink()
    delivery = node_delivery.Delivery([MAC], session=SimpleNamespace(post=lambda *a, **k: response()),
                                     audio_dir=local_queue / "audio", image_dir=local_queue / "images")
    assert not delivery.deliver("detection", detection())
    assert "Falta el WAV" in delivery.last_error


def test_unknown_metric_version_and_redirect_are_not_receipts(local_queue):
    metric = {**detection(), "acoustic_metrics_version": "maad-v2"}
    delivery = node_delivery.Delivery([MAC], session=SimpleNamespace(post=lambda *a, **k: response()))
    assert not delivery.deliver("audio_metric", metric)
    delivery.session.post = lambda *a, **k: response(307)
    assert not delivery.deliver("deployment_start", getCurrentDeploymentContext().activation_payload())


def test_old_context_is_preserved_when_current_site_changes(local_queue, monkeypatch):
    payload = detection()
    node_sync.guardarEventoOffline("detection", payload)
    monkeypatch.setattr(node_sync, "getCurrentDeploymentContext", lambda: replace(
        getCurrentDeploymentContext(), site_code="new-site", site_name="New site"))
    received = []
    delivery = SimpleNamespace(deliver=lambda kind, data: received.append(data) or True)
    monkeypatch.setattr(node_delivery, "get_delivery", lambda: delivery)
    node_sync.sincronizarRespaldo()
    assert received[0][node_delivery.CONTEXT_KEY]["site"]["code"] == "pytest-site"


def test_corrupt_queue_disables_cleanup(local_queue):
    audio = local_queue / "audio/capture.wav"
    os.utime(audio, (1, 1))
    node_sync.guardarEventoOffline("detection", detection())
    with sqlite3.connect(node_sync.OUTBOX_DB) as db:
        db.execute("UPDATE outbox_events SET payload = 'broken-json'")
    node_sync.limpiarArchivosAntiguos()
    assert audio.exists()


@pytest.mark.parametrize("url", ["http://example.com:8000", "http://8.8.8.8", "http://100.98.248.58/other",
                                 "http://user:password@100.98.248.58", "http://100.98.248.58:99999"])
def test_targets_reject_unsafe_addresses_without_exposing_token(tmp_path, url):
    path = tmp_path / "targets.secret"
    path.write_text(json.dumps([{"name": "windows", "url": url, "token": WINDOWS.token}]))
    with pytest.raises(ValueError) as error:
        node_delivery.load_targets(path)
    assert WINDOWS.token not in str(error.value)


def test_load_targets_preserves_distinct_tokens(tmp_path):
    path = tmp_path / "targets.secret"
    path.write_text(json.dumps([{"name": t.name, "url": t.url, "token": t.token} for t in (MAC, WINDOWS)]))
    assert node_delivery.load_targets(path) == [MAC, WINDOWS]
    assert MAC.token not in repr(MAC)


def test_register_historical_context_does_not_replace_newer_active_deployment(client):
    node = "delivery-" + uuid4().hex
    current = getCurrentDeploymentContext().activation_payload()
    current.update(device_name=node, deployment_public_id=str(uuid4()), started_at="2026-10-10T00:00:00Z")
    current["site"] = {**current["site"], "code": "delivery-current-" + uuid4().hex[:8]}
    old = {**current, "deployment_public_id": str(uuid4()), "started_at": "2026-01-01T00:00:00Z",
           "site": {**current["site"], "code": "delivery-old-" + uuid4().hex[:8]}}
    assert client.post("/node/deployments/register", json=current).status_code == 200
    assert client.post("/node/deployments/register", json=old).status_code == 200
    assert client.post("/node/deployments/register", json=old).status_code == 200
    from backend.app.core.database import SessionLocal
    from backend.app.domain import models
    with SessionLocal() as db:
        active = db.query(models.Deployment).filter_by(public_id=current["deployment_public_id"]).one()
        historical = db.query(models.Deployment).filter_by(public_id=old["deployment_public_id"]).one()
        assert active.ended_at is None
        assert historical.ended_at == active.started_at
        assert db.query(models.Deployment).filter_by(public_id=old["deployment_public_id"]).count() == 1
    conflict = {**old, "started_at": "2026-02-01T00:00:00Z"}
    assert client.post("/node/deployments/register", json=conflict).status_code == 409


def test_register_requires_node_or_admin_credentials(client, monkeypatch):
    from backend.app.core.security import hash_admin_password, hash_node_token
    monkeypatch.setenv("BIRDMONITOR_SECURITY_MODE", "required")
    monkeypatch.setenv("BIRDMONITOR_ADMIN_USERNAME", "admin-test")
    monkeypatch.setenv("BIRDMONITOR_ADMIN_PASSWORD_HASH", hash_admin_password("test-password-123"))
    monkeypatch.setenv("BIRDMONITOR_SESSION_SECRET", "session-secret-for-delivery-tests-123456")
    monkeypatch.setenv("BIRDMONITOR_NODE_TOKEN_HASH", hash_node_token(MAC.token))
    monkeypatch.setenv("BIRDMONITOR_REPLICATION_TOKEN_HASH", hash_node_token(WINDOWS.token))
    client.cookies.clear()
    payload = getCurrentDeploymentContext().activation_payload()
    payload.update(device_name="auth-" + uuid4().hex, deployment_public_id=str(uuid4()))
    payload["site"]["code"] = "auth-" + uuid4().hex[:8]
    assert client.post("/node/deployments/register", json=payload).status_code == 401
    assert client.post("/node/deployments/register", json=payload,
                       headers={"Authorization": f"Bearer {WINDOWS.token}"}).status_code == 401
    assert client.post("/node/deployments/register", json=payload,
                       headers={"Authorization": f"Bearer {MAC.token}"}).status_code == 200
    ingest_token = "ingest-" + "z" * 32
    monkeypatch.setenv("BIRDMONITOR_INGEST_TOKEN_HASH", hash_node_token(ingest_token))
    headers = {"Authorization": f"Bearer {ingest_token}"}
    assert client.post("/node/deployments/register", json=payload, headers=headers).status_code == 200
    assert client.get("/devices/", headers=headers).status_code == 403
    assert client.get("/replication/v1/info", headers=headers).status_code == 403
    assert client.post("/stream/control", json={}, headers=headers).status_code == 403
    assert client.post("/node/deployments/activate", json=payload, headers=headers).status_code == 403


def test_configurator_keeps_existing_credentials_and_is_repeatable(tmp_path):
    from configure_delivery import configure
    env = tmp_path / "birdmonitor.env"
    env.write_text(f"BIRDMONITOR_SERVER_URL={MAC.url}\nBIRDMONITOR_NODE_API_TOKEN={MAC.token}\nKEEP=unchanged\n")
    targets = tmp_path / "ingest-targets.secret"
    configure(env, targets, WINDOWS.name, WINDOWS.url, WINDOWS.token)
    configure(env, targets, WINDOWS.name, WINDOWS.url, WINDOWS.token)
    loaded = node_delivery.load_targets(targets)
    assert len(loaded) == 2
    assert loaded[0].token == MAC.token
    assert loaded[1] == WINDOWS
    assert f"BIRDMONITOR_NODE_API_TOKEN={MAC.token}" in env.read_text()
    assert "KEEP=unchanged" in env.read_text()
    assert env.read_text().count("BIRDMONITOR_INGEST_TARGETS_FILE=") == 1
    assert targets.stat().st_mode & 0o777 == 0o600
