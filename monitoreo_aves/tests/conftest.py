import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HARDWARE_DIR = PROJECT_ROOT / "hardware" / "raspberry_pi"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if str(HARDWARE_DIR) not in sys.path:
    sys.path.insert(0, str(HARDWARE_DIR))


@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "birdmonitor_test.db"
    os.environ["BIRDMONITOR_DB_PATH"] = str(db_path)
    return db_path


@pytest.fixture(scope="session")
def client(test_db_path):
    from backend.app import database, models
    from backend import analisisBiodiversidad
    from backend.app.main import app, asegurar_esquema_runtime

    analisisBiodiversidad.DB_PATH = str(test_db_path)
    models.Base.metadata.drop_all(bind=database.engine)
    models.Base.metadata.create_all(bind=database.engine)
    asegurar_esquema_runtime()

    with TestClient(app) as test_client:
        yield test_client

    database.engine.dispose()