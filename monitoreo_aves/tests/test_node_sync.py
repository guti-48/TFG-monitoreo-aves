import node_sync


def test_deteccion_conserva_tiempos_en_la_cola_offline(monkeypatch):
    captured = {}

    def fake_guardar_evento(event_type, payload, error):
        captured.update(event_type=event_type, payload=payload, error=error)

    monkeypatch.setattr(node_sync, "guardarEventoOffline", fake_guardar_evento)

    node_sync.guardarBackupLocal(
        species="Barn Swallow",
        confidence=0.91,
        timestamp="2026-07-22T14:30:00",
        amplitude=0.12,
        filename="record_2026-07-22_14-30-00",
        audio_start_seconds=16.5,
        audio_end_seconds=19.5,
    )

    assert captured["event_type"] == "detection"
    assert captured["payload"]["audio_start_seconds"] == 16.5
    assert captured["payload"]["audio_end_seconds"] == 19.5


def test_deteccion_envia_tiempos_al_backend(monkeypatch):
    captured = {}

    class SuccessfulResponse:
        status_code = 200

    def fake_post(url, json, headers, timeout):
        captured.update(
            url=url,
            payload=json,
            headers=headers,
            timeout=timeout,
        )
        return SuccessfulResponse()

    monkeypatch.setattr(node_sync.requests, "post", fake_post)
    monkeypatch.setattr(node_sync, "subirArchivos", lambda filename: True)
    monkeypatch.setattr(node_sync, "sincronizarRespaldo", lambda: None)
    monkeypatch.setattr(
        node_sync,
        "getBackendAuthHeaders",
        lambda: {"Authorization": "Bearer token-test"},
    )

    node_sync.enviarDatosServidor(
        species="Barn Swallow",
        confidence=0.91,
        filename="record_2026-07-22_14-30-00",
        timestamp_str="2026-07-22T14:30:00",
        amplitude=0.12,
        audio_start_seconds=16.5,
        audio_end_seconds=19.5,
    )

    assert captured["payload"]["filename"] == "record_2026-07-22_14-30-00.wav"
    assert captured["payload"]["audio_start_seconds"] == 16.5
    assert captured["payload"]["audio_end_seconds"] == 19.5
    assert captured["headers"]["Authorization"] == "Bearer token-test"


def test_metricas_envian_diagnostico_aunque_fallen_indices(monkeypatch):
    captured = {}

    class SuccessfulResponse:
        status_code = 200

    def fake_post(url, json, headers, timeout):
        captured.update(
            url=url,
            payload=json,
            headers=headers,
            timeout=timeout,
        )
        return SuccessfulResponse()

    monkeypatch.setattr(node_sync.requests, "post", fake_post)

    node_sync.enviarMetricasAcusticas(
        None,
        "record_2026-07-22_14-30-00.wav",
        "2026-07-22T14:30:00",
        0.012,
        calidad_audio={
            "peak": 0.7,
            "clipping_ratio": 0.0,
            "dc_offset": 0.001,
            "noise_floor_rms": 0.004,
            "quality_status": "ok",
            "quality_detail": "Captura correcta",
            "mic_device": "USB Mic",
        },
        birdnet_info={
            "model_name": "BirdNET-Analyzer",
            "model_version": "2.4",
            "birdnetlib_version": "0.18.1",
        },
    )

    assert captured["payload"]["quality_status"] == "ok"
    assert captured["payload"]["birdnet_model_version"] == "2.4"
    assert captured["payload"]["acoustic_metrics_version"] == "legacy-v1"
    assert captured["payload"]["aci"] == 0.0


def test_metricas_v2_quedan_en_cola_si_backend_no_confirma_version(
    monkeypatch,
):
    queued = {}

    class OldBackendResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"id": 1}

    monkeypatch.setattr(
        node_sync.requests,
        "post",
        lambda *args, **kwargs: OldBackendResponse(),
    )
    monkeypatch.setattr(
        node_sync,
        "guardarEventoOffline",
        lambda event_type, payload, error: queued.update(
            event_type=event_type,
            payload=payload,
            error=error,
        ),
    )

    node_sync.enviarMetricasAcusticas(
        {
            "acoustic_metrics_version": "maad-v2",
            "aci": 1.0,
            "adi": 0.5,
            "aei": 0.3,
            "bio": 1.0,
            "ndsi": 0.0,
            "ht": 0.7,
            "hf": 0.6,
            "h": 0.42,
        },
        "record_v2.wav",
        "2026-07-27T15:00:00",
        0.01,
    )

    assert queued["event_type"] == "audio_metric"
    assert queued["payload"]["acoustic_metrics_version"] == "maad-v2"
    assert "sin soporte confirmado" in queued["error"]
