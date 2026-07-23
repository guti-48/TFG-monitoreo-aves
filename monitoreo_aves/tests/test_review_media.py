import io
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
    clean_audio_dir = tmp_path / "review_audio"
    audio_dir.mkdir()
    filename = "record_review_timed.wav"
    _write_test_wav(audio_dir / filename)

    monkeypatch.setattr(review_media, "SERVER_AUDIO_DIR", audio_dir)
    monkeypatch.setattr(review_media, "REVIEW_SPECTROGRAM_DIR", cache_dir)
    monkeypatch.setattr(review_media, "REVIEW_AUDIO_DIR", clean_audio_dir)
    original_bytes = (audio_dir / filename).read_bytes()

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
    assert media["clean_audio_url"].endswith("/review-audio-clean")
    assert media["diagnostics"]["status"] == "review"
    assert "weak_bird_evidence" in media["diagnostics"]["warnings"]
    assert media["diagnostics"]["high_pass_hz"] == 250.0

    image_response = client.get(media["spectrogram_url"])
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"
    assert image_response.content.startswith(b"\x89PNG\r\n\x1a\n")

    clean_response = client.get(media["clean_audio_url"])
    assert clean_response.status_code == 200
    assert clean_response.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(clean_response.content), "rb") as clean_wav:
        assert clean_wav.getframerate() == 8000
        assert clean_wav.getnframes() == 20 * 8000

    assert (audio_dir / filename).read_bytes() == original_bytes


def test_diagnostico_detecta_zumbido_y_conserva_contraste_de_evento(tmp_path):
    sample_rate = 8000
    duration_seconds = 20
    times = np.arange(duration_seconds * sample_rate, dtype=np.float64) / sample_rate
    samples = 0.08 * np.sin(2 * np.pi * 50 * times)
    samples += 0.04 * np.sin(2 * np.pi * 100 * times)
    event = (times >= 8.5) & (times < 11.5)
    samples[event] += 0.08 * np.sin(2 * np.pi * 1800 * times[event])

    audio_path = tmp_path / "hum_with_bird_event.wav"
    pcm = np.int16(np.clip(samples, -1.0, 1.0) * 32767)
    with wave.open(str(audio_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())

    window = review_media.build_review_window(
        duration_seconds,
        audio_start_seconds=8.5,
        audio_end_seconds=11.5,
    )
    diagnostics = review_media.analyze_review_audio(audio_path, window)

    assert diagnostics.low_frequency_ratio > 0.5
    assert diagnostics.mains_hum_prominence_db >= 10.0
    assert diagnostics.bird_band_snr_db is not None
    assert diagnostics.bird_band_snr_db > 3.0
    assert "low_frequency_noise" in diagnostics.warnings
    assert "mains_hum" in diagnostics.warnings
    assert "weak_bird_evidence" not in diagnostics.warnings


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
