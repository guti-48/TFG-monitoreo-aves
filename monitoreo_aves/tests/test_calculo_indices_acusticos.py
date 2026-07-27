import numpy as np
import pytest
import soundfile as sf
from maad import features, sound

from audio_processing import calcularMetricasAcusticas


def test_metricas_maad_v2_respetan_unidades_funciones_y_bandas(tmp_path):
    fs = 48000
    duration = 2.0
    times = np.arange(int(fs * duration)) / fs
    signal = (
        0.15 * np.sin(2 * np.pi * 700 * times)
        + 0.08 * (1 + np.sin(2 * np.pi * 3 * times))
        * np.sin(2 * np.pi * 4200 * times)
    ).astype(np.float32)
    wav_path = tmp_path / "metricas-v2.wav"
    sf.write(wav_path, signal, fs)

    result = calcularMetricasAcusticas(str(wav_path))
    assert result is not None
    assert result["acoustic_metrics_version"] == "maad-v2"

    samples, loaded_fs = sound.load(str(wav_path))
    power, _, frequencies, _ = sound.spectrogram(
        samples, loaded_fs, mode="psd"
    )
    amplitude = np.sqrt(np.maximum(power, 0.0))

    _, _, aci = features.acoustic_complexity_index(amplitude)
    expected_adi = features.acoustic_diversity_index(
        amplitude,
        frequencies,
        fmin=250,
        fmax=10000,
        bin_step=1000,
        dB_threshold=-47,
    )
    expected_aei = features.acoustic_eveness_index(
        amplitude,
        frequencies,
        fmin=250,
        fmax=10000,
        bin_step=500,
        dB_threshold=-47,
    )
    expected_bio = features.bioacoustics_index(
        amplitude,
        frequencies,
        flim=(2000, 10000),
    )
    expected_ndsi, _, _, _ = features.soundscape_index(
        power,
        frequencies,
        flim_bioPh=(1000, 10000),
        flim_antroPh=(0, 1000),
    )
    expected_ht = features.temporal_entropy(samples)
    expected_hf, _ = features.frequency_entropy(power)

    assert result["aci"] == pytest.approx(float(np.sum(aci)))
    assert result["adi"] == pytest.approx(float(expected_adi))
    assert result["aei"] == pytest.approx(float(expected_aei))
    assert result["bio"] == pytest.approx(float(expected_bio))
    assert result["ndsi"] == pytest.approx(float(expected_ndsi))
    assert result["ht"] == pytest.approx(float(expected_ht))
    assert result["hf"] == pytest.approx(float(expected_hf))
    assert result["h"] == pytest.approx(float(expected_ht * expected_hf))
    assert result["aei"] != pytest.approx(1 - result["adi"] / 3)