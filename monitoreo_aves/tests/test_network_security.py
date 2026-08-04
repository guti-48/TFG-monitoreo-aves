import asyncio

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.app.core.network import (
    NetworkSettings,
    client_address_is_allowed,
    network_configuration_errors,
    request_host_is_allowed,
    server_host_is_valid,
    network_middleware,
)


def test_modo_local_solo_admite_direcciones_locales():
    assert server_host_is_valid("local", "192.168.1.32")
    assert client_address_is_allowed("local", "10.20.30.40")
    assert client_address_is_allowed("local", "172.20.1.5")
    assert client_address_is_allowed("local", "127.0.0.1")
    assert not client_address_is_allowed("local", "100.74.108.117")
    assert not client_address_is_allowed("local", "8.8.8.8")


def test_modo_tailscale_solo_admite_el_rango_del_tailnet():
    assert server_host_is_valid("tailscale", "100.98.248.58")
    assert client_address_is_allowed("tailscale", "100.74.108.117")
    assert client_address_is_allowed(
        "tailscale",
        "fd7a:115c:a1e0::1234",
    )
    assert client_address_is_allowed("tailscale", "127.0.0.1")
    assert not client_address_is_allowed("tailscale", "192.168.1.32")
    assert not client_address_is_allowed("tailscale", "100.128.0.1")


def test_configuracion_invalida_falla_cerrada():
    missing_mode = NetworkSettings("unconfigured", "")
    wrong_host = NetworkSettings("tailscale", "192.168.1.32")

    assert network_configuration_errors(missing_mode)
    assert network_configuration_errors(wrong_host)


def test_host_http_debe_coincidir_con_el_servidor_configurado():
    settings = NetworkSettings("tailscale", "100.98.248.58")

    assert request_host_is_allowed(settings, "100.98.248.58")
    assert request_host_is_allowed(settings, "127.0.0.1")
    assert not request_host_is_allowed(settings, "192.168.1.32")


def _request(client_host: str, request_host: str) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/devices/",
            "raw_path": b"/devices/",
            "query_string": b"",
            "headers": [
                (b"host", f"{request_host}:8000".encode("ascii")),
            ],
            "client": (client_host, 50000),
            "server": (request_host, 8000),
        }
    )


def test_middleware_tailscale_rechaza_cliente_de_lan(monkeypatch):
    monkeypatch.setenv("BIRDMONITOR_NETWORK_MODE", "tailscale")
    monkeypatch.setenv("BIRDMONITOR_SERVER_HOST", "100.98.248.58")
    called = False

    async def next_handler(request):
        nonlocal called
        called = True
        return JSONResponse({"ok": True})

    response = asyncio.run(
        network_middleware(
            _request("192.168.1.50", "100.98.248.58"),
            next_handler,
        )
    )

    assert response.status_code == 403
    assert called is False


def test_middleware_tailscale_admite_cliente_del_tailnet(monkeypatch):
    monkeypatch.setenv("BIRDMONITOR_NETWORK_MODE", "tailscale")
    monkeypatch.setenv("BIRDMONITOR_SERVER_HOST", "100.98.248.58")

    async def next_handler(request):
        return JSONResponse({"ok": True})

    response = asyncio.run(
        network_middleware(
            _request("100.74.108.117", "100.98.248.58"),
            next_handler,
        )
    )

    assert response.status_code == 200
