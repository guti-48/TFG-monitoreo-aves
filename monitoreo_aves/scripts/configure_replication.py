import argparse
from getpass import getpass
import json
import os
from pathlib import Path
import secrets
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from backend.app.core.security import hash_node_token
from backend.app.features.replication.config import Peer
from scripts.configure_stream_security import parse_env, replace_env_values, write_env_atomic


def configure(backend, peer_name=None, peer_url=None, peer_token=None, *, enable_ingest=False):
    env = backend / "birdmonitor.env"
    if not env.is_file():
        raise ValueError("Configura primero la seguridad y la red del servidor")
    lines = env.read_text(encoding="utf-8").splitlines()
    values = parse_env(lines)
    updates = {}
    if peer_url:
        peer = Peer(name=peer_name, url=peer_url, token=peer_token)
        peers_path = backend / "replication-peers.secret"
        peers = json.loads(peers_path.read_text()) if peers_path.exists() else []
        for entry in peers:
            Peer.model_validate(entry)
            if entry["name"] == peer.name or entry["url"] == peer.url:
                raise ValueError("La replica ya existe; revisa el archivo de pares sin duplicarla")
        if len(peers) >= 8:
            raise ValueError("Se admiten hasta ocho replicas")
        peers.append({"name": peer.name, "url": peer.url, "token": peer.token.get_secret_value()})
    if not values.get("BIRDMONITOR_REPLICATION_TOKEN_HASH"):
        access = backend / "replication-access.secret"
        if access.exists():
            token = access.read_text().strip()
            if len(token) < 32:
                raise ValueError("Token local incompleto")
        else:
            token = secrets.token_urlsafe(32)
            with access.open("x", encoding="utf-8") as output:
                output.write(token + "\n")
        access.chmod(0o600)
        updates["BIRDMONITOR_REPLICATION_TOKEN_HASH"] = hash_node_token(token)
    if enable_ingest and not values.get("BIRDMONITOR_INGEST_TOKEN_HASH"):
        access = backend / "ingest-access.secret"
        if access.exists():
            token = access.read_text().strip()
            if len(token) < 32:
                raise ValueError("Token local incompleto")
        else:
            token = secrets.token_urlsafe(32)
            with access.open("x", encoding="utf-8") as output:
                output.write(token + "\n")
        access.chmod(0o600)
        updates["BIRDMONITOR_INGEST_TOKEN_HASH"] = hash_node_token(token)
    if peer_url:
        temporary = peers_path.with_suffix(".secret.tmp")
        temporary.write_text(json.dumps(peers, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(peers_path)
        updates["BIRDMONITOR_REPLICATION_PEERS_FILE"] = peers_path.name
        updates.setdefault("BIRDMONITOR_REPLICATION_INTERVAL_SECONDS", values.get("BIRDMONITOR_REPLICATION_INTERVAL_SECONDS", "60"))
    if updates:
        write_env_atomic(env, replace_env_values(lines, updates))


def main():
    parser = argparse.ArgumentParser(description="Configura sincronizacion entre servidores BirdMonitor")
    parser.add_argument("--peer-name")
    parser.add_argument("--peer-url")
    parser.add_argument("--enable-node-ingest", action="store_true")
    args = parser.parse_args()
    if bool(args.peer_name) != bool(args.peer_url):
        parser.error("--peer-name y --peer-url deben indicarse juntos")
    os.umask(0o077)
    token = getpass("Token de replicacion del otro servidor: ") if args.peer_url else None
    try:
        configure(PROJECT / "backend", args.peer_name, args.peer_url, token, enable_ingest=args.enable_node_ingest)
    except (OSError, ValueError):
        raise SystemExit("No se pudo configurar la replica. Revisa el entorno, la IP privada, el token y los pares existentes.")
    print("Token de lectura de este servidor: backend/replication-access.secret")
    if args.enable_node_ingest:
        print("Token adicional de ingesta del nodo: backend/ingest-access.secret")
    print("Configuracion guardada. Reinicia el backend para aplicarla.")


if __name__ == "__main__":
    main()
