from scripts.raspberry_pi.configure_stream_publisher import (
    PUBLISH_URL_VARIABLE,
    build_publish_url,
    secure_service_content,
    secure_service_contents,
    server_host_matches_mode,
    verify_service_stability,
)
from subprocess import CompletedProcess

import pytest


def test_construye_url_rtsp_codificando_las_credenciales():
    url = build_publish_url(
        "100.98.248.58",
        "birdmonitor-publisher",
        "password+seguro/muy_largo-123456",
        "birdmonitor-audio",
    )

    assert url == (
        "rtsp://birdmonitor-publisher:"
        "password%2Bseguro%2Fmuy_largo-123456"
        "@100.98.248.58:8554/birdmonitor-audio"
    )


def test_transforma_unidad_sin_guardar_la_credencial():
    original = """[Unit]
Description=BirdMonitor stream

[Service]
ExecStart=/usr/bin/ffmpeg -f alsa -i hw:3,0 -f rtsp rtsp://server:8554/birdmonitor-audio
"""

    updated = secure_service_content(original)

    assert (
        "EnvironmentFile=/etc/birdmonitor/stream-publisher.env"
        in updated
    )
    assert PUBLISH_URL_VARIABLE in updated
    assert "rtsp://server:8554" not in updated
    assert secure_service_content(updated) == updated


def test_actualiza_url_rtsp_de_un_override_que_tiene_prioridad():
    primary = """[Service]
EnvironmentFile=/etc/birdmonitor/stream-publisher.env
ExecStart=/usr/bin/ffmpeg -f rtsp ${BIRDMONITOR_STREAM_PUBLISH_URL}
"""
    override = """[Service]
ExecStart=
ExecStart=/usr/bin/ffmpeg -f rtsp rtsp://server:8554/birdmonitor-audio
"""

    updated_primary, updated_override = secure_service_contents(
        [primary, override]
    )

    assert updated_primary == primary
    assert PUBLISH_URL_VARIABLE in updated_override
    assert "rtsp://server:8554" not in updated_override


def test_valida_host_segun_modo_de_red():
    assert server_host_matches_mode("local", "192.168.1.32")
    assert server_host_matches_mode("tailscale", "100.98.248.58")
    assert not server_host_matches_mode("local", "100.98.248.58")
    assert not server_host_matches_mode("tailscale", "192.168.1.32")


def test_detecta_servicio_que_se_reinicia_durante_la_validacion(monkeypatch):
    from scripts.raspberry_pi import configure_stream_publisher as configure

    restart_counts = iter((2, 3))

    def fake_systemctl(*arguments, check=True):
        if "--property=NRestarts" in arguments:
            return CompletedProcess(arguments, 0, f"{next(restart_counts)}\n", "")
        return CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(configure, "run_systemctl", fake_systemctl)
    monkeypatch.setattr(configure.time, "sleep", lambda seconds: None)

    with pytest.raises(RuntimeError, match="se reinicio 1"):
        verify_service_stability("birdstream.service")


def test_acepta_servicio_activo_y_estable(monkeypatch):
    from scripts.raspberry_pi import configure_stream_publisher as configure

    def fake_systemctl(*arguments, check=True):
        if "--property=NRestarts" in arguments:
            return CompletedProcess(arguments, 0, "4\n", "")
        return CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(configure, "run_systemctl", fake_systemctl)
    monkeypatch.setattr(configure.time, "sleep", lambda seconds: None)

    verify_service_stability("birdstream.service")
