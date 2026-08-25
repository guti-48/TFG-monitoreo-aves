import json
from datetime import datetime, timedelta, timezone


def test_control_streaming_guarda_estado_deseado_y_estado_real(client, tmp_path, monkeypatch):
    from backend.app.features.streaming import routes as streaming

    stream_control_file = tmp_path / "stream_control.json"
    monkeypatch.setattr(streaming, "STREAM_CONTROL_FILE", stream_control_file)
    monkeypatch.setattr(streaming, "DEFAULT_STREAM_PATH", "")
    monkeypatch.setattr(streaming, "STREAM_PATH_TEMPLATE", "{node_name}-audio")

    default_response = client.get(
        "/stream/control",
        params={"node_name": "raspberry-test-stream"},
    )

    assert default_response.status_code == 200
    assert default_response.json()["stream_enabled"] is False
    assert default_response.json()["actual_running"] is False
    assert default_response.json()["status_stale"] is True
    assert default_response.json()["playback_ready"] is False
    assert default_response.json()["stream_path"] == "raspberry-test-stream-audio"
    assert default_response.json()["hls_url"] == (
        "http://testserver/stream/hls/"
        "raspberry-test-stream-audio/index.m3u8"
    )
    assert default_response.json()["page_url"] == (
        "http://testserver/stream/hls/raspberry-test-stream-audio/"
    )
    assert default_response.json()["rtsp_url"] == (
        "rtsp://testserver:8554/raspberry-test-stream-audio"
    )

    control_response = client.post(
        "/stream/control",
        json={
            "node_name": "raspberry-test-stream",
            "stream_enabled": True,
            "stream_path": "directo-principal",
        },
    )

    assert control_response.status_code == 200
    assert control_response.json()["stream_enabled"] is True
    assert control_response.json()["stream_path"] == "directo-principal"

    status_response = client.post(
        "/stream/status",
        json={
            "node_name": "raspberry-test-stream",
            "running": True,
            "hls_available": True,
            "detail": "birdstream.service activo",
        },
    )

    assert status_response.status_code == 200
    assert status_response.json()["stream_enabled"] is True
    assert status_response.json()["actual_running"] is True
    assert status_response.json()["hls_available"] is True
    assert status_response.json()["playback_ready"] is True
    assert status_response.json()["status_stale"] is False
    assert status_response.json()["detail"] == "birdstream.service activo"

    persisted_response = client.get(
        "/stream/control",
        params={"node_name": "raspberry-test-stream"},
    )

    assert persisted_response.status_code == 200
    assert persisted_response.json()["stream_enabled"] is True
    assert persisted_response.json()["actual_running"] is True
    assert persisted_response.json()["playback_ready"] is True
    assert persisted_response.json()["stream_path"] == "directo-principal"
    assert persisted_response.json()["hls_url"] == (
        "http://testserver/stream/hls/directo-principal/index.m3u8"
    )
    assert persisted_response.json()["rtsp_url"] == (
        "rtsp://testserver:8554/directo-principal"
    )
    assert stream_control_file.exists()


def test_control_streaming_no_presenta_como_activo_un_reporte_antiguo(
    client,
    tmp_path,
    monkeypatch,
):
    from backend.app.features.streaming import routes as streaming

    stream_control_file = tmp_path / "stream_control.json"
    old_status = datetime.now(timezone.utc) - timedelta(minutes=5)
    stream_control_file.write_text(
        json.dumps(
            {
                "birdmonitor": {
                    "node_name": "birdmonitor",
                    "stream_path": "birdmonitor-audio",
                    "stream_enabled": True,
                    "actual_running": True,
                    "hls_available": True,
                    "detail": "HLS disponible",
                    "updated_at": old_status.isoformat(),
                    "last_status_at": old_status.isoformat(),
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(streaming, "STREAM_CONTROL_FILE", stream_control_file)
    monkeypatch.setattr(streaming, "STREAM_STATUS_STALE_SECONDS", 30)

    response = client.get(
        "/stream/control",
        params={"node_name": "birdmonitor"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status_stale"] is True
    assert payload["last_status_age_seconds"] >= 299
    assert payload["reported_actual_running"] is True
    assert payload["reported_hls_available"] is True
    assert payload["actual_running"] is False
    assert payload["hls_available"] is False
    assert payload["playback_ready"] is False
    assert "telemetria reciente" in payload["detail"]

    persisted = json.loads(stream_control_file.read_text(encoding="utf-8"))
    assert persisted["birdmonitor"]["actual_running"] is True
    assert persisted["birdmonitor"]["hls_available"] is True
    assert "status_stale" not in persisted["birdmonitor"]
    assert "playback_ready" not in persisted["birdmonitor"]


def test_control_streaming_distingue_servicio_activo_de_hls_disponible(
    client,
    tmp_path,
    monkeypatch,
):
    from backend.app.features.streaming import routes as streaming

    monkeypatch.setattr(streaming, "STREAM_CONTROL_FILE", tmp_path / "stream_control.json")

    client.post(
        "/stream/control",
        json={"node_name": "birdmonitor", "stream_enabled": True},
    )
    response = client.post(
        "/stream/status",
        json={
            "node_name": "birdmonitor",
            "running": True,
            "hls_available": False,
            "detail": "Servicio activo; esperando HLS (1/3)",
        },
    )

    assert response.status_code == 200
    assert response.json()["actual_running"] is True
    assert response.json()["hls_available"] is False
    assert response.json()["playback_ready"] is False
    assert response.json()["status_stale"] is False


def test_control_streaming_admite_supervisor_anterior_sin_campo_hls(
    client,
    tmp_path,
    monkeypatch,
):
    from backend.app.features.streaming import routes as streaming

    monkeypatch.setattr(streaming, "STREAM_CONTROL_FILE", tmp_path / "stream_control.json")
    client.post(
        "/stream/control",
        json={"node_name": "birdmonitor", "stream_enabled": True},
    )

    ready = client.post(
        "/stream/status",
        json={
            "node_name": "birdmonitor",
            "running": True,
            "detail": "Estado sincronizado",
        },
    )
    waiting = client.post(
        "/stream/status",
        json={
            "node_name": "birdmonitor",
            "running": True,
            "detail": "Servicio activo; esperando HLS (1/3)",
        },
    )

    assert ready.status_code == 200
    assert ready.json()["playback_ready"] is True
    assert waiting.status_code == 200
    assert waiting.json()["actual_running"] is True
    assert waiting.json()["hls_available"] is False
    assert waiting.json()["playback_ready"] is False


def test_control_streaming_adapta_urls_al_host_del_cliente(client, tmp_path, monkeypatch):
    from backend.app.features.streaming import routes as streaming

    monkeypatch.setattr(streaming, "STREAM_CONTROL_FILE", tmp_path / "stream_control.json")
    monkeypatch.setattr(streaming, "CONFIGURED_STREAM_BASE_URL", None)
    monkeypatch.setattr(streaming, "CONFIGURED_STREAM_RTSP_BASE_URL", None)

    response = client.get(
        "/stream/control",
        params={"node_name": "birdmonitor"},
        headers={"host": "100.98.248.58:8000"},
    )

    assert response.status_code == 200
    assert response.json()["hls_url"] == (
        "http://100.98.248.58:8000/stream/hls/"
        "birdmonitor-audio/index.m3u8"
    )
    assert response.json()["page_url"] == (
        "http://100.98.248.58:8000/stream/hls/birdmonitor-audio/"
    )
    assert response.json()["rtsp_url"] == (
        "rtsp://100.98.248.58:8554/birdmonitor-audio"
    )


def test_stream_path_elimina_segmentos_de_recorrido():
    from backend.app.features.streaming import routes as streaming

    assert (
        streaming._normalize_stream_path("../aves/./directo")
        == "aves/directo"
    )
