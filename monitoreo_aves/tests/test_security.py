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
