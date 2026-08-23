from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from node_config import (
    DEPLOYMENT_ID,
    DEPLOYMENT_NOTES,
    DEPLOYMENT_STATE_FILE,
    DEPLOYMENT_STARTED_AT,
    LEGACY_DEPLOYMENT_ID,
    LEGACY_SITE_CODE,
    NODE_LAT,
    NODE_LOCATION,
    NODE_LON,
    NODE_NAME,
    SITE_CODE,
    SITE_COUNTRY_CODE,
    SITE_LOCATION_ACCURACY_M,
    SITE_LOCATION_SOURCE,
    SITE_MUNICIPALITY,
    SITE_NAME,
    SITE_REGION,
    SITE_TIMEZONE,
)


SITE_CODE_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
LOCATION_SOURCES = {"manual", "gps", "ip_geolocation", "unknown"}


class DeploymentConfigurationError(RuntimeError):
    pass


def _parse_uuid(value: str, variable: str) -> str:
    try:
        return str(UUID(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise DeploymentConfigurationError(
            f"{variable} debe contener un UUID valido"
        ) from exc


def _parse_coordinate(value, variable: str, minimum: float, maximum: float):
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise DeploymentConfigurationError(
            f"{variable} debe ser numerica"
        ) from exc
    if not minimum <= parsed <= maximum:
        raise DeploymentConfigurationError(
            f"{variable} esta fuera de rango"
        )
    return parsed


def _parse_started_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise DeploymentConfigurationError(
            "BIRDMONITOR_DEPLOYMENT_STARTED_AT debe ser una fecha ISO 8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DeploymentConfigurationError(
            "BIRDMONITOR_DEPLOYMENT_STARTED_AT debe incluir zona horaria"
        )
    return parsed.isoformat()


@dataclass(frozen=True)
class EventContext:
    device_name: str
    site_code: str
    deployment_public_id: str

    def event_fields(self) -> dict:
        return {
            "device_name": self.device_name,
            "site_code": self.site_code,
            "deployment_public_id": self.deployment_public_id,
        }

    def upload_fields(self) -> dict:
        return self.event_fields()


@dataclass(frozen=True)
class DeploymentContext(EventContext):
    site_name: str
    municipality: str | None
    region: str | None
    country_code: str
    lat: float | None
    lon: float | None
    location_source: str
    location_accuracy_m: float | None
    timezone: str
    started_at: str
    notes: str | None

    def activation_payload(self) -> dict:
        return {
            "device_name": self.device_name,
            "deployment_public_id": self.deployment_public_id,
            "site": {
                "code": self.site_code,
                "name": self.site_name,
                "municipality": self.municipality,
                "region": self.region,
                "country_code": self.country_code,
                "lat": self.lat,
                "lon": self.lon,
                "location_source": self.location_source,
                "location_accuracy_m": self.location_accuracy_m,
                "timezone": self.timezone,
            },
            "started_at": self.started_at,
            "notes": self.notes,
        }

    def state_payload(self) -> dict:
        return {
            "schema_version": 1,
            "device_name": self.device_name,
            "site_code": self.site_code,
            "deployment_public_id": self.deployment_public_id,
            "site_name": self.site_name,
            "municipality": self.municipality,
            "region": self.region,
            "country_code": self.country_code,
            "lat": self.lat,
            "lon": self.lon,
            "location_source": self.location_source,
            "location_accuracy_m": self.location_accuracy_m,
            "timezone": self.timezone,
            "started_at": self.started_at,
            "notes": self.notes,
        }


def _build_context(values: dict, source: str) -> DeploymentContext:
    device_name = str(values.get("device_name") or "").strip()
    site_code = str(values.get("site_code") or "").strip().lower()
    site_name = str(values.get("site_name") or "").strip()
    country_code = str(values.get("country_code") or "").strip().upper()
    location_source = str(values.get("location_source") or "").strip().lower()
    site_timezone = str(values.get("timezone") or "").strip()

    if not device_name:
        raise DeploymentConfigurationError(f"{source}: device_name esta vacio")
    if not SITE_CODE_PATTERN.fullmatch(site_code):
        raise DeploymentConfigurationError(
            f"{source}: site_code debe usar minusculas, numeros y guiones"
        )
    if not site_name:
        raise DeploymentConfigurationError(f"{source}: site_name esta vacio")
    if len(country_code) != 2 or not country_code.isalpha():
        raise DeploymentConfigurationError(
            f"{source}: country_code debe tener dos letras"
        )
    if location_source not in LOCATION_SOURCES:
        raise DeploymentConfigurationError(
            f"{source}: location_source no es valido"
        )
    if not site_timezone:
        raise DeploymentConfigurationError(f"{source}: timezone esta vacio")

    lat = _parse_coordinate(values.get("lat"), f"{source}: lat", -90, 90)
    lon = _parse_coordinate(values.get("lon"), f"{source}: lon", -180, 180)
    if (lat is None) != (lon is None):
        raise DeploymentConfigurationError(
            f"{source}: lat y lon deben ir juntas"
        )

    raw_accuracy = values.get("location_accuracy_m")
    accuracy = None
    if raw_accuracy is not None and raw_accuracy != "":
        try:
            accuracy = float(raw_accuracy)
        except (TypeError, ValueError) as exc:
            raise DeploymentConfigurationError(
                f"{source}: location_accuracy_m debe ser numerica"
            ) from exc
        if accuracy < 0 or lat is None:
            raise DeploymentConfigurationError(
                f"{source}: la precision requiere coordenadas y no puede ser negativa"
            )

    return DeploymentContext(
        device_name=device_name,
        site_code=site_code,
        deployment_public_id=_parse_uuid(
            values.get("deployment_public_id"),
            f"{source}: deployment_public_id",
        ),
        site_name=site_name,
        municipality=(str(values.get("municipality") or "").strip() or None),
        region=(str(values.get("region") or "").strip() or None),
        country_code=country_code,
        lat=lat,
        lon=lon,
        location_source=location_source,
        location_accuracy_m=accuracy,
        timezone=site_timezone,
        started_at=_parse_started_at(values.get("started_at")),
        notes=(str(values.get("notes") or "").strip() or None),
    )


def deploymentContextFromLocationCommand(
    command: dict,
    *,
    started_at: str | None = None,
) -> DeploymentContext:
    effective_started_at = command.get("deployment_started_at") or started_at
    if effective_started_at is None:
        effective_started_at = datetime.now(timezone.utc).isoformat()
    return _build_context(
        {
            "device_name": command.get("device_name"),
            "site_code": command.get("target_site_code"),
            "deployment_public_id": command.get("deployment_public_id"),
            "site_name": command.get("target_site_name"),
            "municipality": command.get("target_site_municipality"),
            "region": command.get("target_site_region"),
            "country_code": command.get("target_site_country_code"),
            "lat": command.get("target_site_lat"),
            "lon": command.get("target_site_lon"),
            "location_source": command.get("target_site_location_source"),
            "location_accuracy_m": command.get(
                "target_site_location_accuracy_m"
            ),
            "timezone": command.get("target_site_timezone"),
            "started_at": effective_started_at,
            "notes": command.get("notes") or "Cambio remoto confirmado desde dashboard",
        },
        "orden remota",
    )


def persistCurrentDeploymentContext(
    context: DeploymentContext,
    path: str | os.PathLike | None = None,
) -> Path:
    """Guarda el contexto con reemplazo atomico; nunca deja JSON parcial."""
    state_path = Path(path or DEPLOYMENT_STATE_FILE).resolve()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=state_path.parent,
            prefix=f".{state_path.name}.",
            delete=False,
        ) as temporary:
            json.dump(
                context.state_payload(),
                temporary,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, state_path)
        getCurrentDeploymentContext.cache_clear()
        return state_path
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _context_from_state_file(path: str | os.PathLike) -> DeploymentContext | None:
    state_path = Path(path)
    if not state_path.is_file():
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentConfigurationError(
            f"No se pudo leer el estado persistente {state_path}: {exc}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise DeploymentConfigurationError(
            f"El estado persistente {state_path} tiene un formato no compatible"
        )
    return _build_context(payload, f"estado {state_path}")


@lru_cache(maxsize=1)
def getCurrentDeploymentContext() -> DeploymentContext:
    persistent = _context_from_state_file(DEPLOYMENT_STATE_FILE)
    if persistent is not None:
        return persistent
    return _build_context(
        {
            "device_name": NODE_NAME,
            "site_code": SITE_CODE,
            "deployment_public_id": DEPLOYMENT_ID,
            "site_name": SITE_NAME or NODE_LOCATION,
            "municipality": SITE_MUNICIPALITY,
            "region": SITE_REGION,
            "country_code": SITE_COUNTRY_CODE,
            "lat": NODE_LAT,
            "lon": NODE_LON,
            "location_source": SITE_LOCATION_SOURCE,
            "location_accuracy_m": SITE_LOCATION_ACCURACY_M,
            "timezone": SITE_TIMEZONE,
            "started_at": DEPLOYMENT_STARTED_AT,
            "notes": DEPLOYMENT_NOTES,
        },
        "variables BIRDMONITOR_*",
    )


@lru_cache(maxsize=1)
def getLegacyEventContext() -> EventContext | None:
    if not LEGACY_SITE_CODE and not LEGACY_DEPLOYMENT_ID:
        return None
    if not SITE_CODE_PATTERN.fullmatch(LEGACY_SITE_CODE):
        raise DeploymentConfigurationError(
            "BIRDMONITOR_LEGACY_SITE_CODE no es valido"
        )
    return EventContext(
        device_name=NODE_NAME,
        site_code=LEGACY_SITE_CODE,
        deployment_public_id=_parse_uuid(
            LEGACY_DEPLOYMENT_ID,
            "BIRDMONITOR_LEGACY_DEPLOYMENT_ID",
        ),
    )