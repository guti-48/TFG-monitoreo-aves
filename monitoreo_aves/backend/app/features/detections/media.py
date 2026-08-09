from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import numpy as np
import soundfile as sf
from scipy import signal

from ...core.config import SERVER_AUDIO_DIR, SPECTOGRAM_DIR


REVIEW_WINDOW_SECONDS = 20.0
REVIEW_SPECTROGRAM_DIR = SPECTOGRAM_DIR / "review_segments"
REVIEW_RENDER_VERSION = 4
REVIEW_HIGH_PASS_HZ = 250.0
REVIEW_BIRD_BAND_MIN_HZ = 1200.0
REVIEW_MAX_FREQUENCY_HZ = 10000.0
REVIEW_SPECTROGRAM_CONTRAST_DB = 24.0
_SPECTROGRAM_LOCK = Lock()


@dataclass(frozen=True)
class ReviewWindow:
    audio_duration_seconds: float
    review_start_seconds: float
    review_end_seconds: float
    audio_start_seconds: float | None
    audio_end_seconds: float | None
    timing_available: bool

    @property
    def review_duration_seconds(self) -> float:
        return self.review_end_seconds - self.review_start_seconds


@dataclass(frozen=True)
class ReviewAudioDiagnostics:
    status: str
    summary: str
    warnings: list[str]
    low_frequency_ratio: float
    mains_hum_prominence_db: float
    bird_band_snr_db: float | None
    high_pass_hz: float


def resolve_audio_path(filename: str, deployment=None) -> Path:
    safe_name = Path(filename or "").name
    if not safe_name:
        raise FileNotFoundError("La deteccion no tiene un archivo WAV asociado")

    if Path(safe_name).suffix.lower() != ".wav":
        safe_name = f"{Path(safe_name).stem}.wav"

    audio_dir = SERVER_AUDIO_DIR.resolve()
    candidate_dirs = []
    if deployment is not None and getattr(deployment, "site", None) is not None:
        candidate_dirs.append(
            audio_dir / deployment.site.code / deployment.public_id
        )
    candidate_dirs.append(audio_dir)

    for candidate_dir in candidate_dirs:
        audio_path = (candidate_dir / safe_name).resolve()
        try:
            audio_path.relative_to(audio_dir)
        except ValueError as exc:
            raise FileNotFoundError("Ruta de audio no permitida") from exc
        if audio_path.is_file():
            return audio_path

    raise FileNotFoundError(f"No se encontro el audio {safe_name}")


def get_audio_duration(audio_path: Path) -> float:
    info = sf.info(str(audio_path))
    duration = float(info.frames) / float(info.samplerate)
    if duration <= 0:
        raise ValueError("El archivo WAV no contiene audio")
    return duration


def _read_review_audio(
    audio_path: Path,
    window: ReviewWindow,
) -> tuple[np.ndarray, int]:
    with sf.SoundFile(str(audio_path)) as audio_file:
        sample_rate = int(audio_file.samplerate)
        start_frame = round(window.review_start_seconds * sample_rate)
        frame_count = max(1, round(window.review_duration_seconds * sample_rate))
        audio_file.seek(start_frame)
        samples = audio_file.read(frame_count, dtype="float32", always_2d=True)

    mono = np.mean(samples, axis=1, dtype=np.float64)
    if mono.size < 32:
        raise ValueError("El tramo de audio es demasiado corto para revisarlo")
    if not np.isfinite(mono).all():
        raise ValueError("El tramo de audio contiene valores no validos")

    return mono - np.mean(mono), sample_rate


def _apply_high_pass(
    samples: np.ndarray,
    sample_rate: int,
    cutoff_hz: float = REVIEW_HIGH_PASS_HZ,
) -> np.ndarray:
    nyquist = sample_rate / 2.0
    cutoff = min(float(cutoff_hz), nyquist * 0.8)
    if cutoff <= 0:
        return samples.copy()

    sos = signal.butter(
        6,
        cutoff,
        btype="highpass",
        fs=sample_rate,
        output="sos",
    )
    try:
        return signal.sosfiltfilt(sos, samples)
    except ValueError:
        return signal.sosfilt(sos, samples)


def _apply_bird_band(
    samples: np.ndarray,
    sample_rate: int,
) -> np.ndarray:
    nyquist = sample_rate / 2.0
    upper = min(REVIEW_MAX_FREQUENCY_HZ, nyquist * 0.95)
    lower = min(REVIEW_BIRD_BAND_MIN_HZ, upper * 0.8)
    if upper <= lower:
        return _apply_high_pass(samples, sample_rate, lower)

    sos = signal.butter(
        4,
        [lower, upper],
        btype="bandpass",
        fs=sample_rate,
        output="sos",
    )
    try:
        return signal.sosfiltfilt(sos, samples)
    except ValueError:
        return signal.sosfilt(sos, samples)


def _rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


def _db_ratio(numerator: float, denominator: float) -> float:
    epsilon = np.finfo(float).tiny
    return float(20.0 * np.log10(max(numerator, epsilon) / max(denominator, epsilon)))


def _mains_hum_prominence_db(
    frequencies: np.ndarray,
    power: np.ndarray,
) -> float:
    prominences = []
    for target_hz in (50.0, 100.0, 150.0, 200.0):
        target_index = int(np.argmin(np.abs(frequencies - target_hz)))
        neighborhood = (
            (frequencies >= target_hz - 4.0)
            & (frequencies <= target_hz + 4.0)
            & (np.abs(frequencies - target_hz) >= 1.0)
        )
        if not np.any(neighborhood):
            continue

        local_median = float(np.median(power[neighborhood]))
        ratio = max(
            float(power[target_index]) / max(local_median, np.finfo(float).tiny),
            np.finfo(float).tiny,
        )
        prominences.append(10.0 * np.log10(ratio))

    return float(max(prominences, default=0.0))


def analyze_review_audio(
    audio_path: Path,
    window: ReviewWindow,
) -> ReviewAudioDiagnostics:
    samples, sample_rate = _read_review_audio(audio_path, window)
    frequencies, power = signal.welch(
        samples,
        fs=sample_rate,
        window="hann",
        nperseg=min(131072, samples.size),
        scaling="density",
    )

    audible = frequencies <= min(REVIEW_MAX_FREQUENCY_HZ, sample_rate / 2.0)
    low = frequencies <= min(200.0, sample_rate / 2.0)
    audible_power = float(np.sum(power[audible]))
    low_frequency_ratio = (
        float(np.sum(power[low]) / audible_power)
        if audible_power > 0
        else 0.0
    )
    hum_prominence_db = _mains_hum_prominence_db(frequencies, power)

    bird_band_snr_db = None
    if (
        window.timing_available
        and window.audio_start_seconds is not None
        and window.audio_end_seconds is not None
    ):
        filtered = _apply_bird_band(samples, sample_rate)
        relative_start = window.audio_start_seconds - window.review_start_seconds
        relative_end = window.audio_end_seconds - window.review_start_seconds
        event_start = max(0, round(relative_start * sample_rate))
        event_end = min(filtered.size, round(relative_end * sample_rate))
        margin = round(sample_rate)
        background_mask = np.ones(filtered.size, dtype=bool)
        background_mask[
            max(0, event_start - margin):min(filtered.size, event_end + margin)
        ] = False
        event = filtered[event_start:event_end]
        background = filtered[background_mask]
        if event.size and background.size:
            bird_band_snr_db = _db_ratio(_rms(event), _rms(background))

    warnings = []
    if low_frequency_ratio >= 0.55:
        warnings.append("low_frequency_noise")
    if hum_prominence_db >= 10.0:
        warnings.append("mains_hum")
    if bird_band_snr_db is not None and bird_band_snr_db < 3.0:
        warnings.append("weak_bird_evidence")

    if "weak_bird_evidence" in warnings and (
        "low_frequency_noise" in warnings or "mains_hum" in warnings
    ):
        summary = (
            "El fondo grave o electrico domina y la ventana marcada por BirdNET "
            "apenas sobresale. Conviene revisar la deteccion antes de validarla."
        )
    elif "weak_bird_evidence" in warnings:
        summary = (
            "La ventana marcada por BirdNET tiene poco contraste energetico "
            "frente al fondo. Conviene escucharla antes de validarla."
        )
    elif "low_frequency_noise" in warnings or "mains_hum" in warnings:
        summary = (
            "Se detecta ruido grave o zumbido electrico, pero la evidencia del "
            "evento conserva contraste suficiente."
        )
    else:
        summary = "La captura no presenta avisos acusticos relevantes para la revision."

    return ReviewAudioDiagnostics(
        status="review" if warnings else "ok",
        summary=summary,
        warnings=warnings,
        low_frequency_ratio=low_frequency_ratio,
        mains_hum_prominence_db=hum_prominence_db,
        bird_band_snr_db=bird_band_snr_db,
        high_pass_hz=REVIEW_HIGH_PASS_HZ,
    )


def build_review_window(
    audio_duration_seconds: float,
    audio_start_seconds: float | None,
    audio_end_seconds: float | None,
) -> ReviewWindow:
    duration = max(0.0, float(audio_duration_seconds))
    window_duration = min(REVIEW_WINDOW_SECONDS, duration)

    timing_available = (
        audio_start_seconds is not None
        and audio_end_seconds is not None
        and np.isfinite(audio_start_seconds)
        and np.isfinite(audio_end_seconds)
        and audio_end_seconds > audio_start_seconds
        and audio_start_seconds < duration
        and audio_end_seconds > 0
    )

    marker_start = None
    marker_end = None
    review_start = 0.0

    if timing_available:
        marker_start = min(duration, max(0.0, float(audio_start_seconds)))
        marker_end = min(duration, max(marker_start, float(audio_end_seconds)))
        marker_center = (marker_start + marker_end) / 2.0
        max_start = max(0.0, duration - window_duration)
        review_start = min(max(0.0, marker_center - window_duration / 2.0), max_start)

    review_end = min(duration, review_start + window_duration)

    return ReviewWindow(
        audio_duration_seconds=duration,
        review_start_seconds=review_start,
        review_end_seconds=review_end,
        audio_start_seconds=marker_start,
        audio_end_seconds=marker_end,
        timing_available=timing_available,
    )


def get_review_spectrogram_path(
    detection_id: int,
    audio_path: Path,
    window: ReviewWindow,
) -> Path:
    REVIEW_SPECTROGRAM_DIR.mkdir(parents=True, exist_ok=True)
    source_version = audio_path.stat().st_mtime_ns
    start_ms = round(window.review_start_seconds * 1000)
    end_ms = round(window.review_end_seconds * 1000)
    cache_path = REVIEW_SPECTROGRAM_DIR / (
        f"detection_{detection_id}_v{REVIEW_RENDER_VERSION}_"
        f"{source_version}_{start_ms}_{end_ms}.png"
    )

    if cache_path.is_file():
        return cache_path

    with _SPECTROGRAM_LOCK:
        if cache_path.is_file():
            return cache_path

        temporary_path = cache_path.with_name(f".{cache_path.name}.tmp")
        try:
            _render_spectrogram(audio_path, window, temporary_path)
            temporary_path.replace(cache_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    return cache_path


def _render_spectrogram(
    audio_path: Path,
    window: ReviewWindow,
    output_path: Path,
) -> None:
    mono, sample_rate = _read_review_audio(audio_path, window)
    clean = _apply_high_pass(mono, sample_rate)
    nperseg = min(2048, clean.size)
    noverlap = min(nperseg - 1, int(nperseg * 0.75))
    frequencies, times, power = signal.spectrogram(
        clean,
        fs=sample_rate,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        detrend=False,
        scaling="spectrum",
        mode="psd",
    )

    max_frequency = min(REVIEW_MAX_FREQUENCY_HZ, sample_rate / 2.0)
    min_frequency = min(REVIEW_HIGH_PASS_HZ, max_frequency * 0.8)
    visible = (frequencies >= min_frequency) & (frequencies <= max_frequency)
    frequencies = frequencies[visible]
    power = power[visible]
    power_db = 10.0 * np.log10(np.maximum(power, np.finfo(float).tiny))
    background_db = np.percentile(power_db, 25.0, axis=1, keepdims=True)
    contrast_db = np.clip(
        power_db - background_db,
        0.0,
        REVIEW_SPECTROGRAM_CONTRAST_DB,
    )

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(12, 3), dpi=100, facecolor="#160f24")
    axis = figure.add_axes([0, 0, 1, 1])
    axis.pcolormesh(
        times,
        frequencies,
        contrast_db,
        shading="auto",
        cmap="magma",
        vmin=0.0,
        vmax=REVIEW_SPECTROGRAM_CONTRAST_DB,
    )
    axis.set_xlim(0, window.review_duration_seconds)
    axis.set_ylim(min_frequency, max_frequency)
    axis.set_axis_off()
    FigureCanvasAgg(figure).print_png(str(output_path))