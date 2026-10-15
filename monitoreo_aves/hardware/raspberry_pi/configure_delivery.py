import argparse
from getpass import getpass
import json
import os
from pathlib import Path
import tempfile

from node_delivery import load_targets


def atomic_write(path, content, *, owner=None):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        if owner is not None and hasattr(os, "chown") and os.geteuid() == 0:
            os.chown(temporary, *owner)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def configure(env_path, targets_path, name, url, token):
    env_path, targets_path = Path(env_path).resolve(), Path(targets_path).resolve()
    lines = env_path.read_text(encoding="utf-8").splitlines()
    values = {}
    for line in lines:
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip().removeprefix("export ")] = value.strip().strip("\"'")
    if targets_path.exists():
        targets = [{"name": t.name, "url": t.url, "token": t.token} for t in load_targets(targets_path)]
    else:
        targets = [{"name": "principal", "url": values["BIRDMONITOR_SERVER_URL"],
                    "token": values["BIRDMONITOR_NODE_API_TOKEN"]}]
    target = {"name": name, "url": url.rstrip("/"), "token": token}
    targets = [t for t in targets if t["url"].rstrip("/") != target["url"]]
    targets.append(target)
    content = json.dumps(targets, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=targets_path.parent) as check:
        check.write(content)
        check.flush()
        load_targets(check.name)
    owner_stat = targets_path.stat() if targets_path.exists() else targets_path.parent.stat()
    atomic_write(targets_path, content, owner=(owner_stat.st_uid, owner_stat.st_gid))
    key = "BIRDMONITOR_INGEST_TARGETS_FILE"
    lines = [line for line in lines if line.split("=", 1)[0].strip().removeprefix("export ") != key]
    lines.append(f"{key}={json.dumps(str(targets_path))}")
    env_stat = env_path.stat()
    atomic_write(env_path, "\n".join(lines) + "\n", owner=(env_stat.st_uid, env_stat.st_gid))


def main():
    parser = argparse.ArgumentParser(description="Anade un servidor de ingesta conservando el servidor actual")
    parser.add_argument("--env-file", type=Path, default=Path("/etc/birdmonitor/birdmonitor.env"))
    parser.add_argument("--targets-file", type=Path, default=Path(__file__).resolve().parent / "ingest-targets.secret")
    parser.add_argument("--name", required=True)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    token = getpass("Token de nodo del servidor que vas a anadir: ").strip()
    try:
        configure(args.env_file, args.targets_file, args.name, args.url, token)
    except (OSError, ValueError, KeyError):
        raise SystemExit("No se pudo configurar: revisa el entorno, la IP privada, el token y los permisos")
    print("Destinos guardados. Reinicia birdmonitor.service para aplicarlos.")


if __name__ == "__main__":
    main()