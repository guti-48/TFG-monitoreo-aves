import json
import sqlite3
from argparse import Namespace
from pathlib import Path

import pytest

import configure_site
import deployment_context
import node_sync


def _context(site="algeciras", public_id="42000000-0000-4000-8000-000000000001"):
    return deployment_context.EventContext(
        device_name="birdmonitor",
        site_code=site,
        deployment_public_id=public_id,
    )


def test_contexto_de_despliegue_valida_y_construye_activacion(monkeypatch):
    monkeypatch.setattr(deployment_context, "SITE_CODE", "algeciras")
    monkeypatch.setattr(deployment_context, "SITE_NAME", "Algeciras temporal")
    monkeypatch.setattr(deployment_context, "NODE_LOCATION", "Algeciras")
    monkeypatch.setattr(deployment_context, "NODE_LAT", "36.14")
    monkeypatch.setattr(deployment_context, "NODE_LON", "-5.45")
    monkeypatch.setattr(
        deployment_context,
        "DEPLOYMENT_ID",
        "42000000-0000-4000-8000-000000000001",
    )
    monkeypatch.setattr(
        deployment_context,
        "DEPLOYMENT_STARTED_AT",
        "2026-08-23T12:00:00+00:00",
    )
    deployment_context.getCurrentDeploymentContext.cache_clear()

    context = deployment_context.getCurrentDeploymentContext()
    payload = context.activation_payload()

    assert context.site_code == "algeciras"
    assert payload["site"]["lat"] == 36.14
    assert payload["deployment_public_id"] == context.deployment_public_id


def test_contexto_incompleto_falla_cerrado(monkeypatch):
    monkeypatch.setattr(deployment_context, "DEPLOYMENT_ID", "")
    deployment_context.getCurrentDeploymentContext.cache_clear()

    with pytest.raises(
        deployment_context.DeploymentConfigurationError,
        match="UUID",
    ):
        deployment_context.getCurrentDeploymentContext()


def _configure_args(**overrides):
    values = {
        "site_code": "sevilla",
        "site_name": "Sevilla principal",
        "municipality": "Sevilla",
        "region": "Andalucia",
        "country_code": "ES",
        "timezone": "Europe/Madrid",
        "location_source": "manual",
        "lat": 37.38,
        "lon": -6.0,
        "accuracy_m": 10.0,
        "notes": "Prueba",
        "deployment_id": None,
        "started_at": None,
        "new_deployment": False,
        "legacy_site_code": None,
        "legacy_deployment_id": None,
    }
    values.update(overrides)
    return Namespace(**values)


def test_configurador_reutiliza_uuid_y_preserva_secretos(tmp_path):
    old_uuid = "43000000-0000-4000-8000-000000000001"
    env_path = tmp_path / "birdmonitor.env"
    env_path.write_text(
        "BIRDMONITOR_NODE_API_TOKEN=secreto-no-modificable\n"
        "BIRDMONITOR_SITE_CODE=sevilla\n"
        f"BIRDMONITOR_DEPLOYMENT_ID={old_uuid}\n"
        "BIRDMONITOR_DEPLOYMENT_STARTED_AT=2026-08-01T00:00:00+00:00\n",
        encoding="utf-8",
    )
    lines, existing = configure_site.read_env(env_path)
    values, reused = configure_site.build_site_values(
        _configure_args(),
        existing,
    )
    rendered = configure_site.render_env(lines, values)

    assert reused is True
    assert values["BIRDMONITOR_DEPLOYMENT_ID"] == old_uuid
    assert "BIRDMONITOR_NODE_API_TOKEN=secreto-no-modificable" in rendered

    moved, reused_after_move = configure_site.build_site_values(
        _configure_args(
            site_code="algeciras",
            site_name="Algeciras temporal",
            municipality="Algeciras",
            lat=36.14,
            lon=-5.45,
        ),
        existing,
    )
    assert reused_after_move is False
    assert moved["BIRDMONITOR_DEPLOYMENT_ID"] != old_uuid


def test_migracion_outbox_asigna_contexto_legacy_sin_usar_el_actual(
    tmp_path,
    monkeypatch,
):
    outbox = tmp_path / "offline_outbox.db"
    monkeypatch.setattr(node_sync, "OUTBOX_DB", str(outbox))
    node_sync.guardarEventoOffline(
        "detection",
        {
            "species": "Legacy bird",
            "confidence": 0.8,
            "timestamp": "2026-07-20T10:00:00+00:00",
            "amplitude": 0.01,
            "filename": "legacy_record",
        },
    )
    legacy = _context(
        site="sevilla",
        public_id="42000000-0000-4000-8000-000000000002",
    )

    assert node_sync.migrarContextoOutboxLegacy(legacy) == 1
    assert node_sync.migrarContextoOutboxLegacy(legacy) == 0

    with sqlite3.connect(outbox) as connection:
        payload = json.loads(
            connection.execute(
                "SELECT payload FROM outbox_events"
            ).fetchone()[0]
        )
    assert payload["site_code"] == "sevilla"
    assert payload["deployment_public_id"] == legacy.deployment_public_id


def test_sincronizacion_activa_despliegue_antes_de_enviar_eventos(
    tmp_path,
    monkeypatch,
):
    outbox = tmp_path / "offline_outbox.db"
    monkeypatch.setattr(node_sync, "OUTBOX_DB", str(outbox))
    monkeypatch.setattr(node_sync, "OUTPUT_FOLDER_AUDIO", str(tmp_path / "records"))
    monkeypatch.setattr(node_sync, "OUTPUT_FOLDER_IMG", str(tmp_path / "spectrograms"))
    context = _context()
    activation = {
        **context.event_fields(),
        "site": {
            "code": context.site_code,
            "name": "Algeciras",
            "country_code": "ES",
            "location_source": "manual",
            "timezone": "Europe/Madrid",
        },
        "started_at": "2026-08-23T12:00:00+00:00",
    }
    detection = {
        **context.event_fields(),
        "species": "Test bird",
        "confidence": 0.9,
        "timestamp": "2026-08-23T12:05:00+00:00",
        "filename": "phase4_test",
        "amplitude": 0.01,
    }
    node_sync.guardarEventoOffline("detection", detection)
    node_sync.guardarEventoOffline("deployment_start", activation)
    calls = []

    class Response:
        status_code = 200
        text = ""

    def fake_post(url, **kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr(node_sync.requests, "post", fake_post)
    node_sync.sincronizarRespaldo()

    assert calls[0].endswith("/node/deployments/activate")
    assert calls[1].endswith("/detections/")
    with sqlite3.connect(outbox) as connection:
        assert connection.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0] == 0
