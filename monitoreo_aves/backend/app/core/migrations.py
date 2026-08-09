"""Migraciones SQLite versionadas y verificables de BirdMonitor."""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine


LOCATION_MIGRATION_VERSION = "20260809_01_sites_deployments"
LOCATION_MIGRATION_DESCRIPTION = (
    "Crea sitios y despliegues y asigna el historico existente a Sevilla"
)
_LEGACY_DEPLOYMENT_NAMESPACE = uuid.UUID("b07cd2ba-e592-4bc0-bb67-805ece746e59")
_SITE_CODE_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_INVALID_LOCATIONS = {
    "",
    "desconocida",
    "ubicacion_desconocida",
    "ubicación_desconocida",
    "unknown",
}


def legacy_deployment_public_id(site_code: str, device_id: int) -> str:
    """Identidad determinista compartida por migración y compatibilidad API."""
    return str(
        uuid.uuid5(
            _LEGACY_DEPLOYMENT_NAMESPACE,
            f"birdmonitor:legacy:{site_code}:device:{int(device_id)}",
        )
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _columns(connection: Connection, table_name: str) -> set[str]:
    return {
        column["name"]
        for column in inspect(connection).get_columns(table_name)
    }


def _ensure_column(
    connection: Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    if column_name not in _columns(connection, table_name):
        connection.exec_driver_sql(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


def ensure_legacy_runtime_columns(engine: Engine) -> None:
    """Conserva las ampliaciones anteriores en instalaciones antiguas."""
    with engine.begin() as connection:
        _ensure_column(connection, "devices", "lat", "FLOAT")
        _ensure_column(connection, "devices", "lon", "FLOAT")
        _ensure_column(connection, "devices", "location_source", "VARCHAR")
        _ensure_column(connection, "devices", "location_accuracy_m", "FLOAT")

        _ensure_column(
            connection,
            "detections",
            "audio_start_seconds",
            "FLOAT",
        )
        _ensure_column(
            connection,
            "detections",
            "audio_end_seconds",
            "FLOAT",
        )

        audio_columns = {
            "peak": "FLOAT",
            "clipping_ratio": "FLOAT",
            "dc_offset": "FLOAT",
            "noise_floor_rms": "FLOAT",
            "quality_status": "VARCHAR",
            "quality_detail": "VARCHAR",
            "mic_device": "VARCHAR",
            "birdnet_model": "VARCHAR",
            "birdnet_model_version": "VARCHAR",
            "birdnetlib_version": "VARCHAR",
            "acoustic_metrics_version": "VARCHAR",
        }
        for column_name, definition in audio_columns.items():
            _ensure_column(
                connection,
                "audio_metrics",
                column_name,
                definition,
            )


def _legacy_site_code() -> str:
    code = os.getenv("BIRDMONITOR_LEGACY_SITE_CODE", "sevilla").strip().lower()
    if not _SITE_CODE_PATTERN.fullmatch(code):
        raise RuntimeError(
            "BIRDMONITOR_LEGACY_SITE_CODE debe contener solo minusculas, "
            "numeros y guiones"
        )
    return code


def _country_code() -> str:
    code = os.getenv("BIRDMONITOR_LEGACY_COUNTRY_CODE", "ES").strip().upper()
    if len(code) != 2 or not code.isalpha():
        raise RuntimeError("BIRDMONITOR_LEGACY_COUNTRY_CODE debe tener dos letras")
    return code


def _canonical_device(connection: Connection):
    return connection.execute(
        text(
            """
            SELECT id, name, location, lat, lon,
                   location_source, location_accuracy_m
            FROM devices
            ORDER BY CASE WHEN name = 'birdmonitor' THEN 0 ELSE 1 END, id
            LIMIT 1
            """
        )
    ).mappings().first()


def _site_values(device) -> dict:
    code = _legacy_site_code()
    location = str(device["location"] or "").strip() if device else ""
    if location.casefold() in _INVALID_LOCATIONS:
        location = "Sevilla"

    parts = [part.strip() for part in location.split(",") if part.strip()]
    name = os.getenv("BIRDMONITOR_LEGACY_SITE_NAME", "").strip()
    municipality = os.getenv("BIRDMONITOR_LEGACY_MUNICIPALITY", "").strip()
    region = os.getenv("BIRDMONITOR_LEGACY_REGION", "").strip()

    lat = device["lat"] if device else None
    lon = device["lon"] if device else None
    if (lat is None) != (lon is None):
        lat, lon = None, None

    source = str(device["location_source"] or "unknown") if device else "unknown"
    if source not in {"manual", "gps", "ip_geolocation", "unknown"}:
        source = "unknown"

    return {
        "code": code,
        "name": name or location or "Sevilla",
        "municipality": municipality or (parts[0] if parts else "Sevilla"),
        "region": region or (parts[1] if len(parts) > 1 else "Andalucia"),
        "country_code": _country_code(),
        "lat": lat,
        "lon": lon,
        "location_source": source,
        "location_accuracy_m": (
            device["location_accuracy_m"] if device else None
        ),
        "timezone": (
            os.getenv("BIRDMONITOR_LEGACY_TIMEZONE", "Europe/Madrid").strip()
            or "Europe/Madrid"
        ),
    }


def _get_or_create_legacy_site(
    connection: Connection,
    device,
    applied_at: datetime,
) -> int:
    values = _site_values(device)
    existing = connection.execute(
        text("SELECT id FROM sites WHERE code = :code"),
        {"code": values["code"]},
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)

    result = connection.execute(
        text(
            """
            INSERT INTO sites (
                code, name, municipality, region, country_code,
                lat, lon, location_source, location_accuracy_m, timezone,
                created_at, updated_at, archived_at
            ) VALUES (
                :code, :name, :municipality, :region, :country_code,
                :lat, :lon, :location_source, :location_accuracy_m, :timezone,
                :created_at, :updated_at, NULL
            )
            """
        ),
        {**values, "created_at": applied_at, "updated_at": applied_at},
    )
    return int(result.lastrowid)


def _first_observation_at(connection: Connection, device_id: int, fallback):
    return connection.execute(
        text(
            """
            SELECT MIN(observed_at)
            FROM (
                SELECT timestamp AS observed_at
                FROM detections
                WHERE device_id = :device_id
                UNION ALL
                SELECT timestamp AS observed_at
                FROM audio_metrics
                WHERE device_id = :device_id
            )
            """
        ),
        {"device_id": device_id},
    ).scalar_one_or_none() or fallback


def _get_or_create_legacy_deployment(
    connection: Connection,
    *,
    device_id: int,
    site_id: int,
    site_code: str,
    applied_at: datetime,
) -> int:
    public_id = legacy_deployment_public_id(site_code, device_id)
    existing = connection.execute(
        text("SELECT id FROM deployments WHERE public_id = :public_id"),
        {"public_id": public_id},
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)

    active = connection.execute(
        text(
            """
            SELECT id, site_id
            FROM deployments
            WHERE device_id = :device_id AND ended_at IS NULL
            LIMIT 1
            """
        ),
        {"device_id": device_id},
    ).mappings().first()
    if active and int(active["site_id"]) == site_id:
        return int(active["id"])

    started_at = _first_observation_at(connection, device_id, applied_at)
    result = connection.execute(
        text(
            """
            INSERT INTO deployments (
                public_id, device_id, site_id, started_at, ended_at,
                created_at, updated_at, notes
            ) VALUES (
                :public_id, :device_id, :site_id, :started_at, :ended_at,
                :created_at, :updated_at, :notes
            )
            """
        ),
        {
            "public_id": public_id,
            "device_id": device_id,
            "site_id": site_id,
            "started_at": started_at,
            "ended_at": started_at if active else None,
            "created_at": applied_at,
            "updated_at": applied_at,
            "notes": "Despliegue historico creado por la migracion de ubicaciones",
        },
    )
    return int(result.lastrowid)


def _assert_no_unassigned_history(connection: Connection) -> None:
    checks = {
        "detections": "deployment_id",
        "audio_metrics": "deployment_id",
        "learning_rules": "site_id",
    }
    for table_name, column_name in checks.items():
        pending = connection.execute(
            text(
                f"SELECT COUNT(*) FROM {table_name} "
                f"WHERE {column_name} IS NULL"
            )
        ).scalar_one()
        if pending:
            raise RuntimeError(
                f"La migracion dejaria {pending} filas de {table_name} "
                f"sin {column_name}"
            )

    mismatched_detections = connection.execute(
        text(
            """
            SELECT COUNT(*)
            FROM detections AS d
            JOIN deployments AS p ON p.id = d.deployment_id
            WHERE d.device_id != p.device_id
            """
        )
    ).scalar_one()
    mismatched_metrics = connection.execute(
        text(
            """
            SELECT COUNT(*)
            FROM audio_metrics AS m
            JOIN deployments AS p ON p.id = m.deployment_id
            WHERE m.device_id != p.device_id
            """
        )
    ).scalar_one()
    if mismatched_detections or mismatched_metrics:
        raise RuntimeError("La migracion mezclaria datos de dispositivos distintos")


def _protect_post_migration_events(
    connection: Connection,
    *,
    detection_baseline_id: int,
    metric_baseline_id: int,
) -> None:
    """Impide duplicados nuevos sin borrar duplicados científicos heredados."""
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "uq_detections_deployment_event_post_location_migration "
        "ON detections(deployment_id, timestamp, species, filename) "
        "WHERE deployment_id IS NOT NULL "
        f"AND id > {int(detection_baseline_id)}"
    )
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "uq_audio_metric_deployment_event_post_location_migration "
        "ON audio_metrics(deployment_id, timestamp, filename) "
        "WHERE deployment_id IS NOT NULL "
        f"AND id > {int(metric_baseline_id)}"
    )


def apply_location_migration(engine: Engine) -> bool:
    """Aplica la migración histórica. Devuelve True solo si hizo cambios."""
    if engine.dialect.name != "sqlite":
        raise RuntimeError("La migracion de ubicaciones solo admite SQLite")

    with engine.begin() as connection:
        already_applied = connection.execute(
            text(
                "SELECT 1 FROM schema_migrations WHERE version = :version"
            ),
            {"version": LOCATION_MIGRATION_VERSION},
        ).first()
        if already_applied:
            return False

        detection_baseline_id = int(
            connection.execute(
                text("SELECT COALESCE(MAX(id), 0) FROM detections")
            ).scalar_one()
        )
        metric_baseline_id = int(
            connection.execute(
                text("SELECT COALESCE(MAX(id), 0) FROM audio_metrics")
            ).scalar_one()
        )

        _ensure_column(
            connection,
            "detections",
            "deployment_id",
            "INTEGER REFERENCES deployments(id)",
        )
        _ensure_column(
            connection,
            "audio_metrics",
            "deployment_id",
            "INTEGER REFERENCES deployments(id)",
        )
        _ensure_column(
            connection,
            "learning_rules",
            "site_id",
            "INTEGER REFERENCES sites(id)",
        )

        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_detections_deployment_id "
            "ON detections(deployment_id)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_audio_metrics_deployment_id "
            "ON audio_metrics(deployment_id)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_learning_rules_site_id "
            "ON learning_rules(site_id)"
        )

        devices = connection.execute(
            text("SELECT id FROM devices ORDER BY id")
        ).scalars().all()
        if devices:
            applied_at = _utc_now()
            canonical_device = _canonical_device(connection)
            site_id = _get_or_create_legacy_site(
                connection,
                canonical_device,
                applied_at,
            )
            site_code = _legacy_site_code()

            for raw_device_id in devices:
                device_id = int(raw_device_id)
                deployment_id = _get_or_create_legacy_deployment(
                    connection,
                    device_id=device_id,
                    site_id=site_id,
                    site_code=site_code,
                    applied_at=applied_at,
                )
                connection.execute(
                    text(
                        "UPDATE detections SET deployment_id = :deployment_id "
                        "WHERE device_id = :device_id AND deployment_id IS NULL"
                    ),
                    {"deployment_id": deployment_id, "device_id": device_id},
                )
                connection.execute(
                    text(
                        "UPDATE audio_metrics SET deployment_id = :deployment_id "
                        "WHERE device_id = :device_id AND deployment_id IS NULL"
                    ),
                    {"deployment_id": deployment_id, "device_id": device_id},
                )
                connection.execute(
                    text(
                        "UPDATE learning_rules SET site_id = :site_id "
                        "WHERE device_id = :device_id AND site_id IS NULL"
                    ),
                    {"site_id": site_id, "device_id": device_id},
                )

        _assert_no_unassigned_history(connection)
        _protect_post_migration_events(
            connection,
            detection_baseline_id=detection_baseline_id,
            metric_baseline_id=metric_baseline_id,
        )
        connection.execute(
            text(
                """
                INSERT INTO schema_migrations (version, applied_at, description)
                VALUES (:version, :applied_at, :description)
                """
            ),
            {
                "version": LOCATION_MIGRATION_VERSION,
                "applied_at": _utc_now(),
                "description": LOCATION_MIGRATION_DESCRIPTION,
            },
        )
        return True


def ensure_database_schema(engine: Engine) -> bool:
    """Crea tablas, conserva columnas anteriores y aplica migraciones pendientes."""
    from ..domain.models import Base

    Base.metadata.create_all(bind=engine)
    ensure_legacy_runtime_columns(engine)
    return apply_location_migration(engine)