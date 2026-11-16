import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import pytest
from scripts.independent_stream import prepare, receiver_config, configure_receiver, read_env
from hardware.raspberry_pi.node.bounded_capture import capture


def test_receivers_have_independent_credentials_and_demand(tmp_path):
    bundle = tmp_path / "bundle"
    prepare(bundle, "100.74.108.117", ["windows=100.98.248.58", "mac=100.92.197.59"])
    win = json.loads((bundle / "windows.json").read_text())
    mac = json.loads((bundle / "mac.json").read_text())
    assert win["password"] != mac["password"]
    origin = json.loads((bundle / "mediamtx-source.yml").read_text())
    assert origin["authMethod"] == "internal"
    assert len(origin["authInternalUsers"]) == 3
    env = tmp_path / "birdmonitor.env"
    env.write_text("BIRDMONITOR_SERVER_HOST=100.98.248.58\nEXISTING=keep\n")
    configure_receiver(env, bundle / "windows.json")
    rendered = receiver_config(Path("tools/mediamtx/mediamtx.secure.yml").read_text(), read_env(env), env)
    assert "sourceOnDemand: true" in rendered
    assert "hlsAlwaysRemux: false" in rendered
    assert "100.74.108.117:8554" in rendered
    assert mac["password"] not in rendered
    assert "all_others" not in rendered
    assert read_env(env)["EXISTING"] == "keep"
    with pytest.raises(ValueError):
        prepare(bundle, "100.74.108.117", ["windows=100.98.248.58"])


def test_pull_control_never_stops_shared_origin(client, tmp_path, monkeypatch):
    from backend.app.features.streaming import routes
    monkeypatch.setenv("BIRDMONITOR_STREAM_MODE", "pull")
    monkeypatch.setenv("BIRDMONITOR_STREAM_SOURCE_NODE", "birdmonitor")
    monkeypatch.setattr(routes, "STREAM_CONTROL_FILE", tmp_path / "state.json")
    state = client.get("/stream/control").json()
    assert state["connection_allowed"] is True
    assert state["playback_ready"] is False  # configured is not evidence of live audio
    assert state["status_stale"] is False
    unknown = client.get("/stream/control?node_name=unknown").json()
    assert unknown["connection_allowed"] is False
    before = (tmp_path / "state.json").read_text()
    for desired in (False, True):
        response = client.post("/stream/control", json={"stream_enabled": desired})
        assert response.status_code == 409
    assert (tmp_path / "state.json").read_text() == before


def test_capture_usb_timeout_and_next_capture_recovers(monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return SimpleNamespace(returncode=0, stdout=b"\x01\x00" * 8000)
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match="agotada"):
        capture(1, 8000)
    assert len(capture(1, 8000)) == 16000
    assert calls[0]["timeout"] == 16


def test_partial_capture_is_not_presented_as_success(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=b"\0" * 4))
    with pytest.raises(RuntimeError, match="incompleta"):
        capture(1, 8000)
