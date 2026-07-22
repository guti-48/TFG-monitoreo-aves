import wave
from datetime import datetime, timezone

import numpy as np

from backend.app import review_media


def _write_test_wav(path, duration_seconds=30, sample_rate=8000):
    times = np.arange(duration_seconds * sample_rate, dtype=np.float32) / sample_rate
    samples = 0.18 * np.sin(2 * np.pi * 1200 * times)
    samples += 0.04 * np.sin(2 * np.pi * 320 * times)
    pcm = np.int16(np.clip(samples, -1.0, 1.0) * 32767)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


def _detection_payload(filename, suffix, **extra):
    payload = {
        "species": f"Barn Swallow {suffix}",
        "confidence": 0.93,
        "timestamp": datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc).isoformat(),
        "filename": filename,
        "device_name": f"review-node-{suffix}",
        "amplitude": 0.14,
    }
    payload.update(extra)
    return payload


def test_review_media_recorta_20_segundos_y_genera_espectrograma(
    client,
    tmp_path,
    monkeypatch,
):
    audio_dir = tmp_path / "records"
    cache_dir = tmp_path / "review_segments"
    audio_dir.mkdir()
    filename = "record_review_timed.wav"
    _write_test_wav(audio_dir / filename)

    monkeypatch.setattr(review_media, "SERVER_AUDIO_DIR", audio_dir)
    monkeypatch.setattr(review_media, "REVIEW_SPECTROGRAM_DIR", cache_dir)

    create_response = client.post(
        "/detections/",
        json=_detection_payload(
            filename,
            "timed",
            audio_start_seconds=12.0,
            audio_end_seconds=15.0,
        ),
    )
    assert create_response.status_code == 200
    detection = create_response.json()
    assert detection["audio_start_seconds"] == 12.0
    assert detection["audio_end_seconds"] == 15.0

    media_response = client.get(f"/detections/{detection['id']}/review-media")
    assert media_response.status_code == 200
    media = media_response.json()
    assert media["timing_available"] is True
    assert media["review_start_seconds"] == 3.5
    assert media["review_end_seconds"] == 23.5
    assert media["review_duration_seconds"] == 20.0
    assert media["audio_url"] == f"/records/{filename}"

    image_response = client.get(media["spectrogram_url"])
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"
    assert image_response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_reintento_completa_tiempos_y_registro_antiguo_sigue_siendo_valido(client):
    filename = "record_review_backfill.wav"
    payload = _detection_payload(filename, "backfill")

    first_response = client.post("/detections/", json=payload)
    assert first_response.status_code == 200
    assert first_response.json()["audio_start_seconds"] is None

    payload["audio_start_seconds"] = 21.0
    payload["audio_end_seconds"] = 24.0
    retry_response = client.post("/detections/", json=payload)

    assert retry_response.status_code == 200
    assert retry_response.json()["id"] == first_response.json()["id"]
    assert retry_response.json()["audio_start_seconds"] == 21.0
    assert retry_response.json()["audio_end_seconds"] == 24.0


def test_rechaza_intervalo_de_audio_incompleto_o_invertido(client):
    incomplete = _detection_payload(
        "record_review_invalid_1.wav",
        "invalid-1",
        audio_start_seconds=5.0,
    )
    inverted = _detection_payload(
        "record_review_invalid_2.wav",
        "invalid-2",
        audio_start_seconds=8.0,
        audio_end_seconds=4.0,
    )

    assert client.post("/detections/", json=incomplete).status_code == 422
    assert client.post("/detections/", json=inverted).status_code == 422