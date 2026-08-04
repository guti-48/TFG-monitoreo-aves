from __future__ import annotations

import argparse
from ipaddress import ip_address
from pathlib import Path
import shutil
import socket
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.network import server_host_is_valid
from scripts.configure_stream_security import (
    parse_env,
    replace_env_values,
    write_env_atomic,
)


BACKEND_ENV_FILE = PROJECT_ROOT / "backend" / "birdmonitor.env"


def detect_local_ipv4() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # UDP connect no envia paquetes; permite consultar la interfaz de la
        # ruta local predeterminada sin depender de comandos por sistema.
        sock.connect(("192.0.2.1", 9))
        candidate = sock.getsockname()[0]
    finally:
        sock.close()
    return candidate if server_host_is_valid("local", candidate) else ""


def detect_tailscale_ipv4() -> str:
    executable = shutil.which("tailscale") or shutil.which("tailscale.exe")
    if not executable:
        return ""
    result = subprocess.run(
        [executable, "ip", "-4"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return ""
    candidate = result.stdout.strip().splitlines()[0]
    return candidate if server_host_is_valid("tailscale", candidate) else ""


def host_is_assigned_locally(server_host: str) -> bool:
    try:
        address = ip_address(server_host)
        family = socket.AF_INET if address.version == 4 else socket.AF_INET6
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.bind((str(address), 0))
        finally:
            sock.close()
        return True
    except (OSError, ValueError):
        return False


def resolve_server_host(mode: str, requested_host: str = "") -> str:
    host = requested_host.strip().strip("[]")
    if not host:
        host = (
            detect_tailscale_ipv4()
            if mode == "tailscale"
            else detect_local_ipv4()
        )
    if not server_host_is_valid(mode, host):
        expected = (
            "una IP Tailscale 100.64.0.0/10"
            if mode == "tailscale"
            else "una IP privada LAN (10/8, 172.16/12 o 192.168/16)"
        )
        raise ValueError(f"El modo {mode} requiere {expected}.")
    if not host_is_assigned_locally(host):
        raise ValueError(
            f"La IP {host} no esta asignada a este servidor."
        )
    return host


def network_env_updates(mode: str, server_host: str) -> dict[str, str]:
    dashboard_origin = f"http://{server_host}:8000"
    return {
        "BIRDMONITOR_NETWORK_MODE": mode,
        "BIRDMONITOR_SERVER_HOST": server_host,
        "BIRDMONITOR_BACKEND_HOST": "0.0.0.0",
        "BIRDMONITOR_BACKEND_PORT": "8000",
        "BIRDMONITOR_CORS_ORIGINS": (
            f"{dashboard_origin},"
            "http://127.0.0.1:8000,http://localhost:8000"
        ),
        "BIRDMONITOR_STREAM_RTSP_BASE_URL": (
            f"rtsp://{server_host}:8554"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Configura BirdMonitor para una LAN privada o para Tailscale."
        )
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("local", "tailscale"),
    )
    parser.add_argument(
        "--server-host",
        default="",
        help=(
            "IP de este servidor. Si se omite, se detecta la IP LAN o "
            "Tailscale segun el modo."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not BACKEND_ENV_FILE.is_file():
        raise SystemExit(
            "Primero ejecuta scripts/configure_security.py para crear "
            "backend/birdmonitor.env."
        )
    try:
        server_host = resolve_server_host(args.mode, args.server_host)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    original_lines = BACKEND_ENV_FILE.read_text(
        encoding="utf-8",
    ).splitlines()
    updates = network_env_updates(args.mode, server_host)
    write_env_atomic(
        BACKEND_ENV_FILE,
        replace_env_values(original_lines, updates),
    )

    print("\nModo de red configurado.")
    print(f"Modo: {args.mode}")
    print(f"Servidor: {server_host}")
    print(f"Dashboard: http://{server_host}:8000")
    print("\nEn la Raspberry configura:")
    print(f"BIRDMONITOR_NETWORK_MODE={args.mode}")
    print(f"BIRDMONITOR_SERVER_URL=http://{server_host}:8000")
    print("\nSiguiente paso en Windows (PowerShell administrador):")
    print(r".\scripts\windows\apply_network_mode.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
