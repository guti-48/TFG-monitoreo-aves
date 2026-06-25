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