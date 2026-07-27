def test_control_streaming_guarda_estado_deseado_y_estado_real(client, tmp_path, monkeypatch):
    from backend.app import streaming

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
    assert default_response.json()["stream_path"] == "raspberry-test-stream-audio"
    assert default_response.json()["hls_url"] == (
        "http://testserver:8888/raspberry-test-stream-audio/index.m3u8"
    )
    assert default_response.json()["page_url"] == (
        "http://testserver:8888/raspberry-test-stream-audio/"
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
            "detail": "birdstream.service activo",
        },
    )

    assert status_response.status_code == 200
    assert status_response.json()["stream_enabled"] is True
    assert status_response.json()["actual_running"] is True
    assert status_response.json()["detail"] == "birdstream.service activo"

    persisted_response = client.get(
        "/stream/control",
        params={"node_name": "raspberry-test-stream"},
    )

    assert persisted_response.status_code == 200
    assert persisted_response.json()["stream_enabled"] is True
    assert persisted_response.json()["actual_running"] is True
    assert persisted_response.json()["stream_path"] == "directo-principal"
    assert persisted_response.json()["hls_url"] == (
        "http://testserver:8888/directo-principal/index.m3u8"
    )
    assert persisted_response.json()["rtsp_url"] == (
        "rtsp://testserver:8554/directo-principal"
    )
    assert stream_control_file.exists()


def test_control_streaming_adapta_urls_al_host_del_cliente(client, tmp_path, monkeypatch):
    from backend.app import streaming

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
        "http://100.98.248.58:8888/birdmonitor-audio/index.m3u8"
    )
    assert response.json()["page_url"] == (
        "http://100.98.248.58:8888/birdmonitor-audio/"
    )
    assert response.json()["rtsp_url"] == (
        "rtsp://100.98.248.58:8554/birdmonitor-audio"
    )