import httpx

from backend.app.core.security import hash_admin_password, hash_node_token
from backend.app.features.streaming.security import hash_stream_password


PUBLISH_USER = "birdmonitor-publisher"
PUBLISH_PASSWORD = "publisher-password-test-muy-larga"
READER_USER = "birdmonitor-viewer"
READER_PASSWORD = "reader-password-test-muy-larga"
PROXY_USER = "birdmonitor-backend"
PROXY_PASSWORD = "proxy-password-test-muy-larga"
HLS_SESSION = "6f4e6eba-b5a3-4f88-8efd-c9685cc2d814"
ADMIN_PASSWORD = "admin-stream-test-seguro"
NODE_TOKEN = "node-stream-token-test-muy-largo"


def configure_stream_security(monkeypatch):
    monkeypatch.setenv("BIRDMONITOR_STREAM_SECURITY_MODE", "required")
    monkeypatch.setenv(
        "BIRDMONITOR_STREAM_PUBLISH_USER",
        PUBLISH_USER,
    )
    monkeypatch.setenv(
        "BIRDMONITOR_STREAM_PUBLISH_PASSWORD_HASH",
        hash_stream_password(PUBLISH_PASSWORD),
    )
    monkeypatch.setenv(
        "BIRDMONITOR_STREAM_READER_USER",
        READER_USER,
    )
    monkeypatch.setenv(
        "BIRDMONITOR_STREAM_READER_PASSWORD",
        READER_PASSWORD,
    )
    monkeypatch.setenv(
        "BIRDMONITOR_STREAM_PROXY_USER",
        PROXY_USER,
    )
    monkeypatch.setenv(
        "BIRDMONITOR_STREAM_PROXY_PASSWORD",
        PROXY_PASSWORD,
    )
    monkeypatch.setenv(
        "BIRDMONITOR_MEDIAMTX_HLS_INTERNAL_URL",
        "http://127.0.0.1:8888",
    )


def auth_payload(user, password, action, protocol):
    return {
        "user": user,
        "password": password,
        "action": action,
        "path": "birdmonitor-audio",
        "protocol": protocol,
    }


def test_auth_mediamtx_solo_admite_llamadas_loopback(
    client,
    monkeypatch,
):
    configure_stream_security(monkeypatch)

    response = client.post(
        "/internal/mediamtx/auth",
        json=auth_payload(
            PROXY_USER,
            PROXY_PASSWORD,
            "read",
            "hls",
        ),
    )

    assert response.status_code == 403


def test_auth_mediamtx_separa_publicacion_lectura_y_proxy(
    client,
    monkeypatch,
    caplog,
):
    from backend.app.features.streaming import security as stream_security

    configure_stream_security(monkeypatch)
    monkeypatch.setattr(
        stream_security,
        "_request_is_loopback",
        lambda request: True,
    )

    publisher = client.post(
        "/internal/mediamtx/auth",
        json=auth_payload(
            PUBLISH_USER,
            PUBLISH_PASSWORD,
            "publish",
            "rtsp",
        ),
    )
    reader = client.post(
        "/internal/mediamtx/auth",
        json=auth_payload(
            READER_USER,
            READER_PASSWORD,
            "read",
            "rtsp",
        ),
    )
    proxy = client.post(
        "/internal/mediamtx/auth",
        json=auth_payload(
            PROXY_USER,
            PROXY_PASSWORD,
            "read",
            "hls",
        ),
    )
    reader_cannot_publish = client.post(
        "/internal/mediamtx/auth",
        json=auth_payload(
            READER_USER,
            READER_PASSWORD,
            "publish",
            "rtsp",
        ),
    )

    assert publisher.status_code == 204
    assert reader.status_code == 204
    assert proxy.status_code == 204
    assert reader_cannot_publish.status_code == 401
    assert "usuario_lector_ok=True" in caplog.text
    assert "clave_lector_ok=True" in caplog.text
    assert READER_PASSWORD not in caplog.text


def test_proxy_hls_reenvia_con_credencial_interna(
    client,
    monkeypatch,
):
    from backend.app.features.streaming import security as stream_security

    configure_stream_security(monkeypatch)
    captured = {}

    class FakeUpstreamResponse:
        status_code = 200
        headers = {
            "content-type": "application/vnd.apple.mpegurl",
            "cache-control": "max-age=30",
        }

        async def aiter_raw(self):
            yield b"#EXTM3U\nsegment.mp4\n"

        async def aclose(self):
            return None

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["client_kwargs"] = kwargs

        def build_request(self, method, url, headers, params):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["params"] = params
            return object()

        async def send(self, request, auth, stream):
            captured["auth"] = auth
            captured["stream"] = stream
            return FakeUpstreamResponse()

        async def aclose(self):
            return None

    monkeypatch.setattr(
        stream_security.httpx,
        "AsyncClient",
        FakeAsyncClient,
    )

    response = client.get(
        "/stream/hls/birdmonitor-audio/index.m3u8",
        params={"session": HLS_SESSION},
    )

    assert response.status_code == 200
    assert response.text == "#EXTM3U\nsegment.mp4\n"
    assert response.headers["cache-control"] == "no-store"
    assert captured["url"] == (
        "http://127.0.0.1:8888/"
        "birdmonitor-audio/index.m3u8"
    )
    assert isinstance(captured["auth"], httpx.BasicAuth)
    assert captured["stream"] is True
    assert captured["params"] == {"session": HLS_SESSION}
    assert captured["client_kwargs"]["follow_redirects"] is True
    assert captured["client_kwargs"]["max_redirects"] == 3


def test_proxy_hls_rechaza_identificador_de_sesion_no_valido(
    client,
    monkeypatch,
):
    configure_stream_security(monkeypatch)

    response = client.get(
        "/stream/hls/birdmonitor-audio/audio1_stream.m3u8",
        params={"session": "../../otra-ruta"},
    )

    assert response.status_code == 400


def test_url_rtsp_con_secreto_solo_se_entrega_al_administrador_y_no_se_persiste(
    client,
    monkeypatch,
    tmp_path,
):
    from backend.app.features.streaming import routes as streaming

    configure_stream_security(monkeypatch)
    monkeypatch.setenv("BIRDMONITOR_SECURITY_MODE", "required")
    monkeypatch.setenv("BIRDMONITOR_ADMIN_USERNAME", "admin-stream")
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
        "stream-session-secret-test-con-32-caracteres",
    )
    monkeypatch.setenv("BIRDMONITOR_COOKIE_SECURE", "0")
    state_file = tmp_path / "stream_control.json"
    monkeypatch.setattr(streaming, "STREAM_CONTROL_FILE", state_file)
    client.cookies.clear()

    login = client.post(
        "/auth/login",
        data={
            "username": "admin-stream",
            "password": ADMIN_PASSWORD,
        },
        follow_redirects=False,
    )
    assert login.status_code == 303

    admin_response = client.post(
        "/stream/control",
        json={
            "node_name": "birdmonitor",
            "stream_enabled": True,
        },
        headers={"X-BirdMonitor-CSRF": "1"},
    )
    assert admin_response.status_code == 200
    assert (
        f"{READER_USER}:{READER_PASSWORD}@"
        in admin_response.json()["rtsp_url"]
    )

    client.cookies.clear()
    node_response = client.get(
        "/stream/control",
        params={"node_name": "birdmonitor"},
        headers={"Authorization": f"Bearer {NODE_TOKEN}"},
    )
    assert node_response.status_code == 200
    assert "@" not in node_response.json()["rtsp_url"]
    assert READER_PASSWORD not in state_file.read_text(encoding="utf-8")
