from datetime import datetime, timedelta, timezone

import pytest


def _post_detection(client, *, node, timestamp, species, filename):
    response = client.post(
        "/detections/",
        json={
            "species": species,
            "confidence": 0.91,
            "timestamp": timestamp.isoformat(),
            "filename": filename,
            "device_name": node,
            "amplitude": 0.02,
        },
    )
    assert response.status_code == 200
    return response.json()


def _metric_payload(*, node, timestamp, filename, version, aei):
    return {
        "timestamp": timestamp.isoformat(),
        "filename": filename,
        "device_name": node,
        "sample_rate": 48000,
        "duration": 60.0,
        "rms": 0.01,
        "acoustic_metrics_version": version,
        "aci": 120.0,
        "adi": 0.7,
        "aei": aei,
        "bio": 10.0,
        "ndsi": -0.2,
        "ht": 0.8,
        "hf": 0.6,
        "h": 0.48,
    }


def test_reporte_y_mapa_usan_el_mismo_nodo_y_no_mezclan_metricas_legacy(
    client,
):
    node = "raspberry-eco-v2"
    created = client.post(
        "/devices/",
        json={
            "name": node,
            "location": "Parque de prueba",
            "lat": 37.3891,
            "lon": -5.9845,
            "location_source": "manual",
        },
    )
    assert created.status_code == 200

    timestamp = datetime(2026, 7, 27, 6, 0, tzinfo=timezone.utc)
    first = _post_detection(
        client,
        node=node,
        timestamp=timestamp,
        species="Species one",
        filename="eco-one.wav",
    )
    _post_detection(
        client,
        node=node,
        timestamp=timestamp + timedelta(minutes=1),
        species="Species two",
        filename="eco-two.wav",
    )

    legacy = client.post(
        "/audio-metrics/",
        json=_metric_payload(
            node=node,
            timestamp=timestamp,
            filename="eco-legacy.wav",
            version="legacy-v1",
            aei=0.99,
        ),
    )
    current = client.post(
        "/audio-metrics/",
        json=_metric_payload(
            node=node,
            timestamp=timestamp + timedelta(minutes=1),
            filename="eco-current.wav",
            version="maad-v2",
            aei=0.31,
        ),
    )
    assert legacy.status_code == current.status_code == 200

    report_response = client.get("/analytics/biodiversity")
    assert report_response.status_code == 200
    report = next(
        item
        for item in report_response.json()
        if item["device_id"] == first["device_id"]
    )

    assert report["calidad"] == "DESCRIPTIVO"
    assert report["abundancia"] == 2
    assert report["riqueza"] == 2
    assert report["shannon"] == pytest.approx(0.693, abs=0.001)
    assert report["metrics_version"] == "maad-v2"
    assert report["metric_samples"] == 1
    assert report["legacy_metric_samples"] == 1
    assert report["aei_avg"] == pytest.approx(0.31)

    map_response = client.get(
        "/analytics/map",
        params={"device_id": first["device_id"]},
    )
    assert map_response.status_code == 200
    map_data = map_response.json()
    assert map_data["available"] is True
    assert map_data["event_count"] == 2
    assert map_data["species_count"] == 2
    assert map_data["shannon"] == report["shannon"]
    assert map_data["reference_radius_m"] == 25.0
    assert map_data["range_basis"] == "uncalibrated_local_reference"


def test_mapa_no_inventa_ubicacion_si_el_nodo_no_tiene_coordenadas(client):
    node = "raspberry-eco-sin-coordenadas"
    created = client.post(
        "/devices/",
        json={
            "name": node,
            "location": "Sin coordenadas",
        },
    )
    assert created.status_code == 200
    device_id = next(
        item["id"]
        for item in client.get("/devices/").json()
        if item["name"] == node
    )

    response = client.get(
        "/analytics/map",
        params={"device_id": device_id},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert "lat" not in data
    assert "lon" not in data
    assert "IP" in data["error"]


def test_mapa_oculta_radio_si_la_coordenada_procede_de_ip(client):
    node = "raspberry-eco-ip-aproximada"
    created = client.post(
        "/devices/",
        json={
            "name": node,
            "location": "Sevilla aproximada",
            "lat": 37.38,
            "lon": -5.98,
            "location_source": "ip_geolocation",
        },
    )
    assert created.status_code == 200
    device_id = next(
        item["id"]
        for item in client.get("/devices/").json()
        if item["name"] == node
    )

    data = client.get(
        "/analytics/map",
        params={"device_id": device_id},
    ).json()
    assert data["available"] is True
    assert data["location_is_precise"] is False
    assert data["location_source"] == "ip_geolocation"
    assert data["reference_radius_m"] == 0.0
    assert data["requested_reference_radius_m"] == 25.0