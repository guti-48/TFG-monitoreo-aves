"""Correcciones del punto mediante la orden existente, sin tocar la BD real."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain.schemas import NodeLocationCoordinates


@pytest.fixture
def coordinate_context(client, monkeypatch):
    node = "coordinates-" + uuid4().hex[:8]
    monkeypatch.setenv("BIRDMONITOR_PRIMARY_NODE_NAME", node)
    payload = {
        "device_name": node,
        "deployment_public_id": str(uuid4()),
        "started_at": "2026-01-01T00:00:00+00:00",
        "site": {
            "code": node, "name": "Punto de prueba",
            "lat": 37.38, "lon": -5.98, "location_source": "manual",
            "location_accuracy_m": 150,
        },
    }
    response = client.post("/node/deployments/activate", json=payload)
    assert response.status_code == 200, response.text
    deployment = response.json()
    url = f"/devices/{deployment['device_id']}/location-commands"
    command_payload = {
        "target_site_id": deployment["site_id"],
        "confirm_site_code": node,
        "coordinates": {"lat": 37.391234, "lon": -6.012345, "location_accuracy_m": 10},
    }
    return payload, deployment, url, command_payload


def test_precise_point_applies_atomically_and_old_retry_does_not_move_it(client, coordinate_context):
    original, deployment, url, request = coordinate_context
    site_url = f"/sites/{deployment['site_id']}"
    observation = {
        "species": "Species coordinate test", "confidence": 0.9, "amplitude": 0.02,
        "timestamp": "2026-01-01T12:00:00+00:00",
        "filename": original["device_name"] + ".wav",
        "device_name": original["device_name"], "site_code": original["site"]["code"],
        "deployment_public_id": original["deployment_public_id"],
    }
    detected = client.post("/detections/", json=observation)
    assert detected.status_code == 200, detected.text
    detection_id = detected.json()["id"]
    command = client.post(url, json=request).json()
    assert command["status"] == "pending"
    assert client.get(site_url).json()["lat"] == original["site"]["lat"]
    delivered = client.get("/node/location-command", params={"device_name": original["device_name"]})
    assert delivered.json()["target_site_lat"] == request["coordinates"]["lat"]
    activation = {
        **original, "deployment_public_id": command["deployment_public_id"],
        "started_at": "2026-01-02T00:00:00+00:00",
        "site": {**original["site"], **request["coordinates"]},
    }
    applied = client.post("/node/deployments/activate", json=activation)
    assert applied.status_code == 200, applied.text
    assert client.post("/node/location-command/ack", json={
        "command_public_id": command["public_id"], "status": "applied",
        "deployment_started_at": activation["started_at"],
    }).status_code == 200
    for retry in (activation, original):
        assert client.post("/node/deployments/activate", json=retry).status_code == 200
        site = client.get(site_url).json()
        assert site["lat"] == request["coordinates"]["lat"]
        assert site["lon"] == request["coordinates"]["lon"]
    history = client.get(f"/sites/{deployment['site_id']}/deployments").json()
    assert len(history) == 2
    assert sum(item["active"] for item in history) == 1
    assert next(item for item in history if item["active"])["public_id"] == command["deployment_public_id"]
    assert client.post(url, json=request).status_code == 409  # no-op
    # Un archivo de la cola antigua sigue perteneciendo a su campaña cerrada.
    delayed = client.post("/detections/", json={**observation,
        "filename": "late-" + observation["filename"], "timestamp": "2026-01-01T13:00:00+00:00"})
    assert delayed.status_code == 200
    rows = client.get("/detections/", params={"deployment_id": deployment["id"]}).json()
    assert {row["id"] for row in rows} == {detection_id, delayed.json()["id"]}


def test_cancel_does_not_update_site_or_authorize_activation(client, coordinate_context):
    original, deployment, url, request = coordinate_context
    command = client.post(url, json=request).json()
    assert client.post(f"{url}/{command['id']}/cancel").status_code == 200
    activation = {**original, "deployment_public_id": command["deployment_public_id"],
                  "site": {**original["site"], **request["coordinates"]}}
    assert client.post("/node/deployments/activate", json=activation).status_code == 409
    assert client.get(f"/sites/{deployment['site_id']}").json()["lat"] == original["site"]["lat"]


def test_rejects_mismatched_and_backdated_coordinate_command(client, coordinate_context):
    original, deployment, url, request = coordinate_context
    command = client.post(url, json=request).json()
    activation = {**original, "deployment_public_id": command["deployment_public_id"],
                  "site": {**original["site"], **request["coordinates"]}}
    activation["site"]["lat"] = 38
    assert client.post("/node/deployments/activate", json=activation).status_code == 409
    activation["site"]["lat"] = request["coordinates"]["lat"]
    activation["started_at"] = "2025-01-01T00:00:00+00:00"
    assert client.post("/node/deployments/activate", json=activation).status_code == 409
    assert client.get(f"/sites/{deployment['site_id']}").json()["lat"] == original["site"]["lat"]


@pytest.mark.parametrize("coordinates", [
    {"lat": 91, "lon": 0}, {"lat": 0, "lon": -181}, {"lat": 0},
    {"lat": float("nan"), "lon": 0}, {"lat": 0, "lon": float("inf")},
    {"lat": 0, "lon": 0, "location_accuracy_m": -1},
    {"lat": 0, "lon": 0, "location_accuracy_m": float("inf")},
])
def test_rejects_invalid_coordinates(coordinates):
    with pytest.raises(ValidationError):
        NodeLocationCoordinates(**coordinates)
