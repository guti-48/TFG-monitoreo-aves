import json
import os

import pytest

import deployment_context
import node_location
import node_sync


def _context(
    *,
    code="sevilla",
    public_id="71000000-0000-4000-8000-000000000001",
    started_at="2026-08-23T08:00:00+00:00",
):
    return deployment_context.DeploymentContext(
        device_name="birdmonitor",
        site_code=code,
        deployment_public_id=public_id,
        site_name=code.title(),
        municipality=code.title(),
        region="Andalucia",
        country_code="ES",
        lat=37.3891 if code == "sevilla" else 36.12942,
        lon=-5.9845 if code == "sevilla" else -5.45303,
        location_source="manual",
        location_accuracy_m=20.0,
        timezone="Europe/Madrid",
        started_at=started_at,
        notes="Prueba",
    )


def _command(**overrides):
    values = {
        "public_id": "72000000-0000-4000-8000-000000000001",
        "device_name": "birdmonitor",
        "target_site_code": "algeciras",
        "target_site_name": "Colegio Salesianos - Algeciras",
        "target_site_municipality": "Algeciras",
        "target_site_region": "Cadiz",
        "target_site_country_code": "ES",
        "target_site_lat": 36.12942,
        "target_site_lon": -5.45303,
        "target_site_location_source": "manual",
        "target_site_location_accuracy_m": 150,
        "target_site_timezone": "Europe/Madrid",
        "deployment_public_id": "71000000-0000-4000-8000-000000000002",
        "deployment_started_at": None,
        "notes": "Traslado confirmado",
    }
    values.update(overrides)
    return values


def test_estado_remoto_se_persiste_atomicamente_y_prevalece_sobre_env(
    tmp_path,
    monkeypatch,
):
    state_path = tmp_path / "deployment_state.json"
    monkeypatch.setattr(deployment_context, "DEPLOYMENT_STATE_FILE", str(state_path))
    context = _context(code="algeciras")

    stored = deployment_context.persistCurrentDeploymentContext(context)
    assert stored == state_path.resolve()
    if os.name != "nt":
        assert state_path.stat().st_mode & 0o777 == 0o600
    assert json.loads(state_path.read_text(encoding="utf-8"))["site_code"] == "algeciras"

    loaded = deployment_context.getCurrentDeploymentContext()
    assert loaded == context
    assert loaded.site_code != deployment_context.SITE_CODE


def test_estado_persistente_corrupto_falla_cerrado(tmp_path, monkeypatch):
    state_path = tmp_path / "deployment_state.json"
    state_path.write_text("{incompleto", encoding="utf-8")
    monkeypatch.setattr(deployment_context, "DEPLOYMENT_STATE_FILE", str(state_path))
    deployment_context.getCurrentDeploymentContext.cache_clear()

    with pytest.raises(
        deployment_context.DeploymentConfigurationError,
        match="estado persistente",
    ):
        deployment_context.getCurrentDeploymentContext()


def test_ubicacion_y_birdnet_usan_el_contexto_activo():
    context = _context(code="algeciras")
    location = node_location.obtenerUbicacionNodo(context)

    assert location == {
        "location": "Algeciras",
        "lat": 36.12942,
        "lon": -5.45303,
        "source": "manual",
    }


def test_cambio_remoto_respeta_orden_activar_persistir_confirmar(monkeypatch):
    calls = []
    current = _context()
    command = _command()
    monkeypatch.setattr(node_sync, "obtenerOrdenCambioUbicacion", lambda: command)
    monkeypatch.setattr(node_sync, "getCurrentDeploymentContext", lambda: current)
    monkeypatch.setattr(
        node_sync,
        "activarDespliegue",
        lambda context, queue_on_failure=False: calls.append(
            ("activate", context)
        ) or True,
    )
    monkeypatch.setattr(
        node_sync,
        "persistCurrentDeploymentContext",
        lambda context: calls.append(("persist", context)) or "/state.json",
    )
    monkeypatch.setattr(
        node_sync,
        "confirmarOrdenCambioUbicacion",
        lambda command_id, **kwargs: calls.append(("ack", command_id, kwargs)) or True,
    )

    assert node_sync.procesarCambioUbicacionPendiente() is True
    assert [call[0] for call in calls] == ["activate", "persist", "ack"]
    candidate = calls[0][1]
    assert candidate.site_code == "algeciras"
    assert calls[2][2]["deployment_started_at"] == candidate.started_at


def test_sin_red_o_activacion_no_confirmada_conserva_sitio_actual(monkeypatch):
    current = _context()
    persisted = []
    acknowledgements = []
    monkeypatch.setattr(node_sync, "obtenerOrdenCambioUbicacion", lambda: _command())
    monkeypatch.setattr(node_sync, "getCurrentDeploymentContext", lambda: current)
    monkeypatch.setattr(node_sync, "activarDespliegue", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        node_sync,
        "persistCurrentDeploymentContext",
        lambda context: persisted.append(context),
    )
    monkeypatch.setattr(
        node_sync,
        "confirmarOrdenCambioUbicacion",
        lambda *args, **kwargs: acknowledgements.append((args, kwargs)),
    )

    assert node_sync.procesarCambioUbicacionPendiente() is False
    assert persisted == []
    assert acknowledgements == []


def test_fallo_de_ack_reinicia_y_permite_reintento_idempotente(monkeypatch):
    current = _context()
    command = _command(
        deployment_started_at="2026-08-23T09:30:00+00:00",
    )
    persisted = []
    monkeypatch.setattr(node_sync, "obtenerOrdenCambioUbicacion", lambda: command)
    monkeypatch.setattr(node_sync, "getCurrentDeploymentContext", lambda: current)
    monkeypatch.setattr(node_sync, "activarDespliegue", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        node_sync,
        "persistCurrentDeploymentContext",
        lambda context: persisted.append(context) or "/state.json",
    )
    monkeypatch.setattr(node_sync, "confirmarOrdenCambioUbicacion", lambda *args, **kwargs: False)

    assert node_sync.procesarCambioUbicacionPendiente() is True
    assert persisted[0].started_at == command["deployment_started_at"]


def test_fallo_al_persistir_despues_de_activar_es_critico(monkeypatch):
    monkeypatch.setattr(node_sync, "obtenerOrdenCambioUbicacion", lambda: _command())
    monkeypatch.setattr(node_sync, "getCurrentDeploymentContext", lambda: _context())
    monkeypatch.setattr(node_sync, "activarDespliegue", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        node_sync,
        "persistCurrentDeploymentContext",
        lambda context: (_ for _ in ()).throw(OSError("disco lleno")),
    )

    with pytest.raises(node_sync.RemoteLocationStateError, match="disco lleno"):
        node_sync.procesarCambioUbicacionPendiente()
