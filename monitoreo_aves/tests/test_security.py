from backend.app.core.security import hash_admin_password, hash_node_token


ADMIN_USERNAME = "admin-test"
ADMIN_PASSWORD = "contrasena-segura-test"
NODE_TOKEN = "token-nodo-test-muy-largo"


def configure_security(monkeypatch):
    monkeypatch.setenv("BIRDMONITOR_SECURITY_MODE", "required")
    monkeypatch.setenv("BIRDMONITOR_ADMIN_USERNAME", ADMIN_USERNAME)
    monkeypatch.setenv(
        "BIRDMONITOR_ADMIN_PASSWORD_HASH",
        hash_admin_password(ADMIN_PASSWORD),
    )
    monkeypatch.setenv(
        "BIRDMONITOR_NODE_TOKEN_HASH",
        hash_node_token(NODE_TOKEN),
    )
    monkeypatch.setenv(
        "BIRDMONITOR_SESSION_SECRET",
        "session-secret-test-con-mas-de-32-caracteres",
    )
    monkeypatch.setenv("BIRDMONITOR_COOKIE_SECURE", "0")


def test_rechaza_api_anonima_y_permite_sesion_administradora(
    client,
    monkeypatch,
):
    configure_security(monkeypatch)
    client.cookies.clear()

    anonymous = client.get("/devices/")
    assert anonymous.status_code == 401
    anonymous_audio = client.get("/records/audio-privado.wav")
    assert anonymous_audio.status_code == 401
    anonymous_spectrogram = client.get("/spectrograms/evidencia-privada.png")
    assert anonymous_spectrogram.status_code == 401
    anonymous_hls = client.get(
        "/stream/hls/birdmonitor-audio/index.m3u8"
    )
    assert anonymous_hls.status_code == 401

    login = client.post(
        "/auth/login",
        data={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD,
        },
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/?location_setup=1"
    assert "birdmonitor_session" in login.cookies

    authenticated = client.get("/devices/")
    assert authenticated.status_code == 200


def test_sesion_administradora_exige_csrf_para_modificaciones(
    client,
    monkeypatch,
):
    configure_security(monkeypatch)
    client.cookies.clear()
    client.post(
        "/auth/login",
        data={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD,
        },
    )

    payload = {
        "name": "nodo-csrf-test",
        "location": "Laboratorio",
    }
    without_csrf = client.post("/devices/", json=payload)
    assert without_csrf.status_code == 403

    with_csrf = client.post(
        "/devices/",
        json=payload,
        headers={"X-BirdMonitor-CSRF": "1"},
    )
    assert with_csrf.status_code == 200


def test_cerrar_sesion_elimina_cookie_y_regresa_al_login(
    client,
    monkeypatch,
):
    configure_security(monkeypatch)
    client.cookies.clear()
    login = client.post(
        "/auth/login",
        data={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD,
        },
        follow_redirects=False,
    )
    assert login.status_code == 303

    logout = client.post("/auth/logout", follow_redirects=False)
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"

    protected_page = client.get(
        "/",
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    assert protected_page.status_code == 303
    assert protected_page.headers["location"] == "/login"


def test_token_nodo_solo_accede_a_rutas_de_ingesta(
    client,
    monkeypatch,
):
    configure_security(monkeypatch)
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {NODE_TOKEN}"}

    ingest = client.post(
        "/devices/",
        json={
            "name": "nodo-token-test",
            "location": "Bosque",
        },
        headers=headers,
    )
    assert ingest.status_code == 200

    forbidden_read = client.get("/devices/", headers=headers)
    assert forbidden_read.status_code == 403
    forbidden_audio = client.get(
        "/records/audio-privado.wav",
        headers=headers,
    )
    assert forbidden_audio.status_code == 403

    forbidden_admin = client.post(
        "/stream/control",
        json={
            "node_name": "nodo-token-test",
            "stream_enabled": True,
        },
        headers=headers,
    )
    assert forbidden_admin.status_code == 403


def test_token_nodo_activa_su_despliegue_pero_no_administra_sitios(
    client,
    monkeypatch,
):
    configure_security(monkeypatch)
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {NODE_TOKEN}"}

    activation = client.post(
        "/node/deployments/activate",
        headers=headers,
        json={
            "device_name": "nodo-token-location-test",
            "deployment_public_id": "34000000-0000-4000-8000-000000000001",
            "site": {
                "code": "fase3-token-site",
                "name": "Sitio del token de nodo",
                "country_code": "ES",
                "lat": 37.38,
                "lon": -6.0,
                "location_source": "manual",
                "timezone": "Europe/Madrid",
            },
            "started_at": "2026-08-09T12:00:00+00:00",
        },
    )
    assert activation.status_code == 200

    forbidden_site_admin = client.post(
        "/sites/",
        headers=headers,
        json={"code": "token-no-admin", "name": "No permitido"},
    )
    assert forbidden_site_admin.status_code == 403

    allowed_legacy_lookup = client.get(
        "/node/deployments/legacy-context",
        headers=headers,
        params={"device_name": "nodo-inexistente-token"},
    )
    assert allowed_legacy_lookup.status_code == 404


def test_cambio_remoto_ubicacion_separa_permisos_admin_y_nodo(
    client,
    monkeypatch,
):
    configure_security(monkeypatch)
    monkeypatch.setenv("BIRDMONITOR_PRIMARY_NODE_NAME", "birdmonitor")
    client.cookies.clear()

    login = client.post(
        "/auth/login",
        data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200

    device_response = client.post(
        "/devices/",
        headers={"X-BirdMonitor-CSRF": "1"},
        json={"name": "birdmonitor", "location": "Sin asignar"},
    )
    assert device_response.status_code == 200
    device = next(
        item for item in client.get("/devices/").json()
        if item["name"] == "birdmonitor"
    )
    site = client.post(
        "/sites/",
        headers={"X-BirdMonitor-CSRF": "1"},
        json={
            "code": "security-remote-location",
            "name": "Sitio seguro remoto",
            "country_code": "ES",
            "lat": 42.57,
            "lon": -1.28,
            "location_source": "manual",
            "timezone": "Europe/Madrid",
        },
    ).json()
    payload = {
        "target_site_id": site["id"],
        "confirm_site_code": site["code"],
    }

    without_csrf = client.post(
        f"/devices/{device['id']}/location-commands",
        json=payload,
    )
    assert without_csrf.status_code == 403
    created = client.post(
        f"/devices/{device['id']}/location-commands",
        headers={"X-BirdMonitor-CSRF": "1"},
        json=payload,
    )
    assert created.status_code == 200

    client.cookies.clear()
    node_headers = {"Authorization": f"Bearer {NODE_TOKEN}"}
    delivered = client.get(
        "/node/location-command",
        headers=node_headers,
        params={"device_name": "birdmonitor"},
    )
    assert delivered.status_code == 200
    assert delivered.json()["public_id"] == created.json()["public_id"]

    premature_ack = client.post(
        "/node/location-command/ack",
        headers=node_headers,
        json={
            "command_public_id": created.json()["public_id"],
            "status": "applied",
            "deployment_started_at": "2026-08-23T15:00:00+00:00",
        },
    )
    assert premature_ack.status_code == 409

    forbidden_admin_action = client.post(
        f"/devices/{device['id']}/location-commands",
        headers=node_headers,
        json=payload,
    )
    assert forbidden_admin_action.status_code == 403


def test_modo_requerido_sin_secretos_falla_cerrado(client, monkeypatch):
    monkeypatch.setenv("BIRDMONITOR_SECURITY_MODE", "required")
    for variable in (
        "BIRDMONITOR_ADMIN_PASSWORD_HASH",
        "BIRDMONITOR_NODE_TOKEN_HASH",
        "BIRDMONITOR_SESSION_SECRET",
    ):
        monkeypatch.delenv(variable, raising=False)
    client.cookies.clear()

    response = client.get("/devices/")
    assert response.status_code == 503
    assert "configure_security.py" in response.json()["detail"]

    login = client.get("/login")
    assert login.status_code == 200
