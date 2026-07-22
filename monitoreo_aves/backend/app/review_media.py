from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import numpy as np
import soundfile as sf
from scipy import signal

from .config import SERVER_AUDIO_DIR, SPECTOGRAM_DIR


REVIEW_WINDOW_SECONDS = 20.0
REVIEW_SPECTROGRAM_DIR = SPECTOGRAM_DIR / "review_segments"
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


def resolve_audio_path(filename: str) -> Path:
    safe_name = Path(filename or "").name
    if not safe_name:
        raise FileNotFoundError("La deteccion no tiene un archivo WAV asociado")

    if Path(safe_name).suffix.lower() != ".wav":
        safe_name = f"{Path(safe_name).stem}.wav"

    audio_dir = SERVER_AUDIO_DIR.resolve()
    audio_path = (audio_dir / safe_name).resolve()

    try:
        audio_path.relative_to(audio_dir)
    except ValueError as exc:
        raise FileNotFoundError("Ruta de audio no permitida") from exc

    if not audio_path.is_file():
        raise FileNotFoundError(f"No se encontro el audio {safe_name}")

    return audio_path


def get_audio_duration(audio_path: Path) -> float:
    info = sf.info(str(audio_path))
    duration = float(info.frames) / float(info.samplerate)
    if duration <= 0:
        raise ValueError("El archivo WAV no contiene audio")
    return duration


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
        f"detection_{detection_id}_{source_version}_{start_ms}_{end_ms}.png"
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
    with sf.SoundFile(str(audio_path)) as audio_file:
        sample_rate = int(audio_file.samplerate)
        start_frame = round(window.review_start_seconds * sample_rate)
        frame_count = max(1, round(window.review_duration_seconds * sample_rate))
        audio_file.seek(start_frame)
        samples = audio_file.read(frame_count, dtype="float32", always_2d=True)

    mono = np.mean(samples, axis=1)
    if mono.size < 32:
        raise ValueError("El tramo de audio es demasiado corto para generar el espectrograma")

    mono = mono - np.mean(mono)
    nperseg = min(2048, mono.size)
    noverlap = min(nperseg - 1, int(nperseg * 0.75))
    frequencies, times, power = signal.spectrogram(
        mono,
        fs=sample_rate,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        detrend=False,
        scaling="spectrum",
        mode="psd",
    )

    max_frequency = min(10000.0, sample_rate / 2.0)
    visible = frequencies <= max_frequency
    frequencies = frequencies[visible]
    power = power[visible]
    power_db = 10.0 * np.log10(np.maximum(power, np.finfo(float).tiny))
    color_max = float(np.percentile(power_db, 99.5))
    color_min = color_max - 75.0

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(12, 3), dpi=100, facecolor="#160f24")
    axis = figure.add_axes([0, 0, 1, 1])
    axis.pcolormesh(
        times,
        frequencies,
        power_db,
        shading="auto",
        cmap="magma",
        vmin=color_min,
        vmax=color_max,
    )
    axis.set_xlim(0, window.review_duration_seconds)
    axis.set_ylim(0, max_frequency)
    axis.set_axis_off()
    FigureCanvasAgg(figure).print_png(str(output_path))