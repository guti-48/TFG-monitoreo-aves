import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from backend.app.core.migrations import (
    LOCATION_MIGRATION_VERSION,
    ensure_database_schema,
)


def _create_legacy_database(db_path: Path) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=ON;

            CREATE TABLE devices (
                id INTEGER PRIMARY KEY,
                name VARCHAR UNIQUE,
                location VARCHAR,
                lat FLOAT,
                lon FLOAT,
                location_source VARCHAR,
                location_accuracy_m FLOAT
            );

            CREATE TABLE detections (
                id INTEGER PRIMARY KEY,
                timestamp DATETIME,
                species VARCHAR,
                confidence FLOAT,
                filename VARCHAR,
                amplitude FLOAT,
                audio_start_seconds FLOAT,
                audio_end_seconds FLOAT,
                device_id INTEGER REFERENCES devices(id)
            );

            CREATE TABLE audio_metrics (
                id INTEGER PRIMARY KEY,
                timestamp DATETIME,
                filename VARCHAR,
                sample_rate INTEGER,
                duration FLOAT,
                rms FLOAT,
                aci FLOAT,
                adi FLOAT,
                aei FLOAT,
                bio FLOAT,
                ndsi FLOAT,
                ht FLOAT,
                hf FLOAT,
                h FLOAT,
                device_id INTEGER REFERENCES devices(id)
            );

            CREATE TABLE learning_rules (
                id INTEGER PRIMARY KEY,
                device_id INTEGER NOT NULL REFERENCES devices(id),
                original_species VARCHAR NOT NULL,
                learned_status VARCHAR NOT NULL,
                corrected_species VARCHAR,
                min_confidence FLOAT NOT NULL,
                max_confidence FLOAT NOT NULL,
                min_amplitude FLOAT,
                max_amplitude FLOAT,
                support_count INTEGER NOT NULL,
                active BOOLEAN NOT NULL,
                auto_apply BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO devices (
                id, name, location, lat, lon,
                location_source, location_accuracy_m
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "birdmonitor",
                "Sevilla, Andalucia, Espana",
                37.3845,
                -6.0001,
                "manual",
                10.0,
            ),
        )
        detections = [
            (
                1,
                "2026-05-07 16:36:24.000000",
                "Common Kingfisher",
                0.91,
                "record_2026-05-07_16-36-24.wav",
                0.1,
                1,
            ),
            (
                2,
                "2026-05-07 16:36:24.000000",
                "Common Kingfisher",
                0.91,
                "record_2026-05-07_16-36-24.wav",
                0.1,
                1,
            ),
        ]
        connection.executemany(
            """
            INSERT INTO detections (
                id, timestamp, species, confidence, filename, amplitude, device_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            detections,
        )
        connection.execute(
            """
            INSERT INTO audio_metrics (
                id, timestamp, filename, sample_rate, duration, rms,
                aci, adi, aei, bio, ndsi, ht, hf, h, device_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "2026-05-07 16:35:00.000000",
                "record_2026-05-07_16-35-00.wav",
                48000,
                60.0,
                0.01,
                1.0,
                1.0,
                1.0,
                1.0,
                0.0,
                1.0,
                1.0,
                1.0,
                1,
            ),
        )
        connection.execute(
            """
            INSERT INTO learning_rules (
                id, device_id, original_species, learned_status,
                min_confidence, max_confidence, support_count,
                active, auto_apply, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                1,
                "Rose-ringed Parakeet",
                "validated",
                0.60,
                1.0,
                3,
                1,
                1,
                "2026-05-08 10:00:00.000000",
                "2026-05-08 10:00:00.000000",
            ),
        )
        connection.commit()


def _engine_for(db_path: Path):
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )


def test_migra_historico_a_sevilla_sin_perder_duplicados(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_database(db_path)
    engine = _engine_for(db_path)

    with engine.connect() as connection:
        original_detections = connection.execute(
            text(
                "SELECT id, timestamp, species, confidence, filename, amplitude, "
                "device_id FROM detections ORDER BY id"
            )
        ).all()

    assert ensure_database_schema(engine) is True

    with engine.connect() as connection:
        site = connection.execute(
            text(
                "SELECT id, code, name, lat, lon, timezone "
                "FROM sites"
            )
        ).mappings().one()
        deployment = connection.execute(
            text(
                "SELECT id, public_id, device_id, site_id, started_at, ended_at "
                "FROM deployments"
            )
        ).mappings().one()
        migrated_detections = connection.execute(
            text(
                "SELECT id, timestamp, species, confidence, filename, amplitude, "
                "device_id FROM detections ORDER BY id"
            )
        ).all()

        assert site["code"] == "sevilla"
        assert site["lat"] == pytest.approx(37.3845)
        assert site["lon"] == pytest.approx(-6.0001)
        assert site["timezone"] == "Europe/Madrid"
        assert deployment["device_id"] == 1
        assert deployment["site_id"] == site["id"]
        assert deployment["started_at"] == "2026-05-07 16:35:00.000000"
        assert deployment["ended_at"] is None
        assert len(deployment["public_id"]) == 36
        assert migrated_detections == original_detections

        deployment_ids = connection.execute(
            text("SELECT DISTINCT deployment_id FROM detections")
        ).scalars().all()
        metric_deployment = connection.execute(
            text("SELECT deployment_id FROM audio_metrics WHERE id = 1")
        ).scalar_one()
        rule_site = connection.execute(
            text("SELECT site_id FROM learning_rules WHERE id = 1")
        ).scalar_one()
        assert deployment_ids == [deployment["id"]]
        assert metric_deployment == deployment["id"]
        assert rule_site == site["id"]

        migration_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM schema_migrations "
                "WHERE version = :version"
            ),
            {"version": LOCATION_MIGRATION_VERSION},
        ).scalar_one()
        assert migration_count == 1

    engine.dispose()


def test_migracion_es_idempotente_y_no_duplica_entidades(tmp_path):
    db_path = tmp_path / "idempotent.db"
    _create_legacy_database(db_path)
    engine = _engine_for(db_path)

    assert ensure_database_schema(engine) is True
    assert ensure_database_schema(engine) is False

    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM sites")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM deployments")).scalar_one() == 1
        assert connection.execute(
            text("SELECT COUNT(*) FROM detections")
        ).scalar_one() == 2
        versions = {
            row[0]
            for row in connection.execute(
                text("SELECT version FROM schema_migrations")
            ).fetchall()
        }
        assert versions == {
            "20260809_01_sites_deployments",
            "20260823_02_node_location_commands",
        }

    engine.dispose()


def test_conserva_duplicados_legacy_y_bloquea_duplicados_nuevos(tmp_path):
    db_path = tmp_path / "new-duplicates.db"
    _create_legacy_database(db_path)
    engine = _engine_for(db_path)
    ensure_database_schema(engine)

    with engine.connect() as connection:
        deployment_id = connection.execute(
            text("SELECT id FROM deployments")
        ).scalar_one()

    payload = {
        "timestamp": "2026-08-09 18:00:00.000000",
        "species": "Rose-ringed Parakeet",
        "confidence": 0.9,
        "filename": "record_2026-08-09_18-00-00.wav",
        "amplitude": 0.2,
        "device_id": 1,
        "deployment_id": deployment_id,
    }
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO detections (
                    timestamp, species, confidence, filename, amplitude,
                    device_id, deployment_id
                ) VALUES (
                    :timestamp, :species, :confidence, :filename, :amplitude,
                    :device_id, :deployment_id
                )
                """
            ),
            payload,
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO detections (
                        timestamp, species, confidence, filename, amplitude,
                        device_id, deployment_id
                    ) VALUES (
                        :timestamp, :species, :confidence, :filename, :amplitude,
                        :device_id, :deployment_id
                    )
                    """
                ),
                payload,
            )

    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM detections WHERE id IN (1, 2)")
        ).scalar_one() == 2

    engine.dispose()


def test_solo_permite_un_despliegue_activo_por_dispositivo(tmp_path):
    db_path = tmp_path / "active-deployment.db"
    _create_legacy_database(db_path)
    engine = _engine_for(db_path)
    ensure_database_schema(engine)

    with engine.begin() as connection:
        site_id = connection.execute(text("SELECT id FROM sites")).scalar_one()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO deployments (
                        public_id, device_id, site_id, started_at,
                        created_at, updated_at
                    ) VALUES (
                        :public_id, 1, :site_id, :started_at,
                        :created_at, :updated_at
                    )
                    """
                ),
                {
                    "public_id": "11111111-1111-4111-8111-111111111111",
                    "site_id": site_id,
                    "started_at": "2026-08-01 00:00:00.000000",
                    "created_at": "2026-08-01 00:00:00.000000",
                    "updated_at": "2026-08-01 00:00:00.000000",
                },
            )

    engine.dispose()


def test_esquema_nuevo_valida_pareja_y_rango_de_coordenadas(tmp_path):
    db_path = tmp_path / "fresh.db"
    engine = _engine_for(db_path)

    assert ensure_database_schema(engine) is True
    table_names = set(inspect(engine).get_table_names())
    assert {"sites", "deployments", "schema_migrations"} <= table_names

    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO sites (
                        code, name, country_code, lat, lon, location_source,
                        timezone, created_at, updated_at
                    ) VALUES (
                        'invalido', 'Invalido', 'ES', 95, NULL, 'manual',
                        'Europe/Madrid', :now, :now
                    )
                    """
                ),
                {"now": "2026-08-09 12:00:00.000000"},
            )

    engine.dispose()
