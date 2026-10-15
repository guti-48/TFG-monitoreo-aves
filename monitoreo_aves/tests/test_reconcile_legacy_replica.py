from datetime import datetime
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.domain import models
from scripts.reconcile_legacy_replica import reconcile


@pytest.fixture
def historical_database(tmp_path):
    path = tmp_path / "history.db"
    engine = create_engine(f"sqlite:///{path}")
    models.Base.metadata.create_all(engine)
    public_id = str(uuid4())
    with Session(engine) as db:
        alias = models.Device(name="RaspberryPi_01")
        canonical = models.Device(name="birdmonitor")
        site = models.Site(code="sevilla", name="Sevilla", country_code="ES", timezone="Europe/Madrid")
        db.add_all([alias, canonical, site])
        db.flush()
        historical = models.Deployment(public_id=public_id, device_id=alias.id, site_id=site.id,
                                       started_at=datetime(2026, 1, 1))
        active = models.Deployment(public_id=str(uuid4()), device_id=canonical.id, site_id=site.id,
                                   started_at=datetime(2026, 9, 1))
        db.add_all([historical, active])
        db.flush()
        detection = models.Detection(species="Passer domesticus", confidence=.9, amplitude=.01,
                                     timestamp=datetime(2026, 1, 15), filename="original.wav",
                                     device_id=alias.id, deployment_id=historical.id)
        db.add(detection)
        db.flush()
        db.add(models.DetectionReview(detection_id=detection.id, status="validated", note="Conservar esta revision",
                                      reviewed_at=datetime(2026, 1, 16)))
        db.commit()
    engine.dispose()
    return path, dict(deployment_id=public_id, canonical_name="birdmonitor", aliases=["RaspberryPi_01"],
                     site_code="sevilla", started_at="2026-01-01T00:00:00", ended_at="2026-08-01T00:00:00")


def test_reconcile_preserves_observations_reviews_and_current_deployment(historical_database):
    path, args = historical_database
    assert reconcile(path, **args)["merge_device"] is True
    assert reconcile(path, **args, apply=True)["backup"]
    assert reconcile(path, **args, apply=True)["merge_device"] is False
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM devices").fetchall() == [("birdmonitor",)]
        assert db.execute("SELECT COUNT(*) FROM detections").fetchone()[0] == 1
        assert db.execute("SELECT note FROM detection_reviews").fetchone()[0] == "Conservar esta revision"
        assert db.execute("SELECT COUNT(*) FROM deployments WHERE ended_at IS NULL").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM detections x JOIN deployments d ON d.id=x.deployment_id WHERE x.device_id=d.device_id").fetchone()[0] == 1
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("change", [{"started_at": "2026-02-01T00:00:00"}, {"site_code": "algeciras"}, {"aliases": []}])
def test_invalid_plan_leaves_database_unchanged(historical_database, change):
    path, args = historical_database
    with pytest.raises(ValueError):
        reconcile(path, **(args | change), apply=True)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM deployments WHERE ended_at IS NULL").fetchone()[0] == 2
