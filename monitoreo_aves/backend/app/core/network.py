from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address, ip_network
import hmac
import os

from fastapi import Request
from fastapi.responses import JSONResponse


LOCAL_NETWORKS = (
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("169.254.0.0/16"),
    ip_network("fc00::/7"),
    ip_network("fe80::/10"),
)
TAILSCALE_NETWORKS = (
    ip_network("100.64.0.0/10"),
    ip_network("fd7a:115c:a1e0::/48"),
)


@dataclass(frozen=True)
class NetworkSettings:
    mode: str
    server_host: str

    @property
    def configured(self) -> bool:
        return not network_configuration_errors(self)


def get_network_settings() -> NetworkSettings:
    mode = os.getenv("BIRDMONITOR_NETWORK_MODE", "unconfigured")
    return NetworkSettings(
        mode=mode.strip().lower(),
        server_host=os.getenv(
            "BIRDMONITOR_SERVER_HOST",
            "",
        ).strip().strip("[]"),
    )


def _address_in_networks(value: str, networks) -> bool:
    try:
        address = ip_address(value)
    except ValueError:
        return False
    return any(address in network for network in networks)


def server_host_is_valid(mode: str, server_host: str) -> bool:
    host = server_host.strip().strip("[]")
    if mode == "local":
        return _address_in_networks(host, LOCAL_NETWORKS)
    if mode == "tailscale":
        return _address_in_networks(host, TAILSCALE_NETWORKS)
    return mode == "disabled" and not host


def network_configuration_errors(
    settings: NetworkSettings | None = None,
) -> list[str]:
    settings = settings or get_network_settings()
    if settings.mode == "disabled":
        return []
    if settings.mode not in {"local", "tailscale"}:
        return ["falta BIRDMONITOR_NETWORK_MODE"]
    if not server_host_is_valid(settings.mode, settings.server_host):
        return [
            "BIRDMONITOR_SERVER_HOST no pertenece al modo de red seleccionado"
        ]
    return []


def client_address_is_allowed(mode: str, client_host: str) -> bool:
    try:
        address = ip_address(client_host)
    except ValueError:
        return False
    if address.is_loopback:
        return True
    if mode == "local":
        return any(address in network for network in LOCAL_NETWORKS)
    if mode == "tailscale":
        return any(address in network for network in TAILSCALE_NETWORKS)
    return mode == "disabled"


def request_host_is_allowed(
    settings: NetworkSettings,
    request_host: str,
) -> bool:
    host = request_host.strip().strip("[]")
    if host in {"127.0.0.1", "::1", "localhost"}:
        return True
    return bool(
        settings.server_host
        and hmac.compare_digest(
            host.casefold(),
            settings.server_host.casefold(),
        )
    )


async def network_middleware(request: Request, call_next):
    settings = get_network_settings()
    if settings.mode == "disabled":
        return await call_next(request)

    client_host = request.client.host if request.client else ""
    client_is_loopback = client_address_is_allowed("local", client_host) and (
        client_host.startswith("127.") or client_host == "::1"
    )

    if not settings.configured:
        if request.url.path == "/health" and client_is_loopback:
            return await call_next(request)
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "El modo de red no esta configurado. Ejecuta "
                    "scripts/configure_network_mode.py."
                )
            },
        )

    if not client_address_is_allowed(settings.mode, client_host):
        return JSONResponse(
            status_code=403,
            content={"detail": "Origen de red no autorizado"},
        )

    if not request_host_is_allowed(
        settings,
        request.url.hostname or "",
    ):
        return JSONResponse(
            status_code=400,
            content={"detail": "Host no autorizado"},
        )

    return await call_next(request)