from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path
import re
import secrets
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.security import hash_admin_password, hash_node_token


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
OUTPUT_FILE = PROJECT_ROOT / "backend" / "birdmonitor.env"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Configura el acceso privado de BirdMonitor.",
    )
    parser.add_argument(
        "--https",
        action="store_true",
        help="Marca la cookie como exclusiva para HTTPS.",
    )
    return parser.parse_args()


def ask_username() -> str:
    while True:
        username = input("Usuario administrador [admin]: ").strip() or "admin"
        if USERNAME_PATTERN.fullmatch(username):
            return username
        print("Usa entre 3 y 64 letras, numeros, punto, guion o guion bajo.")


def ask_password() -> str:
    while True:
        password = getpass("Contrasena administradora (minimo 12 caracteres): ")
        if len(password) < 12:
            print("La contrasena es demasiado corta.")
            continue
        if password != getpass("Repite la contrasena: "):
            print("Las contrasenas no coinciden.")
            continue
        return password


def main() -> int:
    args = parse_args()

    if OUTPUT_FILE.exists():
        answer = input(
            "Ya existe backend/birdmonitor.env. "
            "¿Rotar contrasena y token? [s/N]: "
        ).strip().casefold()
        if answer not in {"s", "si", "sí", "y", "yes"}:
            print("Configuracion conservada sin cambios.")
            return 0

    username = ask_username()
    password = ask_password()
    node_token = secrets.token_urlsafe(32)
    session_secret = secrets.token_urlsafe(48)

    content = "\n".join(
        [
            "# Generado por scripts/configure_security.py. No subir a Git.",
            "BIRDMONITOR_SECURITY_MODE=required",
            f"BIRDMONITOR_ADMIN_USERNAME={username}",
            f"BIRDMONITOR_ADMIN_PASSWORD_HASH={hash_admin_password(password)}",
            f"BIRDMONITOR_NODE_TOKEN_HASH={hash_node_token(node_token)}",
            f"BIRDMONITOR_SESSION_SECRET={session_secret}",
            "BIRDMONITOR_SESSION_HOURS=12",
            f"BIRDMONITOR_COOKIE_SECURE={1 if args.https else 0}",
            "BIRDMONITOR_NETWORK_MODE=unconfigured",
            "BIRDMONITOR_SERVER_HOST=",
            "",
        ]
    )
    OUTPUT_FILE.write_text(content, encoding="utf-8")
    try:
        OUTPUT_FILE.chmod(0o600)
    except OSError:
        pass

    print("\nSeguridad configurada.")
    print("Guarda este token ahora; el servidor conserva solamente su hash:")
    print(f"\nBIRDMONITOR_NODE_API_TOKEN={node_token}\n")
    print(
        "Anade esa linea a hardware/raspberry_pi/birdmonitor.env "
        "en la Raspberry y reinicia nodo y backend."
    )
    print(
        "Despues selecciona la red con "
        "scripts/configure_network_mode.py --mode local|tailscale."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
