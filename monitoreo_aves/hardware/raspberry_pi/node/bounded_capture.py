"""Fresh ALSA capture process with a hard deadline."""
import math
import subprocess


def capture(duration, sample_rate, pcm="plug:micshared"):
    if not math.isfinite(duration) or not 0 < duration <= 3600:
        raise ValueError("Duracion de captura invalida")
    if not 8000 <= sample_rate <= 192000:
        raise ValueError("Frecuencia de captura invalida")
    seconds = math.ceil(duration)
    try:
        result = subprocess.run(["arecord", "-q", "-D", pcm, "-t", "raw", "-f", "S16_LE",
            "-r", str(sample_rate), "-c", "1", "-d", str(seconds)],
            capture_output=True, timeout=seconds + 15)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Captura agotada: el microfono no entrego audio a tiempo") from None
    expected = int(duration * sample_rate) * 2
    if result.returncode or len(result.stdout) < expected:
        raise RuntimeError("Captura USB incompleta; se reabrira en el siguiente ciclo")
    return result.stdout[:expected]
