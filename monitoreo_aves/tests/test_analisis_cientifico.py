from datetime import datetime, timedelta, timezone

import pytest


def _metric(node, timestamp, filename, version, **valores):
    payload = {
        "timestamp": timestamp.isoformat(),
        "filename": filename,
        "device_name": node,
        "sample_rate": 48000,
        "duration": 60.0,
        "rms": 0.01,
        "acoustic_metrics_version": version,
        "aci": 100.0,
        "adi": 0.7,
        "aei": 0.3,
        "bio": 10.0,
        "ndsi": -0.2,
        "ht": 0.8,
        "hf": 0.6,
        "h": 0.48,
    }
    payload.update(valores)
    return payload


def _crear_nodo(client, node):
    response = client.post(
        "/devices/",
        json={"name": node, "location": "Parque", "lat": 37.38, "lon": -5.98, "location_source": "manual"},
    )
    assert response.status_code == 200


def test_serie_acustica_agrupa_por_dia_y_hora_y_excluye_el_metodo_antiguo(client):
    node = "raspberry-serie"
    _crear_nodo(client, node)

    base = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)
    muestras = [
        # dia 1: dos muestras a las 06 h y una a las 18 h
        (base, "a.wav", "maad-v2", {"ndsi": 0.1}),
        (base + timedelta(minutes=5), "b.wav", "maad-v2", {"ndsi": 0.3}),
        (base + timedelta(hours=12), "c.wav", "maad-v2", {"ndsi": -0.5}),
        # dia 2
        (base + timedelta(days=1), "d.wav", "maad-v2", {"ndsi": 0.5}),
        # metodo antiguo: no debe entrar en ninguna media
        (base + timedelta(minutes=10), "viejo.wav", "legacy-v1", {"ndsi": 0.99}),
    ]
    for timestamp, filename, version, valores in muestras:
        response = client.post("/audio-metrics/", json=_metric(node, timestamp, filename, version, **valores))
        assert response.status_code == 200
    device_id = response.json()["device_id"]

    response = client.get("/analytics/acoustic-series", params={"device_id": device_id})
    assert response.status_code == 200
    serie = response.json()

    assert serie["available"] is True
    assert serie["metrics_version"] == "maad-v2"
    assert serie["samples"] == 4
    assert serie["legacy_excluded"] == 1
    assert serie["days"] == 2
    assert {item["key"] for item in serie["indices"]} == {"aci", "adi", "aei", "bio", "ndsi", "h"}

    dias = {fila["date"]: fila for fila in serie["daily"]}
    primero = dias["2026-10-01"]
    assert primero["n"] == 3
    assert primero["ndsi"] == pytest.approx((0.1 + 0.3 - 0.5) / 3, abs=0.001)
    assert primero["low_sample"] is True  # muy por debajo de las muestras minimas por dia

    horas = {fila["hour"]: fila for fila in serie["hourly"]}
    # a las 06 h entran tres muestras: dos del dia 1 y la del dia 2
    assert horas[6]["n"] == 3 and horas[6]["ndsi"] == pytest.approx((0.1 + 0.3 + 0.5) / 3, abs=0.001)
    assert horas[18]["n"] == 1


def test_serie_acustica_sin_datos_del_metodo_actual_devuelve_no_disponible(client):
    node = "raspberry-solo-antiguo"
    _crear_nodo(client, node)
    response = client.post(
        "/audio-metrics/",
        json=_metric(node, datetime(2026, 7, 1, 6, 0, tzinfo=timezone.utc), "solo-viejo.wav", "legacy-v1"),
    )
    assert response.status_code == 200
    device_id = response.json()["device_id"]

    serie = client.get("/analytics/acoustic-series", params={"device_id": device_id}).json()

    assert serie["available"] is False
    assert serie["legacy_excluded"] == 1
    assert serie["daily"] == [] and serie["hourly"] == []


def _detection(client, node, timestamp, species, filename):
    response = client.post(
        "/detections/",
        json={
            "species": species,
            "confidence": 0.9,
            "timestamp": timestamp.isoformat(),
            "filename": filename,
            "device_name": node,
            "amplitude": 0.02,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_actividad_por_hora_devuelve_24_horas_y_no_cuenta_el_ruido(client):
    node = "raspberry-actividad"
    _crear_nodo(client, node)
    base = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)

    _detection(client, node, base, "Species one", "a.wav")                              # 06 h
    _detection(client, node, base + timedelta(minutes=5), "Species two", "b.wav")       # 06 h
    _detection(client, node, base + timedelta(hours=12), "Species one", "c.wav")        # 18 h
    _detection(client, node, base + timedelta(hours=6), "Noise_Ruido Ambiente", "d.wav")  # 12 h, ruido
    device_id = _detection(client, node, base + timedelta(days=1), "Species one", "e.wav")["device_id"]  # 06 h

    actividad = client.get("/analytics/activity", params={"device_id": device_id}).json()

    assert actividad["available"] is True
    assert actividad["total"] == 4  # el ruido no es una deteccion de ave
    assert actividad["days"] == 2
    assert len(actividad["hourly"]) == 24  # siempre las 24 horas, tambien las vacias
    assert [fila["hour"] for fila in actividad["hourly"]] == list(range(24))

    horas = {fila["hour"]: fila for fila in actividad["hourly"]}
    # a las 06 h: dos detecciones del dia 1 y una del dia 2, de dos especies distintas
    assert horas[6] == {"hour": 6, "detections": 3, "species": 2}
    assert horas[18] == {"hour": 18, "detections": 1, "species": 1}
    assert horas[12] == {"hour": 12, "detections": 0, "species": 0}  # solo habia ruido


def test_actividad_por_hora_sin_detecciones_devuelve_no_disponible(client):
    node = "raspberry-actividad-vacia"
    _crear_nodo(client, node)
    metrica = client.post(
        "/audio-metrics/",
        json=_metric(node, datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc), "solo-metrica.wav", "maad-v2"),
    )
    assert metrica.status_code == 200

    actividad = client.get("/analytics/activity", params={"device_id": metrica.json()["device_id"]}).json()

    assert actividad["available"] is False
    assert actividad["hourly"] == []
    assert "reason" in actividad
