import pytest
import requests

from hardware.raspberry_pi import supervisor


class FakeResponse:
    def __init__(self, status_code=200, text="#EXTM3U\n"):
        self.status_code = status_code
        self.text = text


def test_get_hls_health_validates_manifest(monkeypatch):
    captured = {}

    def fake_get(*args, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(
        supervisor.requests,
        "get",
        fake_get,
    )
    monkeypatch.setattr(
        supervisor,
        "backend_auth_headers",
        lambda: {"Authorization": "Bearer nodo-test"},
    )

    available, detail = supervisor.get_hls_health("http://server:8888/audio/index.m3u8")

    assert available is True
    assert detail == ""
    assert captured["headers"] == {
        "Authorization": "Bearer nodo-test",
    }


def test_get_hls_health_reports_connection_error(monkeypatch):
    def fail_request(*args, **kwargs):
        raise requests.ConnectionError("sin conexion")

    monkeypatch.setattr(supervisor.requests, "get", fail_request)

    available, detail = supervisor.get_hls_health("http://server:8888/audio/index.m3u8")

    assert available is False
    assert "sin conexion" in detail


def test_main_restarts_active_service_after_consecutive_hls_failures(monkeypatch):
    actions = []
    reports = []
    sleep_calls = 0

    monkeypatch.setattr(supervisor, "HLS_FAILURE_LIMIT", 2)
    monkeypatch.setattr(
        supervisor,
        "get_control_state",
        lambda: {
            "stream_enabled": True,
            "hls_url": "http://server:8888/audio/index.m3u8",
        },
    )
    monkeypatch.setattr(supervisor, "is_stream_running", lambda: True)
    monkeypatch.setattr(
        supervisor,
        "get_hls_health",
        lambda hls_url: (False, "HTTP 404"),
    )
    monkeypatch.setattr(
        supervisor,
        "run_systemctl",
        lambda action: actions.append(action) or True,
    )
    monkeypatch.setattr(
        supervisor,
        "report_status",
        lambda running, detail="": reports.append((running, detail)),
    )
    monkeypatch.setattr(supervisor, "log", lambda message: None)

    def stop_after_two_iterations(seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 2:
            raise StopIteration

    monkeypatch.setattr(supervisor.time, "sleep", stop_after_two_iterations)

    with pytest.raises(StopIteration):
        supervisor.main()

    assert actions == ["restart"]
    assert reports[-1] == (True, "Streaming reiniciado tras perder la publicacion HLS")
