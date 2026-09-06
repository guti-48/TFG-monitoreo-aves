#!/usr/bin/env python3
"""Configura birdstream.service para publicar en MediaMTX con credenciales."""

from __future__ import annotations

import argparse
from getpass import getpass
from ipaddress import ip_address, ip_network
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from urllib.parse import quote


DEFAULT_SERVICE = "birdstream.service"
DEFAULT_PUBLISH_USER = "birdmonitor-publisher"
DEFAULT_STREAM_PATH = "birdmonitor-audio"
PUBLISH_ENV_FILE = Path("/etc/birdmonitor/stream-publisher.env")
BACKUP_DIR = Path("/etc/birdmonitor/backups")
SERVICE_NAME_PATTERN = re.compile(r"[A-Za-z0-9_.@-]+\.service")
RTSP_URL_PATTERN = re.compile(r"rtsp://[^\s\"']+")
PUBLISH_URL_VARIABLE = "${BIRDMONITOR_STREAM_PUBLISH_URL}"
STABILITY_WAIT_SECONDS = 8
LOCAL_NETWORKS = (
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
)
TAILSCALE_NETWORK = ip_network("100.64.0.0/10")


def build_publish_url(
    server_host: str,
    publish_user: str,
    publish_password: str,
    stream_path: str,
) -> str:
    host = server_host.strip()
    user = publish_user.strip()
    path = stream_path.strip().strip("/")
    if not host or any(char.isspace() for char in host):
        raise ValueError("La IP o nombre del servidor no es valido")
    if not user or any(char.isspace() for char in user):
        raise ValueError("El usuario de publicacion no es valido")
    if len(publish_password) < 24:
        raise ValueError("La contrasena de publicacion no es valida")
    if not path or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", path):
        raise ValueError("La ruta del stream no es valida")

    return (
        f"rtsp://{quote(user, safe='')}:{quote(publish_password, safe='')}"
        f"@{host}:8554/{path}"
    )


def server_host_matches_mode(network_mode: str, server_host: str) -> bool:
    try:
        address = ip_address(server_host.strip())
    except ValueError:
        return False
    if network_mode == "local":
        return any(address in network for network in LOCAL_NETWORKS)
    if network_mode == "tailscale":
        return address in TAILSCALE_NETWORK
    return False


def secure_service_content(content: str) -> str:
    if "[Service]" not in content:
        raise ValueError("La unidad no contiene una seccion [Service]")

    updated = content
    urls = RTSP_URL_PATTERN.findall(updated)
    if PUBLISH_URL_VARIABLE not in updated:
        if len(urls) != 1:
            raise ValueError(
                "Se esperaba una unica URL rtsp:// en ExecStart; "
                f"se encontraron {len(urls)}"
            )
    for url in urls:
        updated = updated.replace(url, PUBLISH_URL_VARIABLE)

    environment_line = f"EnvironmentFile={PUBLISH_ENV_FILE.as_posix()}"
    if environment_line not in updated:
        updated = updated.replace(
            "[Service]",
            f"[Service]\n{environment_line}",
            1,
        )
    return updated


def secure_service_contents(contents: list[str]) -> list[str]:
    """Actualiza la unidad principal y todos sus drop-ins de systemd."""
    if not contents or "[Service]" not in contents[0]:
        raise ValueError("La unidad no contiene una seccion [Service]")

    updated_contents = []
    replacements = 0
    for content in contents:
        updated = content
        urls = RTSP_URL_PATTERN.findall(updated)
        for url in urls:
            updated = updated.replace(url, PUBLISH_URL_VARIABLE)
            replacements += 1
        updated_contents.append(updated)

    if (
        replacements == 0
        and not any(PUBLISH_URL_VARIABLE in item for item in updated_contents)
    ):
        raise ValueError(
            "No se encontro una URL RTSP ni la variable protegida en la "
            "unidad efectiva"
        )

    environment_line = f"EnvironmentFile={PUBLISH_ENV_FILE.as_posix()}"
    if environment_line not in updated_contents[0]:
        updated_contents[0] = updated_contents[0].replace(
            "[Service]",
            f"[Service]\n{environment_line}",
            1,
        )
    return updated_contents


def run_systemctl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/usr/bin/systemctl", *arguments],
        check=check,
        capture_output=True,
        text=True,
    )


def service_restart_count(service_name: str) -> int:
    result = run_systemctl(
        "show",
        "--property=NRestarts",
        "--value",
        service_name,
    )
    try:
        return int(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(
            "systemd no devolvio un contador de reinicios valido"
        ) from exc


def verify_service_stability(
    service_name: str,
    wait_seconds: int = STABILITY_WAIT_SECONDS,
) -> None:
    initial_restarts = service_restart_count(service_name)
    time.sleep(wait_seconds)
    active = run_systemctl(
        "is-active",
        "--quiet",
        service_name,
        check=False,
    )
    final_restarts = service_restart_count(service_name)

    if active.returncode != 0:
        raise RuntimeError(
            f"{service_name} dejo de estar activo durante la comprobacion"
        )
    if final_restarts > initial_restarts:
        raise RuntimeError(
            f"{service_name} se reinicio {final_restarts - initial_restarts} "
            "vez/veces; revisa la autenticacion RTSP y el registro del servicio"
        )


def resolve_service_path(service_name: str) -> Path:
    result = run_systemctl(
        "show",
        "--property=FragmentPath",
        "--value",
        service_name,
    )
    path = Path(result.stdout.strip()).resolve()
    if not path.is_file() or path.suffix != ".service":
        raise RuntimeError(
            f"No se ha encontrado la unidad real de {service_name}"
        )
    return path


def resolve_service_paths(service_name: str) -> list[Path]:
    """Devuelve el fragmento principal y los drop-ins en orden efectivo."""
    primary_path = resolve_service_path(service_name)
    result = run_systemctl(
        "show",
        "--property=DropInPaths",
        "--value",
        service_name,
    )
    paths = [primary_path]
    for raw_path in shlex.split(result.stdout.strip()):
        path = Path(raw_path).resolve()
        if not path.is_file() or path.suffix != ".conf":
            raise RuntimeError(
                f"Drop-in de systemd no valido para {service_name}: {raw_path}"
            )
        if path not in paths:
            paths.append(path)
    return paths


def atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=str(path.parent),
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Protege la publicacion RTSP de birdstream.service sin guardar "
            "la contrasena en el repositorio ni en el historial del shell."
        )
    )
    parser.add_argument("--server-host", required=True)
    parser.add_argument(
        "--network-mode",
        required=True,
        choices=("local", "tailscale"),
    )
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--publish-user", default=DEFAULT_PUBLISH_USER)
    parser.add_argument("--stream-path", default=DEFAULT_STREAM_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Ejecuta este instalador con sudo.")
    if not SERVICE_NAME_PATTERN.fullmatch(args.service):
        raise SystemExit("Nombre de servicio no valido.")
    if not server_host_matches_mode(args.network_mode, args.server_host):
        raise SystemExit(
            "La IP del servidor no pertenece al modo de red seleccionado."
        )
    if args.network_mode == "tailscale":
        tailscale = run_systemctl(
            "is-active",
            "--quiet",
            "tailscaled.service",
            check=False,
        )
        if tailscale.returncode != 0:
            raise SystemExit(
                "El modo Tailscale requiere tailscaled.service activo."
            )

    password = getpass("Contrasena de publicacion mostrada por el servidor: ")
    try:
        publish_url = build_publish_url(
            args.server_host,
            args.publish_user,
            password,
            args.stream_path,
        )
        service_paths = resolve_service_paths(args.service)
        original_services = {
            path: path.read_text(encoding="utf-8")
            for path in service_paths
        }
        updated_contents = secure_service_contents(
            list(original_services.values())
        )
        updated_services = dict(zip(service_paths, updated_contents))
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    original_env = (
        PUBLISH_ENV_FILE.read_bytes()
        if PUBLISH_ENV_FILE.is_file()
        else None
    )
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(BACKUP_DIR, 0o700)
    backup_paths = []
    for index, service_path in enumerate(service_paths):
        backup_path = BACKUP_DIR / (
            f"{args.service}.{index}-{service_path.name}.before-stream-auth"
        )
        if not backup_path.exists():
            shutil.copy2(service_path, backup_path)
            os.chmod(backup_path, 0o600)
        backup_paths.append(backup_path)

    try:
        atomic_write(
            PUBLISH_ENV_FILE,
            f"BIRDMONITOR_STREAM_PUBLISH_URL={publish_url}\n",
            0o600,
        )
        for service_path, updated_service in updated_services.items():
            original_service = original_services[service_path]
            if updated_service != original_service:
                atomic_write(service_path, updated_service, 0o644)

        run_systemctl("daemon-reload")
        run_systemctl("enable", args.service)
        run_systemctl("restart", args.service)
        verify_service_stability(args.service)
    except Exception as exc:
        for service_path, original_service in original_services.items():
            atomic_write(service_path, original_service, 0o644)
        if original_env is None:
            PUBLISH_ENV_FILE.unlink(missing_ok=True)
        else:
            atomic_write(
                PUBLISH_ENV_FILE,
                original_env.decode("utf-8"),
                0o600,
            )
        run_systemctl("daemon-reload", check=False)
        run_systemctl("restart", args.service, check=False)
        raise SystemExit(
            f"No se pudo aplicar la configuracion; se restauro la unidad: {exc}"
        ) from exc

    print(
        f"{args.service} permanece activo sin reinicios y usa "
        "autenticacion RTSP."
    )
    print(f"Credencial local protegida en {PUBLISH_ENV_FILE} (permisos 600).")
    for backup_path in backup_paths:
        print(f"Copia de seguridad: {backup_path}")


if __name__ == "__main__":
    main()
