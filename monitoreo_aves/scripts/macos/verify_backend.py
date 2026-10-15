"""Comprueba el servicio HTTP real, incluidas red y credenciales."""

import argparse
import json
from urllib.request import urlopen


def validate_health(health: dict, network_mode: str) -> None:
    expected = {
        "status": "ok",
        "network_mode": network_mode,
        "network_configured": True,
        "security": "required",
        "security_configured": True,
        "stream_security": "required",
        "stream_security_configured": True,
    }
    invalid = [key for key, value in expected.items() if health.get(key) != value]
    if invalid:
        raise ValueError("Configuracion incompleta: " + ", ".join(invalid))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--network-mode", choices=("local", "tailscale"), required=True)
    args = parser.parse_args()
    try:
        with urlopen(f"http://127.0.0.1:{args.port}/health", timeout=5) as response:
            validate_health(json.load(response), args.network_mode)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Backend no preparado: {exc}") from exc
    print("Backend, red y credenciales verificados por HTTP.")


if __name__ == "__main__":
    main()
