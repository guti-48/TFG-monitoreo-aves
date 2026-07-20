def test_control_streaming_guarda_estado_deseado_y_estado_real(client, tmp_path, monkeypatch):
    from backend.app import main

    stream_control_file = tmp_path / "stream_control.json"
    monkeypatch.setattr(main, "STREAM_CONTROL_FILE", stream_control_file)

    default_response = client.get(
        "/stream/control",
        params={"node_name": "raspberry-test-stream"},
    )

    assert default_response.status_code == 200
    assert default_response.json()["stream_enabled"] is False
    assert default_response.json()["actual_running"] is False

    control_response = client.post(
        "/stream/control",
        json={
            "node_name": "raspberry-test-stream",
            "stream_enabled": True,
        },
    )

    assert control_response.status_code == 200
    assert control_response.json()["stream_enabled"] is True

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
    assert stream_control_file.exists()
