from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.features.streaming.security import hash_stream_password


BACKEND_ENV_FILE = PROJECT_ROOT / "backend" / "birdmonitor.env"

def parse_env(lines: list[str]) -> dict[str, str]:
    values = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def replace_env_values(
    lines: list[str],
    updates: dict[str, str],
) -> list[str]:
    output = []
    replaced = set()

    for raw_line in lines:
        stripped = raw_line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                output.append(f"{key}={updates[key]}")
                replaced.add(key)
                continue
        output.append(raw_line)

    missing = [key for key in updates if key not in replaced]
    if missing:
        if output and output[-1].strip():
            output.append("")
        output.append("# Seguridad del streaming MediaMTX")
        output.extend(f"{key}={updates[key]}" for key in missing)

    return output


def write_env_atomic(path: Path, lines: list[str]) -> None:
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, path)
    if os.name != "nt":
        path.chmod(0o600)


def stream_security_is_configured(values: dict[str, str]) -> bool:
    return (
        values.get("BIRDMONITOR_STREAM_SECURITY_MODE") == "required"
        and bool(values.get("BIRDMONITOR_STREAM_PUBLISH_USER"))
        and values.get(
            "BIRDMONITOR_STREAM_PUBLISH_PASSWORD_HASH",
            "",
        ).startswith("sha256$")
        and len(values.get("BIRDMONITOR_STREAM_READER_PASSWORD", "")) >= 24
        and len(values.get("BIRDMONITOR_STREAM_PROXY_PASSWORD", "")) >= 24
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Configura credenciales separadas para MediaMTX.",
    )
    rotation_group = parser.add_mutually_exclusive_group()
    rotation_group.add_argument(
        "--rotate",
        action="store_true",
        help="Rota todas las credenciales de streaming existentes.",
    )
    rotation_group.add_argument(
        "--rotate-reader",
        action="store_true",
        help=(
            "Rota solo la credencial de lectura RTSP sin cambiar la "
            "publicacion de la Raspberry ni el proxy HLS."
        ),
    )
    parser.add_argument(
        "--server-host",
        default="",
        help=(
            "IP LAN o Tailscale del servidor. Normalmente se toma del "
            "modo configurado."
        ),
    )
    args = parser.parse_args()

    if not BACKEND_ENV_FILE.is_file():
        raise SystemExit(
            "Primero ejecuta scripts/configure_security.py para crear "
            "backend/birdmonitor.env."
        )

    original_lines = BACKEND_ENV_FILE.read_text(
        encoding="utf-8",
    ).splitlines()
    current_values = parse_env(original_lines)
    network_mode = current_values.get("BIRDMONITOR_NETWORK_MODE", "")
    configured_host = current_values.get("BIRDMONITOR_SERVER_HOST", "")
    if network_mode not in {"local", "tailscale"} or not configured_host:
        raise SystemExit(
            "Primero ejecuta scripts/configure_network_mode.py "
            "--mode local|tailscale."
        )
    requested_host = args.server_host.strip()
    if requested_host and requested_host != configured_host:
        raise SystemExit(
            "--server-host no coincide con BIRDMONITOR_SERVER_HOST. "
            "Vuelve a configurar el modo de red."
        )

    security_configured = stream_security_is_configured(current_values)
    if security_configured and not args.rotate and not args.rotate_reader:
        print(
            "La seguridad de streaming ya esta configurada. "
            "Usa --rotate solo si quieres invalidar las credenciales actuales."
        )
        return

    if args.rotate_reader:
        if not security_configured:
            raise SystemExit(
                "No se puede rotar solo el lector porque la seguridad de "
                "streaming aun no esta configurada completamente."
            )

        reader_password = secrets.token_urlsafe(32)
        updates = {
            "BIRDMONITOR_STREAM_READER_USER": (
                current_values.get("BIRDMONITOR_STREAM_READER_USER")
                or "birdmonitor-viewer"
            ),
            "BIRDMONITOR_STREAM_READER_PASSWORD": reader_password,
        }
        write_env_atomic(
            BACKEND_ENV_FILE,
            replace_env_values(original_lines, updates),
        )
        print(
            "Credencial de lectura RTSP rotada. La nueva clave permanece "
            "solo en backend/birdmonitor.env y no se muestra en consola."
        )
        print(
            "Reinicia el backend para invalidar la clave anterior. "
            "La Raspberry no necesita cambios."
        )
        return

    publish_user = "birdmonitor-publisher"
    reader_user = "birdmonitor-viewer"
    proxy_user = "birdmonitor-backend"
    publish_password = secrets.token_urlsafe(32)
    reader_password = secrets.token_urlsafe(32)
    proxy_password = secrets.token_urlsafe(32)

    updates = {
        "BIRDMONITOR_STREAM_SECURITY_MODE": "required",
        "BIRDMONITOR_STREAM_PUBLISH_USER": publish_user,
        "BIRDMONITOR_STREAM_PUBLISH_PASSWORD_HASH": (
            hash_stream_password(publish_password)
        ),
        "BIRDMONITOR_STREAM_READER_USER": reader_user,
        "BIRDMONITOR_STREAM_READER_PASSWORD": reader_password,
        "BIRDMONITOR_STREAM_PROXY_USER": proxy_user,
        "BIRDMONITOR_STREAM_PROXY_PASSWORD": proxy_password,
        "BIRDMONITOR_MEDIAMTX_HLS_INTERNAL_URL": (
            "http://127.0.0.1:8888"
        ),
    }
    write_env_atomic(
        BACKEND_ENV_FILE,
        replace_env_values(original_lines, updates),
    )

    server_host = configured_host
    stream_url = (
        f"rtsp://{publish_user}:{publish_password}"
        f"@{server_host}:8554/birdmonitor-audio"
    )

    print("\nSeguridad de streaming configurada.")
    print(
        "Guarda esta contrasena para introducirla una sola vez en el "
        "instalador de la Raspberry:"
    )
    print(f"\n{publish_password}\n")
    print("URL completa de referencia:")
    print("La contrasena de publicacion no se almacena en texto plano en el servidor.")
    print(f"\n{stream_url}\n")
    print(
        "Despues configura la Raspberry con "
        "configure_stream_publisher.py --network-mode "
        f"{network_mode} --server-host {server_host}."
    )
    print(
        "Finalmente ejecuta scripts/windows/apply_network_mode.ps1 "
        "como administrador."
    )


if __name__ == "__main__":
    main()