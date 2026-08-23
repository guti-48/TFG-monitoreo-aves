from datetime import datetime, timezone


def _activate(client, *, node, site_code, site_name, public_id, started_at, lat, lon):
    return client.post(
        "/node/deployments/activate",
        json={
            "device_name": node,
            "deployment_public_id": public_id,
            "site": {
                "code": site_code,
                "name": site_name,
                "municipality": site_name,
                "region": "Andalucia",
                "country_code": "ES",
                "lat": lat,
                "lon": lon,
                "location_source": "manual",
                "location_accuracy_m": 20,
                "timezone": "Europe/Madrid",
            },
            "started_at": started_at,
        },
    )


def _create_site(client, *, code, name, lat=None, lon=None):
    payload = {
        "code": code,
        "name": name,
        "municipality": name,
        "region": "Andalucia",
        "country_code": "ES",
        "location_source": "manual" if lat is not None else "unknown",
        "timezone": "Europe/Madrid",
    }
    if lat is not None:
        payload.update({"lat": lat, "lon": lon, "location_accuracy_m": 20})
    response = client.post("/sites/", json=payload)
    assert response.status_code == 200
    return response.json()


def test_orden_remota_no_cambia_datos_hasta_que_el_nodo_la_aplica(
    client,
    monkeypatch,
):
    monkeypatch.setenv("BIRDMONITOR_PRIMARY_NODE_NAME", "birdmonitor")
    initial = _activate(
        client,
        node="birdmonitor",
        site_code="fase6-control-sevilla",
        site_name="Sevilla control remoto",
        public_id="61000000-0000-4000-8000-000000000001",
        started_at="2026-08-23T08:00:00+00:00",
        lat=37.3891,
        lon=-5.9845,
    )
    assert initial.status_code == 200
    initial_data = initial.json()
    target = _create_site(
        client,
        code="fase6-control-algeciras",
        name="Algeciras control remoto",
        lat=36.12942,
        lon=-5.45303,
    )

    requested = client.post(
        f"/devices/{initial_data['device_id']}/location-commands",
        json={
            "target_site_id": target["id"],
            "confirm_site_code": target["code"],
            "notes": "Cambio solicitado desde el dashboard de pruebas",
        },
    )
    assert requested.status_code == 200
    command = requested.json()
    assert command["status"] == "pending"
    assert command["target_site_code"] == target["code"]
    assert command["target_site_lat"] == 36.12942
    assert command["delivery_count"] == 0

    # Crear la orden no cambia todavía la campaña física ni el histórico.
    devices = client.get("/devices/").json()
    device = next(item for item in devices if item["id"] == initial_data["device_id"])
    assert device["location"] == "Sevilla control remoto"
    assert client.get(
        f"/sites/{initial_data['site_id']}/deployments"
    ).json()[0]["active"] is True

    duplicate = client.post(
        f"/devices/{initial_data['device_id']}/location-commands",
        json={
            "target_site_id": target["id"],
            "confirm_site_code": target["code"],
        },
    )
    assert duplicate.status_code == 409

    delivered = client.get(
        "/node/location-command",
        params={"device_name": "birdmonitor"},
    )
    assert delivered.status_code == 200
    delivered_command = delivered.json()
    assert delivered_command["public_id"] == command["public_id"]
    assert delivered_command["status"] == "delivered"
    assert delivered_command["delivery_count"] == 1

    started_at = datetime.now(timezone.utc).isoformat()
    activation = _activate(
        client,
        node="birdmonitor",
        site_code=delivered_command["target_site_code"],
        site_name=delivered_command["target_site_name"],
        public_id=delivered_command["deployment_public_id"],
        started_at=started_at,
        lat=delivered_command["target_site_lat"],
        lon=delivered_command["target_site_lon"],
    )
    assert activation.status_code == 200

    # Si el nodo se reinicia antes de guardar/confirmar, el servidor conserva
    # la fecha real de activacion y la vuelve a entregar de forma idempotente.
    redelivered = client.get(
        "/node/location-command",
        params={"device_name": "birdmonitor"},
    )
    assert redelivered.status_code == 200
    assert datetime.fromisoformat(
        redelivered.json()["deployment_started_at"]
    ) == datetime.fromisoformat(started_at)

    acknowledged = client.post(
        "/node/location-command/ack",
        json={
            "command_public_id": command["public_id"],
            "status": "applied",
            "deployment_started_at": started_at,
        },
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["status"] == "applied"

    # El ACK es idempotente y el historial conserva ambos despliegues.
    repeated = client.post(
        "/node/location-command/ack",
        json={
            "command_public_id": command["public_id"],
            "status": "applied",
            "deployment_started_at": started_at,
        },
    )
    assert repeated.status_code == 200
    history = client.get(
        f"/devices/{initial_data['device_id']}/deployments"
    ).json()
    relevant_history = [
        item for item in history
        if item["site_code"] in {
            "fase6-control-sevilla",
            "fase6-control-algeciras",
        }
    ]
    assert len(relevant_history) == 2
    assert sum(1 for item in history if item["active"]) == 1
    assert next(item for item in history if item["active"])["site_code"] == target["code"]

    no_pending = client.get(
        "/node/location-command",
        params={"device_name": "birdmonitor"},
    )
    assert no_pending.status_code == 204

    commands = client.get(
        f"/devices/{initial_data['device_id']}/location-commands"
    ).json()
    assert commands[0]["requested_by"] == "admin"
    assert commands[0]["status"] == "applied"
    assert commands[0]["applied_at"] is not None


def test_validacion_y_cancelacion_de_orden_remota(client, monkeypatch):
    monkeypatch.setenv("BIRDMONITOR_PRIMARY_NODE_NAME", "birdmonitor")
    devices = client.get("/devices/").json()
    device = next(item for item in devices if item["name"] == "birdmonitor")
    target = _create_site(
        client,
        code="fase6-control-sanguesa",
        name="Sanguesa control remoto",
        lat=42.574,
        lon=-1.282,
    )

    wrong_confirmation = client.post(
        f"/devices/{device['id']}/location-commands",
        json={
            "target_site_id": target["id"],
            "confirm_site_code": "otro-sitio",
        },
    )
    assert wrong_confirmation.status_code == 422

    no_coordinates = _create_site(
        client,
        code="fase6-control-sin-coordenadas",
        name="Sitio incompleto para control remoto",
    )
    incomplete = client.post(
        f"/devices/{device['id']}/location-commands",
        json={
            "target_site_id": no_coordinates["id"],
            "confirm_site_code": no_coordinates["code"],
        },
    )
    assert incomplete.status_code == 409

    created = client.post(
        f"/devices/{device['id']}/location-commands",
        json={
            "target_site_id": target["id"],
            "confirm_site_code": target["code"],
        },
    )
    assert created.status_code == 200
    cancelled = client.post(
        f"/devices/{device['id']}/location-commands/{created.json()['id']}/cancel"
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    no_pending = client.get(
        "/node/location-command",
        params={"device_name": "birdmonitor"},
    )
    assert no_pending.status_code == 204
