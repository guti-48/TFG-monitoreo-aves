import os
import stat

import pytest

from backend.app.core.security import verify_admin_password
from scripts.configure_security import change_admin_password


def test_password_change_preserves_other_credentials(tmp_path):
    path = tmp_path / "birdmonitor.env"
    preserved = (
        "# Configuracion existente\n"
        "BIRDMONITOR_ADMIN_USERNAME=carlos\n"
        "BIRDMONITOR_NODE_TOKEN_HASH=node-hash\n"
        "BIRDMONITOR_INGEST_TOKEN_HASH=ingest-hash\n"
        "BIRDMONITOR_REPLICATION_TOKEN_HASH=replica-hash\n"
        "BIRDMONITOR_STREAM_PROXY_PASSWORD=stream-secret\n"
        "BIRDMONITOR_NETWORK_MODE=tailscale\n"
    )
    path.write_text(preserved + "BIRDMONITOR_ADMIN_PASSWORD_HASH=old-hash\n"
                    "BIRDMONITOR_SESSION_SECRET=old-session\n")
    password = "nueva-contrasena-de-prueba"
    change_admin_password(path, password)
    content = path.read_text()
    assert content.startswith(preserved)
    values = dict(line.split("=", 1) for line in content.splitlines() if "=" in line)
    assert verify_admin_password(password, values["BIRDMONITOR_ADMIN_PASSWORD_HASH"])
    assert not verify_admin_password("otra-contrasena", values["BIRDMONITOR_ADMIN_PASSWORD_HASH"])
    assert values["BIRDMONITOR_SESSION_SECRET"] != "old-session"
    assert password not in content
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_incomplete_configuration_is_not_overwritten(tmp_path):
    path = tmp_path / "birdmonitor.env"
    original = "BIRDMONITOR_NODE_TOKEN_HASH=preserve\n"
    path.write_text(original)
    with pytest.raises(ValueError, match="Falta la configuracion"):
        change_admin_password(path, "una-contrasena-valida")
    assert path.read_text() == original
