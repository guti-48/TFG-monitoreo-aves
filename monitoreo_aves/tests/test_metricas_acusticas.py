from datetime import datetime, timezone


def test_metrica_acustica_repetida_es_idempotente(client):
    timestamp = datetime(2026, 5, 10, 15, 56, 44, tzinfo=timezone.utc)
    payload = {
        "timestamp": timestamp.isoformat(),
        "filename": "record_2026-05-10_15-56-44.wav",
        "device_name": "raspberry-test-metricas",
        "sample_rate": 48000,
        "duration": 60.0,
        "rms": 0.013,
        "peak": 0.42,
        "clipping_ratio": 0.0002,
        "dc_offset": 0.0001,
        "noise_floor_rms": 0.004,
        "quality_status": "ok",
        "quality_detail": "Captura dentro de los limites configurados.",
        "mic_device": "USB Audio Device",
        "birdnet_model": "BirdNET-Analyzer",
        "birdnet_model_version": "2.4",
        "birdnetlib_version": "0.18.1",
        "aci": 504.4,
        "adi": 0.570,
        "aei": 0.810,
        "bio": 36.53,
        "ndsi": -0.560,
        "ht": 0.919,
        "hf": 0.635,
        "h": 0.583,
    }

    first_response = client.post("/audio-metrics/", json=payload)
    second_response = client.post("/audio-metrics/", json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["id"] == first_response.json()["id"]

    metrics_response = client.get("/audio-metrics/", params={"limit": 20})

    assert metrics_response.status_code == 200

    matching_metrics = [
        metric
        for metric in metrics_response.json()
        if metric["device_id"] == first_response.json()["device_id"]
        and metric["filename"] == payload["filename"]
    ]

    assert len(matching_metrics) == 1
    assert matching_metrics[0]["sample_rate"] == payload["sample_rate"]
    assert matching_metrics[0]["duration"] == payload["duration"]
    assert matching_metrics[0]["ndsi"] == payload["ndsi"]
    assert matching_metrics[0]["peak"] == payload["peak"]
    assert matching_metrics[0]["quality_status"] == "ok"
    assert matching_metrics[0]["birdnet_model_version"] == "2.4"


def test_metrica_de_nodo_antiguo_sigue_siendo_compatible(client):
    payload = {
        "timestamp": datetime(2026, 5, 10, 16, 1, 0, tzinfo=timezone.utc).isoformat(),
        "filename": "record_legacy.wav",
        "device_name": "raspberry-test-metricas",
        "sample_rate": 48000,
        "duration": 60.0,
        "rms": 0.01,
        "aci": 10.0,
        "adi": 0.5,
        "aei": 0.5,
        "bio": 1.0,
        "ndsi": 0.0,
        "ht": 0.5,
        "hf": 0.5,
        "h": 0.25,
    }

    response = client.post("/audio-metrics/", json=payload)

    assert response.status_code == 200
    assert response.json()["quality_status"] == "unknown"
    assert response.json()["peak"] == 0.0
