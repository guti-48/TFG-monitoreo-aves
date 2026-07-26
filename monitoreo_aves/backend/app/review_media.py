from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import numpy as np
import soundfile as sf
from scipy import ndimage, signal

from .config import SERVER_AUDIO_DIR, SPECTOGRAM_DIR


REVIEW_WINDOW_SECONDS = 20.0
REVIEW_SPECTROGRAM_DIR = SPECTOGRAM_DIR / "review_segments"
REVIEW_AUDIO_DIR = SPECTOGRAM_DIR / "review_audio"
REVIEW_RENDER_VERSION = 4
REVIEW_HIGH_PASS_HZ = 250.0
REVIEW_BIRD_BAND_MIN_HZ = 1200.0
REVIEW_MAX_FREQUENCY_HZ = 10000.0
REVIEW_LISTENING_LOW_PASS_HZ = 10000.0
REVIEW_NOISE_PERCENTILE = 20.0
REVIEW_NOISE_PROFILE_BLOCK_SECONDS = 2.0
REVIEW_NOISE_PROFILE_GLOBAL_LIMIT = 2.0
REVIEW_NOISE_REDUCTION_STRENGTH = 1.1
REVIEW_NOISE_RATIO_POWER = 2.0
REVIEW_NOISE_MINIMUM_GAIN = 0.14
REVIEW_MAINS_FREQUENCY_HZ = 50.0
REVIEW_MAINS_MAX_HZ = 500.0
REVIEW_MAINS_SEARCH_HALF_WIDTH_HZ = 1.5
REVIEW_MAINS_NEIGHBOR_MIN_HZ = 3.0
REVIEW_MAINS_NEIGHBOR_MAX_HZ = 10.0
REVIEW_MAINS_MIN_PROMINENCE_DB = 7.0
REVIEW_MAINS_MIN_REFERENCE_POWER_RATIO = 0.0001
REVIEW_MAINS_FRAME_PROMINENCE_DB = 5.0
REVIEW_MAINS_MIN_PERSISTENCE = 0.6
REVIEW_MAINS_NOTCH_BANDWIDTH_HZ = 7.0
REVIEW_MAX_LISTENING_GAIN = 48.0
REVIEW_TARGET_REFERENCE_PEAK = 0.72
REVIEW_OUTPUT_PEAK_LIMIT = 0.95
REVIEW_SPECTROGRAM_CONTRAST_DB = 24.0
_SPECTROGRAM_LOCK = Lock()
_AUDIO_LOCK = Lock()


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


def _apply_low_pass(
    samples: np.ndarray,
    sample_rate: int,
    cutoff_hz: float = REVIEW_LISTENING_LOW_PASS_HZ,
) -> np.ndarray:
    nyquist = sample_rate / 2.0
    cutoff = min(float(cutoff_hz), nyquist * 0.95)
    if cutoff <= 0 or cutoff >= nyquist:
        return samples.copy()

    sos = signal.butter(
        6,
        cutoff,
        btype="lowpass",
        fs=sample_rate,
        output="sos",
    )
    try:
        return signal.sosfiltfilt(sos, samples)
    except ValueError:
        return signal.sosfilt(sos, samples)


def _detect_mains_harmonics(
    samples: np.ndarray,
    sample_rate: int,
) -> list[float]:
    """
    Localiza solo armónicos de red que sobresalen de su vecindad espectral.

    El filtrado selectivo evita abrir muescas innecesarias en frecuencias
    donde podría haber componentes reales de las vocalizaciones.
    """
    if samples.size < 32:
        return []

    frequencies, power = signal.welch(
        samples,
        fs=sample_rate,
        window="hann",
        nperseg=min(65536, samples.size),
        scaling="density",
    )
    if _mains_hum_prominence_db(frequencies, power) < 10.0:
        return []

    reference_hum = np.zeros_like(frequencies, dtype=bool)
    for reference_hz in (50.0, 100.0, 150.0, 200.0):
        reference_hum |= (
            np.abs(frequencies - reference_hz)
            <= REVIEW_MAINS_SEARCH_HALF_WIDTH_HZ
        )
    total_power = max(float(np.sum(power)), np.finfo(float).tiny)
    reference_power_ratio = (
        float(np.sum(power[reference_hum])) / total_power
    )
    if reference_power_ratio < REVIEW_MAINS_MIN_REFERENCE_POWER_RATIO:
        return []

    frame_size = min(sample_rate, samples.size)
    frame_overlap = min(frame_size - 1, frame_size // 2)
    frame_frequencies, _, frame_power = signal.spectrogram(
        samples,
        fs=sample_rate,
        window="hann",
        nperseg=frame_size,
        noverlap=frame_overlap,
        detrend=False,
        scaling="density",
        mode="psd",
    )

    nyquist = sample_rate / 2.0
    first_harmonic = (
        np.ceil(REVIEW_HIGH_PASS_HZ / REVIEW_MAINS_FREQUENCY_HZ)
        * REVIEW_MAINS_FREQUENCY_HZ
    )
    last_harmonic = min(REVIEW_MAINS_MAX_HZ, nyquist * 0.9)
    if first_harmonic > last_harmonic:
        return []

    detected = []
    targets = np.arange(
        first_harmonic,
        last_harmonic + REVIEW_MAINS_FREQUENCY_HZ / 2.0,
        REVIEW_MAINS_FREQUENCY_HZ,
    )
    epsilon = np.finfo(float).tiny

    for target_hz in targets:
        distance = np.abs(frequencies - target_hz)
        target_band = distance <= REVIEW_MAINS_SEARCH_HALF_WIDTH_HZ
        neighborhood = (
            (distance >= REVIEW_MAINS_NEIGHBOR_MIN_HZ)
            & (distance <= REVIEW_MAINS_NEIGHBOR_MAX_HZ)
        )
        if not np.any(target_band) or not np.any(neighborhood):
            continue

        target_indices = np.flatnonzero(target_band)
        peak_index = target_indices[np.argmax(power[target_band])]
        peak_power = max(float(power[peak_index]), epsilon)
        local_median = max(float(np.median(power[neighborhood])), epsilon)
        prominence_db = 10.0 * np.log10(peak_power / local_median)
        if prominence_db < REVIEW_MAINS_MIN_PROMINENCE_DB:
            continue

        peak_frequency = float(frequencies[peak_index])
        frame_distance = np.abs(frame_frequencies - peak_frequency)
        frame_target = (
            frame_distance <= REVIEW_MAINS_SEARCH_HALF_WIDTH_HZ
        )
        frame_neighbors = (
            (frame_distance >= REVIEW_MAINS_NEIGHBOR_MIN_HZ)
            & (frame_distance <= REVIEW_MAINS_NEIGHBOR_MAX_HZ)
        )
        if not np.any(frame_target) or not np.any(frame_neighbors):
            continue

        target_over_time = np.max(frame_power[frame_target], axis=0)
        neighborhood_over_time = np.median(
            frame_power[frame_neighbors],
            axis=0,
        )
        frame_prominence_db = 10.0 * np.log10(
            np.maximum(target_over_time, epsilon)
            / np.maximum(neighborhood_over_time, epsilon)
        )
        persistence = float(
            np.mean(
                frame_prominence_db
                >= REVIEW_MAINS_FRAME_PROMINENCE_DB
            )
        )
        if persistence >= REVIEW_MAINS_MIN_PERSISTENCE:
            detected.append(peak_frequency)

    return detected


def _apply_mains_notches(
    samples: np.ndarray,
    sample_rate: int,
    frequencies: list[float],
) -> np.ndarray:
    clean = samples.copy()
    for frequency_hz in frequencies:
        quality = (
            frequency_hz / REVIEW_MAINS_NOTCH_BANDWIDTH_HZ
        )
        numerator, denominator = signal.iirnotch(
            frequency_hz,
            quality,
            fs=sample_rate,
        )
        sos = signal.tf2sos(numerator, denominator)
        try:
            clean = signal.sosfiltfilt(sos, clean)
        except ValueError:
            clean = signal.sosfilt(sos, clean)
    return clean


def _reduce_adaptive_noise(
    samples: np.ndarray,
    sample_rate: int,
) -> np.ndarray:
    """
    Atenua el fondo mediante perfiles espectrales locales interpolados.

    El perfil se actualiza por bloques para seguir variaciones lentas de viento
    y ruido mecánico. Se conserva una fracción del fondo y se suaviza la
    máscara para evitar el sonido metálico de una puerta de ruido agresiva.
    Esta función solo se usa en la copia de escucha humana.
    """
    nperseg = min(2048, samples.size)
    if nperseg < 32:
        return samples.copy()

    noverlap = min(nperseg - 1, round(nperseg * 0.75))
    _, times, spectrum = signal.stft(
        samples,
        fs=sample_rate,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        boundary="zeros",
        padded=True,
    )
    magnitude = np.abs(spectrum)

    block_count = max(
        1,
        int(
            np.ceil(
                times[-1] / REVIEW_NOISE_PROFILE_BLOCK_SECONDS
            )
        ),
    )
    block_edges = np.linspace(0.0, times[-1], block_count + 1)
    block_centers = (block_edges[:-1] + block_edges[1:]) / 2.0
    block_profiles = []
    for block_index in range(block_count):
        in_block = (
            (times >= block_edges[block_index])
            & (
                (times < block_edges[block_index + 1])
                | (block_index == block_count - 1)
            )
        )
        block_profiles.append(
            np.percentile(
                magnitude[:, in_block],
                REVIEW_NOISE_PERCENTILE,
                axis=1,
            )
        )
    block_profiles = np.stack(block_profiles, axis=1)

    right_profile = np.searchsorted(block_centers, times, side="right")
    right_profile = np.clip(right_profile, 0, block_count - 1)
    left_profile = np.clip(right_profile - 1, 0, block_count - 1)
    interpolation_width = (
        block_centers[right_profile] - block_centers[left_profile]
    )
    interpolation = np.divide(
        times - block_centers[left_profile],
        interpolation_width,
        out=np.zeros_like(times),
        where=interpolation_width > 0,
    )
    interpolation = np.clip(interpolation, 0.0, 1.0)
    noise_profile = (
        block_profiles[:, left_profile] * (1.0 - interpolation)[None, :]
        + block_profiles[:, right_profile] * interpolation[None, :]
    )
    global_profile = np.percentile(
        magnitude,
        REVIEW_NOISE_PERCENTILE,
        axis=1,
        keepdims=True,
    )
    noise_profile = np.minimum(
        noise_profile,
        global_profile * REVIEW_NOISE_PROFILE_GLOBAL_LIMIT,
    )

    epsilon = np.finfo(float).eps
    noise_ratio = noise_profile / np.maximum(magnitude, epsilon)
    gain = 1.0 - (
        REVIEW_NOISE_REDUCTION_STRENGTH
        * np.power(noise_ratio, REVIEW_NOISE_RATIO_POWER)
    )
    gain = np.clip(gain, REVIEW_NOISE_MINIMUM_GAIN, 1.0)

    # Expande ligeramente los eventos transitorios antes de suavizar la
    # mascara: así se conservan mejor sílabas y ataques breves de las aves.
    gain = ndimage.maximum_filter(gain, size=(3, 3), mode="nearest")
    gain = ndimage.gaussian_filter(
        gain,
        sigma=(0.7, 1.0),
        mode="nearest",
    )

    _, reduced = signal.istft(
        spectrum * gain,
        fs=sample_rate,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        input_onesided=True,
        boundary=True,
    )
    if reduced.size < samples.size:
        reduced = np.pad(reduced, (0, samples.size - reduced.size))
    return reduced[:samples.size]


def _normalize_review_audio(samples: np.ndarray) -> np.ndarray:
    absolute = np.abs(samples)
    reference_peak = float(np.percentile(absolute, 99.9))
    absolute_peak = float(np.max(absolute, initial=0.0))
    epsilon = np.finfo(float).eps

    if reference_peak <= epsilon or absolute_peak <= epsilon:
        return np.zeros_like(samples, dtype=np.float64)

    gain_for_reference = REVIEW_TARGET_REFERENCE_PEAK / reference_peak
    gain_for_peak = REVIEW_OUTPUT_PEAK_LIMIT / absolute_peak
    gain = min(
        REVIEW_MAX_LISTENING_GAIN,
        gain_for_reference,
        gain_for_peak,
    )
    return samples * max(0.0, gain)


def enhance_review_audio(
    samples: np.ndarray,
    sample_rate: int,
) -> np.ndarray:
    """
    Genera una copia más clara y audible para la revisión humana.

    No se invoca en la inferencia de BirdNET ni modifica el WAV original.
    """
    hum_frequencies = _detect_mains_harmonics(samples, sample_rate)
    clean = _apply_high_pass(samples, sample_rate)
    clean = _apply_mains_notches(clean, sample_rate, hum_frequencies)
    clean = _apply_low_pass(clean, sample_rate)
    clean = _reduce_adaptive_noise(clean, sample_rate)
    clean = _normalize_review_audio(clean)
    return np.clip(
        clean,
        -REVIEW_OUTPUT_PEAK_LIMIT,
        REVIEW_OUTPUT_PEAK_LIMIT,
    ).astype(np.float32)


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


def get_clean_review_audio_path(
    detection_id: int,
    audio_path: Path,
    window: ReviewWindow,
) -> Path:
    REVIEW_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    source_version = audio_path.stat().st_mtime_ns
    start_ms = round(window.review_start_seconds * 1000)
    end_ms = round(window.review_end_seconds * 1000)
    cache_path = REVIEW_AUDIO_DIR / (
        f"detection_{detection_id}_v{REVIEW_RENDER_VERSION}_"
        f"{source_version}_{start_ms}_{end_ms}_clean.wav"
    )

    if cache_path.is_file():
        return cache_path

    with _AUDIO_LOCK:
        if cache_path.is_file():
            return cache_path

        samples, sample_rate = _read_review_audio(audio_path, window)
        clean = enhance_review_audio(samples, sample_rate)

        temporary_path = cache_path.with_name(f".{cache_path.name}.tmp.wav")
        try:
            sf.write(str(temporary_path), clean, sample_rate, subtype="PCM_16")
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