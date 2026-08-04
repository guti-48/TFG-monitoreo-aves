import pytest

from scripts.configure_network_mode import (
    network_env_updates,
    resolve_server_host,
)


def test_genera_variables_del_modo_local(monkeypatch):
    monkeypatch.setattr(
        "scripts.configure_network_mode.host_is_assigned_locally",
        lambda host: True,
    )

    host = resolve_server_host("local", "192.168.1.32")
    updates = network_env_updates("local", host)

    assert updates["BIRDMONITOR_NETWORK_MODE"] == "local"
    assert updates["BIRDMONITOR_SERVER_HOST"] == "192.168.1.32"
    assert updates["BIRDMONITOR_STREAM_RTSP_BASE_URL"] == (
        "rtsp://192.168.1.32:8554"
    )


def test_genera_variables_del_modo_tailscale(monkeypatch):
    monkeypatch.setattr(
        "scripts.configure_network_mode.host_is_assigned_locally",
        lambda host: True,
    )

    host = resolve_server_host("tailscale", "100.98.248.58")
    updates = network_env_updates("tailscale", host)

    assert updates["BIRDMONITOR_NETWORK_MODE"] == "tailscale"
    assert "http://100.98.248.58:8000" in updates[
        "BIRDMONITOR_CORS_ORIGINS"
    ]


@pytest.mark.parametrize(
    ("mode", "host"),
    (
        ("tailscale", "192.168.1.32"),
        ("tailscale", "100.128.0.1"),
        ("local", "100.98.248.58"),
        ("local", "8.8.8.8"),
    ),
)
def test_rechaza_ip_ajena_al_modo(monkeypatch, mode, host):
    monkeypatch.setattr(
        "scripts.configure_network_mode.host_is_assigned_locally",
        lambda value: True,
    )

    with pytest.raises(ValueError):
        resolve_server_host(mode, host)
