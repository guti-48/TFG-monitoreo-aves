import pytest

from scripts.macos.verify_backend import validate_health


def healthy_response():
    return {
        "status": "ok",
        "network_mode": "tailscale",
        "network_configured": True,
        "security": "required",
        "security_configured": True,
        "stream_security": "required",
        "stream_security_configured": True,
    }


def test_accepts_ready_backend():
    validate_health(healthy_response(), "tailscale")


@pytest.mark.parametrize("key,value", [
    ("status", "error"),
    ("network_mode", "local"),
    ("network_configured", False),
    ("security", "disabled"),
    ("security_configured", False),
    ("stream_security", "disabled"),
    ("stream_security_configured", False),
])
def test_rejects_http_success_with_unusable_configuration(key, value):
    response = healthy_response()
    response[key] = value
    with pytest.raises(ValueError, match=key):
        validate_health(response, "tailscale")


def test_rejects_an_unrelated_http_service():
    with pytest.raises(ValueError):
        validate_health({}, "tailscale")
