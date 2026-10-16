#!/usr/bin/env python3
"""Configura un sitio/despliegue sin alterar secretos ni otros ajustes."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4


SITE_CODE_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
MANAGED_KEYS = (
    "BIRDMONITOR_SITE_CODE",
    "BIRDMONITOR_SITE_NAME",
    "BIRDMONITOR_SITE_MUNICIPALITY",
    "BIRDMONITOR_SITE_REGION",
    "BIRDMONITOR_SITE_COUNTRY_CODE",
    "BIRDMONITOR_SITE_TIMEZONE",
    "BIRDMONITOR_SITE_LOCATION_SOURCE",
    "BIRDMONITOR_SITE_LOCATION_ACCURACY_M",
    "BIRDMONITOR_DEPLOYMENT_ID",
    "BIRDMONITOR_DEPLOYMENT_STARTED_AT",
    "BIRDMONITOR_DEPLOYMENT_NOTES",
    "BIRDMONITOR_NODE_LOCATION",
    "BIRDMONITOR_NODE_LAT",
    "BIRDMONITOR_NODE_LON",
    "BIRDMONITOR_AUTO_GEOLOCATION",
    "BIRDMONITOR_LEGACY_SITE_CODE",
    "BIRDMONITOR_LEGACY_DEPLOYMENT_ID",
)


def read_env(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    values = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return lines, values


def _safe_env_value(value) -> str:
    text = "" if value is None else str(value).strip()
    if any(character in text for character in ("\n", "\r", "\x00")):
        raise ValueError("Los valores de configuracion no admiten saltos de linea")
    return text


def _valid_uuid(value: str, label: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} debe ser un UUID valido") from exc


def _valid_started_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("started-at debe usar ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("started-at debe incluir zona horaria")
    return parsed.isoformat()


def build_site_values(args, existing: dict[str, str]) -> tuple[dict[str, str], bool]:
    code = args.site_code.strip().lower()
    if not SITE_CODE_PATTERN.fullmatch(code):
        raise ValueError("site-code solo admite minusculas, numeros y guiones")
    country_code = args.country_code.strip().upper()
    if len(country_code) != 2 or not country_code.isalpha():
        raise ValueError("country-code debe tener dos letras")
    if (args.lat is None) != (args.lon is None):
        raise ValueError("lat y lon deben proporcionarse juntas")
    if args.accuracy_m is not None and args.lat is None:
        raise ValueError("accuracy-m requiere lat y lon")
    if args.accuracy_m is not None and args.accuracy_m < 0:
        raise ValueError("accuracy-m no puede ser negativa")

    same_site = existing.get("BIRDMONITOR_SITE_CODE") == code
    existing_id = existing.get("BIRDMONITOR_DEPLOYMENT_ID", "")
    reuse = same_site and bool(existing_id) and not args.new_deployment

    if args.deployment_id:
        deployment_id = _valid_uuid(args.deployment_id, "deployment-id")
        reuse = deployment_id == existing_id
    elif reuse:
        deployment_id = _valid_uuid(existing_id, "BIRDMONITOR_DEPLOYMENT_ID")
    else:
        deployment_id = str(uuid4())

    if args.started_at:
        started_at = _valid_started_at(args.started_at)
    elif reuse and existing.get("BIRDMONITOR_DEPLOYMENT_STARTED_AT"):
        started_at = _valid_started_at(
            existing["BIRDMONITOR_DEPLOYMENT_STARTED_AT"]
        )
    else:
        started_at = datetime.now(timezone.utc).isoformat()

    values = {
        "BIRDMONITOR_SITE_CODE": code,
        "BIRDMONITOR_SITE_NAME": args.site_name,
        "BIRDMONITOR_SITE_MUNICIPALITY": args.municipality or "",
        "BIRDMONITOR_SITE_REGION": args.region or "",
        "BIRDMONITOR_SITE_COUNTRY_CODE": country_code,
        "BIRDMONITOR_SITE_TIMEZONE": args.timezone,
        "BIRDMONITOR_SITE_LOCATION_SOURCE": args.location_source,
        "BIRDMONITOR_SITE_LOCATION_ACCURACY_M": (
            args.accuracy_m if args.accuracy_m is not None else ""
        ),
        "BIRDMONITOR_DEPLOYMENT_ID": deployment_id,
        "BIRDMONITOR_DEPLOYMENT_STARTED_AT": started_at,
        "BIRDMONITOR_DEPLOYMENT_NOTES": args.notes or "",
        "BIRDMONITOR_NODE_LOCATION": args.site_name,
        "BIRDMONITOR_NODE_LAT": args.lat if args.lat is not None else "",
        "BIRDMONITOR_NODE_LON": args.lon if args.lon is not None else "",
        "BIRDMONITOR_AUTO_GEOLOCATION": "0",
    }
    if args.legacy_site_code or args.legacy_deployment_id:
        legacy_code = (args.legacy_site_code or "").strip().lower()
        if not SITE_CODE_PATTERN.fullmatch(legacy_code):
            raise ValueError("legacy-site-code no es valido")
        values["BIRDMONITOR_LEGACY_SITE_CODE"] = legacy_code
        values["BIRDMONITOR_LEGACY_DEPLOYMENT_ID"] = _valid_uuid(
            args.legacy_deployment_id,
            "legacy-deployment-id",
        )
    elif existing.get("BIRDMONITOR_LEGACY_DEPLOYMENT_ID"):
        values["BIRDMONITOR_LEGACY_SITE_CODE"] = existing.get(
            "BIRDMONITOR_LEGACY_SITE_CODE",
            "",
        )
        values["BIRDMONITOR_LEGACY_DEPLOYMENT_ID"] = existing[
            "BIRDMONITOR_LEGACY_DEPLOYMENT_ID"
        ]

    return {key: _safe_env_value(value) for key, value in values.items()}, reuse


def render_env(lines: list[str], values: dict[str, str]) -> str:
    rendered = []
    written = set()
    for raw_line in lines:
        stripped = raw_line.strip()
        candidate = stripped[7:].strip() if stripped.startswith("export ") else stripped
        key = candidate.split("=", 1)[0].strip() if "=" in candidate else ""
        if key in values:
            if key not in written:
                rendered.append(f"{key}={values[key]}")
                written.add(key)
            continue
        rendered.append(raw_line)

    missing = [key for key in MANAGED_KEYS if key in values and key not in written]
    if missing:
        if rendered and rendered[-1].strip():
            rendered.append("")
        rendered.append("# Sitio y despliegue gestionados por configure_site.py")
        rendered.extend(f"{key}={values[key]}" for key in missing)
    return "\n".join(rendered).rstrip() + "\n"


def write_env_atomic(path: Path, content: str) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    original_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    backup_path = None
    if path.exists():
        backup_dir = path.parent / "backups"
        backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        backup_path = backup_dir / (
            f"{path.name}.before-site-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        shutil.copy2(path, backup_path)
        os.chmod(backup_path, 0o600)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    try:
        os.chmod(temporary_path, original_mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return backup_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Configura de forma segura el sitio activo de BirdMonitor",
    )
    parser.add_argument(
        "--env-file",
        default="/etc/birdmonitor/birdmonitor.env",
    )
    parser.add_argument("--site-code", required=True)
    parser.add_argument("--site-name", required=True)
    parser.add_argument("--municipality")
    parser.add_argument("--region")
    parser.add_argument("--country-code", default="ES")
    parser.add_argument("--timezone", default="Europe/Madrid")
    parser.add_argument(
        "--location-source",
        choices=("manual", "gps", "ip_geolocation", "unknown"),
        default="manual",
    )
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--accuracy-m", type=float)
    parser.add_argument("--notes")
    parser.add_argument("--deployment-id")
    parser.add_argument("--started-at")
    parser.add_argument("--new-deployment", action="store_true")
    parser.add_argument("--legacy-site-code")
    parser.add_argument("--legacy-deployment-id")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    env_path = Path(args.env_file).resolve()
    lines, existing = read_env(env_path)
    values, reused = build_site_values(args, existing)
    content = render_env(lines, values)

    print(f"Sitio: {values['BIRDMONITOR_SITE_CODE']}")
    print(f"Nombre: {values['BIRDMONITOR_SITE_NAME']}")
    print(f"Deployment UUID: {values['BIRDMONITOR_DEPLOYMENT_ID']}")
    print(f"UUID reutilizado: {'si' if reused else 'no'}")
    print(f"Inicio: {values['BIRDMONITOR_DEPLOYMENT_STARTED_AT']}")
    print("Secretos conservados: si")

    if args.dry_run:
        print("Modo dry-run: no se ha escrito ningun archivo.")
        return 0

    backup_path = write_env_atomic(env_path, content)
    print(f"Configuracion guardada: {env_path}")
    if backup_path:
        print(f"Copia previa: {backup_path}")
    print("Reinicia birdmonitor.service solo despues de validar el backend.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())