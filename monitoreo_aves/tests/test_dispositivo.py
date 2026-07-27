from datetime import datetime, timezone


def test_registra_y_actualiza_dispositivo_sin_duplicarlo(client):
    payload = {
        "name": "raspberry-test-01",
        "location": "Reserva Norte",
        "lat": 40.4168,
        "lon": -3.7038,
        "location_source": "manual",
        "location_accuracy_m": 10.0,
    }

    response = client.post("/devices/", json=payload)

    assert response.status_code == 200
    assert response.json() == payload

    update_payload = {
        "name": "raspberry-test-01",
        "location": "Reserva Sur",
        "lat": 40.4200,
        "lon": -3.7100,
        "location_source": "gps",
        "location_accuracy_m": 5.0,
    }

    update_response = client.post("/devices/", json=update_payload)

    assert update_response.status_code == 200
    assert update_response.json() == update_payload

    devices_response = client.get("/devices/")

    assert devices_response.status_code == 200

    matching_devices = [
        device
        for device in devices_response.json()
        if device["name"] == "raspberry-test-01"
    ]

    assert len(matching_devices) == 1
    assert matching_devices[0]["location"] == "Reserva Sur"
    assert matching_devices[0]["lat"] == 40.4200
    assert matching_devices[0]["lon"] == -3.7100
    assert matching_devices[0]["location_source"] == "gps"
    assert matching_devices[0]["location_accuracy_m"] == 5.0


def test_deteccion_repetida_es_idempotente(client):
    timestamp = datetime(2026, 5, 10, 15, 51, 44, tzinfo=timezone.utc)
    payload = {
        "species": "Common Kingfisher",
        "confidence": 0.9,
        "timestamp": timestamp.isoformat(),
        "filename": "record_2026-05-10_15-51-44.wav",
        "device_name": "raspberry-test-02",
        "amplitude": 0.12,
    }

    first_response = client.post("/detections/", json=payload)
    second_response = client.post("/detections/", json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["id"] == first_response.json()["id"]

    detections_response = client.get("/detections/", params={"limit": 20})

    assert detections_response.status_code == 200

    matching_detections = [
        detection
        for detection in detections_response.json()
        if detection["device_id"] == first_response.json()["device_id"]
        and detection["species"] == payload["species"]
        and detection["filename"] == payload["filename"]
    ]

    assert len(matching_detections) == 1
    assert matching_detections[0]["confidence"] == payload["confidence"]
    assert matching_detections[0]["amplitude"] == payload["amplitude"]


def test_dispositivo_rechaza_coordenadas_incompletas_o_fuera_de_rango(client):
    incomplete = client.post(
        "/devices/",
        json={
            "name": "raspberry-coords-incompletas",
            "location": "Prueba",
            "lat": 37.38,
        },
    )
    assert incomplete.status_code == 422

    invalid = client.post(
        "/devices/",
        json={
            "name": "raspberry-coords-invalidas",
            "location": "Prueba",
            "lat": 137.38,
            "lon": -5.98,
        },
    )
    assert invalid.status_code == 422