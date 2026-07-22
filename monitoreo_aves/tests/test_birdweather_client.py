import sys
from datetime import datetime
from pathlib import Path


HARDWARE_DIR = Path(__file__).resolve().parents[1] / "hardware" / "raspberry_pi"
if str(HARDWARE_DIR) not in sys.path:
    sys.path.insert(0, str(HARDWARE_DIR))

import birdweather_client


def test_envia_deteccion_con_ruta_y_campos_oficiales(monkeypatch):
    captured = {}

    class SuccessfulResponse:
        status_code = 201
        text = ""

        @staticmethod
        def json():
            return {"success": True}

    def fake_post(url, json, headers, timeout):
        captured.update(
            url=url,
            payload=json,
            headers=headers,
            timeout=timeout,
        )
        return SuccessfulResponse()

    monkeypatch.setattr(birdweather_client, "BIRDWEATHER_ENABLED", True)
    monkeypatch.setattr(birdweather_client, "BIRDWEATHER_TOKEN", "station/token")
    monkeypatch.setattr(
        birdweather_client,
        "BIRDWEATHER_URL",
        "https://app.birdweather.com/api/v1/stations/{token}/detections",
    )
    monkeypatch.setattr(birdweather_client.requests, "post", fake_post)

    sent = birdweather_client.enviarDatosBirdWeather(
        species="Barn Swallow",
        scientific_name="Hirundo rustica",
        confidence=0.93,
        lat=37.3845,
        lon=-6.0001,
        timestamp="2026-07-22T14:24:18",
        audio_start_seconds=12.0,
    )

    assert sent is True
    assert captured["url"].endswith("/stations/station%2Ftoken/detections")
    payload = captured["payload"]
    assert payload["commonName"] == "Barn Swallow"
    assert payload["scientificName"] == "Hirundo rustica"
    assert payload["confidence"] == 0.93
    assert payload["lat"] == 37.3845
    assert payload["lon"] == -6.0001
    detection_time = datetime.fromisoformat(payload["timestamp"])
    assert detection_time.replace(tzinfo=None) == datetime(2026, 7, 22, 14, 24, 30)
    assert detection_time.utcoffset() is not None


def test_no_publica_si_falta_nombre_cientifico(monkeypatch):
    monkeypatch.setattr(birdweather_client, "BIRDWEATHER_ENABLED", True)
    monkeypatch.setattr(birdweather_client, "BIRDWEATHER_TOKEN", "station-token")

    def unexpected_post(*args, **kwargs):
        raise AssertionError("No debe llamar a BirdWeather sin nombre cientifico")

    monkeypatch.setattr(birdweather_client.requests, "post", unexpected_post)

    sent = birdweather_client.enviarDatosBirdWeather(
        species="Barn Swallow",
        confidence=0.93,
        lat=37.3845,
        lon=-6.0001,
        timestamp="2026-07-22T14:24:18",
    )

    assert sent is False


def test_convierte_la_url_legacy_sin_exponer_el_token(monkeypatch):
    monkeypatch.setattr(
        birdweather_client,
        "BIRDWEATHER_URL",
        "https://app.birdweather.com/api/v1/stations/detections",
    )

    result = birdweather_client.construirUrlDetecciones("station-token")

    assert result == (
        "https://app.birdweather.com/api/v1/stations/"
        "station-token/detections"
    )
