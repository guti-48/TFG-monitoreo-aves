import numpy as np

import audio_processing
from audio_processing import analizarCalidadAudio


def test_calidad_audio_acepta_senal_limpia():
    sample_rate = 48_000
    times = np.arange(sample_rate, dtype=np.float32) / sample_rate
    audio = 0.1 * np.sin(2 * np.pi * 2_000 * times)

    calidad = analizarCalidadAudio(audio, sample_rate)

    assert calidad["quality_status"] == "ok"
    assert 0.09 <= calidad["peak"] <= 0.11
    assert calidad["clipping_ratio"] == 0.0
    assert abs(calidad["dc_offset"]) < 1e-5


def test_calidad_audio_detecta_senal_baja_y_saturacion():
    low_signal = analizarCalidadAudio(np.zeros(4_800, dtype=np.float32), 48_000)
    clipped = analizarCalidadAudio(np.ones(4_800, dtype=np.float32), 48_000)

    assert low_signal["quality_status"] == "low_signal"
    assert "clipping" in clipped["quality_status"]
    assert "dc_offset" in clipped["quality_status"]
    assert clipped["clipping_ratio"] == 1.0


def test_configura_ganancia_alsa_fija(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))

    monkeypatch.setattr(audio_processing.sys, "platform", "linux")
    monkeypatch.setattr(audio_processing.shutil, "which", lambda name: "/usr/bin/amixer")
    monkeypatch.setattr(audio_processing.subprocess, "run", fake_run)
    monkeypatch.setattr(audio_processing, "MIC_ALSA_CARD", "3")
    monkeypatch.setattr(audio_processing, "MIC_CAPTURE_VOLUME", "50%")
    monkeypatch.setattr(audio_processing, "MIC_AUTO_GAIN", "0")

    assert audio_processing.configurarGananciaMicrofono() is True
    assert calls[0][0] == ["amixer", "-c", "3", "sset", "Mic", "50%", "cap"]
    assert calls[1][0] == [
        "amixer",
        "-c",
        "3",
        "sset",
        "Auto Gain Control",
        "off",
    ]