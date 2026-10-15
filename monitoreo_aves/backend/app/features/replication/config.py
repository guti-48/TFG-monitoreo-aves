import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ...core.config import BACKEND_DIR

NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "100.64.0.0/10", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
))


class Peer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    url: str
    token: SecretStr = Field(min_length=32)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or parsed.username or parsed.password
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            raise ValueError("Usa un origen HTTP(S) privado sin credenciales ni rutas")
        try:
            address = ipaddress.ip_address(parsed.hostname or "")
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Usa la IPv4 privada del otro ordenador") from exc
        if not any(address in network for network in NETWORKS):
            raise ValueError("La replica debe estar en Tailscale, LAN privada o loopback")
        if port is not None and port == 0:
            raise ValueError("Puerto no valido")
        return value.rstrip("/")


def load_peers() -> list[Peer]:
    value = os.getenv("BIRDMONITOR_REPLICATION_PEERS_FILE", "").strip()
    if not value:
        return []
    path = Path(value)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    try:
        if path.stat().st_size > 65536:
            raise ValueError("Archivo demasiado grande")
        content = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(content, list) or len(content) > 8:
            raise ValueError("Se esperaba una lista de hasta ocho pares")
        peers = [Peer.model_validate(item) for item in content]
        if len({p.url for p in peers}) != len(peers) or len({p.name for p in peers}) != len(peers):
            raise ValueError("Pares duplicados")
    except (OSError, ValueError, TypeError):
        raise ValueError("Configuracion de replicas invalida: revisa archivo, IP privada y credenciales") from None
    return peers


def interval_seconds() -> int:
    return max(30, int(os.getenv("BIRDMONITOR_REPLICATION_INTERVAL_SECONDS", "60")))