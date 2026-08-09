import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HARDWARE_DIR = PROJECT_ROOT / "hardware" / "raspberry_pi"
PYTEST_TMP_DIR = PROJECT_ROOT / ".tmp"
PYTEST_TMP_DIR.mkdir(parents=True, exist_ok=True)

# Se fija antes de que pytest recopile los modulos de pruebas. Incluso si un
# test importa el backend demasiado pronto, el motor SQL nunca puede apuntar a
# la base de datos operativa.
TEST_DB_PATH = PYTEST_TMP_DIR / f"birdmonitor_pytest_{uuid4().hex}.db"
os.environ["BIRDMONITOR_DB_PATH"] = str(TEST_DB_PATH)

os.environ["BIRDMONITOR_SECURITY_MODE"] = "disabled"
os.environ["BIRDMONITOR_NETWORK_MODE"] = "disabled"
# Las pruebas no deben heredar direcciones de una instalacion real desde
# backend/birdmonitor.env. Las URL se construyen con el host del TestClient.
os.environ["BIRDMONITOR_STREAM_BASE_URL"] = ""
os.environ["BIRDMONITOR_STREAM_RTSP_BASE_URL"] = ""

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if str(HARDWARE_DIR) not in sys.path:
    sys.path.insert(0, str(HARDWARE_DIR))


@pytest.fixture(scope="session")
def test_db_path():
    return TEST_DB_PATH


@pytest.fixture(scope="session")
def client(test_db_path):
    from backend.app.core import database
    from backend.app.domain import models
    from backend import analisisBiodiversidad
    from backend.app.main import app, asegurar_esquema_runtime

    analisisBiodiversidad.DB_PATH = str(test_db_path)
    models.Base.metadata.drop_all(bind=database.engine)
    models.Base.metadata.create_all(bind=database.engine)
    asegurar_esquema_runtime()

    with TestClient(app) as test_client:
        yield test_client

    database.engine.dispose()