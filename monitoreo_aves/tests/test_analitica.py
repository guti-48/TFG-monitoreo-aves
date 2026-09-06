from datetime import datetime, timezone


def test_actividad_diaria_agrupa_por_hora_y_filtra_ruido(client):
    client.post(
        "/devices/",
        json={
            "name": "raspberry-test-analitica",
            "location": "Bosque Test",
            "lat": 40.42,
            "lon": -3.71,
        },
    )

    detecciones = [
        {
            "species": "Common Kingfisher",
            "confidence": 0.9,
            "timestamp": datetime(2026, 5, 10, 6, 10, 0, tzinfo=timezone.utc).isoformat(),
            "filename": "record_2026-05-10_06-10-00.wav",
            "device_name": "raspberry-test-analitica",
            "amplitude": 0.11,
        },
        {
            "species": "White Stork",
            "confidence": 0.8,
            "timestamp": datetime(2026, 5, 10, 6, 20, 0, tzinfo=timezone.utc).isoformat(),
            "filename": "record_2026-05-10_06-20-00.wav",
            "device_name": "raspberry-test-analitica",
            "amplitude": 0.10,
        },
        {
            "species": "Noise_Ruido Ambiente",
            "confidence": 1.0,
            "timestamp": datetime(2026, 5, 10, 6, 30, 0, tzinfo=timezone.utc).isoformat(),
            "filename": "record_2026-05-10_06-30-00.wav",
            "device_name": "raspberry-test-analitica",
            "amplitude": 0.20,
        },
        {
            "species": "Red Kite",
            "confidence": 0.95,
            "timestamp": datetime(2026, 5, 11, 6, 10, 0, tzinfo=timezone.utc).isoformat(),
            "filename": "record_2026-05-11_06-10-00.wav",
            "device_name": "raspberry-test-analitica",
            "amplitude": 0.09,
        },
    ]

    for deteccion in detecciones:
        response = client.post("/detections/", json=deteccion)
        assert response.status_code == 200

    response = client.get("/analytics/daily-activity", params={"date": "2026-05-10"})

    assert response.status_code == 200

    actividad = response.json()

    assert len(actividad) == 24

    hora_6 = actividad[6]

    assert hora_6["hora"] == 6
    assert hora_6["total_detecciones"] == 2
    assert hora_6["confianza_media"] == 0.85
    assert hora_6["especies_activas"] == 2
    assert set(hora_6["lista_especies"]) == {"Common Kingfisher", "White Stork"}
    assert actividad[7]["total_detecciones"] == 0


def test_error_del_mapa_no_expone_detalles_internos(client, monkeypatch):
    from backend.app.features.analytics import routes

    def fallar_mapa(**_kwargs):
        raise RuntimeError("C:/ruta/privada/base-de-datos.db")

    monkeypatch.setattr(routes, "obetenerDatosMapa", fallar_mapa)

    response = client.get("/analytics/map")

    assert response.status_code == 200
    assert response.json() == {"error": "No se pudo generar el mapa"}
    assert "ruta/privada" not in response.text
