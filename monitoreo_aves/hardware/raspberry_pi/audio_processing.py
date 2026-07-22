import os
import re
import shutil
import subprocess
import sys

import matplotlib

matplotlib.use("Agg")

import librosa
import librosa.display
import numpy as np
import sounddevice as sd
import soundfile as sf

from node_config import (
    MIC_CLIPPING_LEVEL,
    MIC_ALSA_CARD,
    MIC_AUTO_GAIN,
    MIC_CAPTURE_VOLUME,
    MIC_DEVICE,
    MIC_MAX_CLIPPING_RATIO,
    MIC_MAX_DC_OFFSET,
    MIC_MIN_RMS,
    OUTPUT_FOLDER_AUDIO,
    OUTPUT_FOLDER_IMG,
)

import matplotlib.pyplot as plt


def configurarGananciaMicrofono():
    """Aplica ganancia ALSA fija cuando el nodo la configura explicitamente."""
    if not any((MIC_ALSA_CARD, MIC_CAPTURE_VOLUME, MIC_AUTO_GAIN)):
        return False

    if not sys.platform.startswith("linux"):
        print("[WARN] La ganancia ALSA solo esta disponible en Linux.")
        return False
    if not MIC_ALSA_CARD.isdigit():
        print("[WARN] BIRDMONITOR_MIC_ALSA_CARD debe ser un numero de tarjeta ALSA.")
        return False
    if shutil.which("amixer") is None:
        print("[WARN] No se encontro amixer; no se pudo fijar la ganancia del microfono.")
        return False

    commands = []
    if MIC_CAPTURE_VOLUME:
        match = re.fullmatch(r"(\d{1,3})%", MIC_CAPTURE_VOLUME)
        if match is None or not 0 <= int(match.group(1)) <= 100:
            print(
                "[WARN] BIRDMONITOR_MIC_CAPTURE_VOLUME debe ser un porcentaje "
                "entre 0% y 100%."
            )
            return False
        commands.append(["sset", "Mic", MIC_CAPTURE_VOLUME, "cap"])

    if MIC_AUTO_GAIN:
        if MIC_AUTO_GAIN in {"1", "true", "on", "yes"}:
            agc_value = "on"
        elif MIC_AUTO_GAIN in {"0", "false", "off", "no"}:
            agc_value = "off"
        else:
            print("[WARN] BIRDMONITOR_MIC_AUTO_GAIN debe ser 0/1 u off/on.")
            return False
        commands.append(["sset", "Auto Gain Control", agc_value])

    try:
        for command in commands:
            subprocess.run(
                ["amixer", "-c", MIC_ALSA_CARD, *command],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"[WARN] No se pudo configurar la ganancia ALSA: {exc}")
        return False

    print(
        "Ganancia ALSA aplicada: "
        f"tarjeta={MIC_ALSA_CARD}, volumen={MIC_CAPTURE_VOLUME or 'sin cambio'}, "
        f"AGC={MIC_AUTO_GAIN or 'sin cambio'}."
    )
    return True


def listarDispositivosAudio():
    """Muestra los dispositivos de audio disponibles en la Raspberry."""
    try:
        dispositivos = sd.query_devices()
        print("\nDispositivos de audio detectados:")
        for idx, dev in enumerate(dispositivos):
            entradas = dev.get("max_input_channels", 0)
            salidas = dev.get("max_output_channels", 0)
            print(f"  [{idx}] {dev['name']} | entradas={entradas} | salidas={salidas}")
        print("")
    except Exception as e:
        print(f"No se pudieron listar dispositivos de audio: {e}")


def resolverDispositivoEntrada():
    """
    Devuelve el indice del microfono de entrada.
    Si BIRDMONITOR_MIC_DEVICE esta definido, intenta usarlo.
    """
    try:
        dispositivos = sd.query_devices()
    except Exception as e:
        print(f"No se pudo consultar PortAudio/sounddevice: {e}")
        return None

    if MIC_DEVICE:
        try:
            idx = int(MIC_DEVICE)
            if idx < 0 or idx >= len(dispositivos):
                print(f"BIRDMONITOR_MIC_DEVICE={idx} fuera de rango.")
                return None

            if dispositivos[idx].get("max_input_channels", 0) <= 0:
                print(f"El dispositivo {idx} no tiene canales de entrada.")
                return None

            print(f"Microfono seleccionado por entorno: [{idx}] {dispositivos[idx]['name']}")
            return idx

        except ValueError:
            print("BIRDMONITOR_MIC_DEVICE debe ser un indice numerico, por ejemplo 1 o 2.")
            return None

    try:
        default_input = sd.default.device[0]

        if default_input is not None and default_input >= 0:
            dev = dispositivos[default_input]
            if dev.get("max_input_channels", 0) > 0:
                print(f"Microfono por defecto: [{default_input}] {dev['name']}")
                return default_input
    except Exception:
        pass

    for idx, dev in enumerate(dispositivos):
        if dev.get("max_input_channels", 0) > 0:
            print(f"Microfono encontrado automaticamente: [{idx}] {dev['name']}")
            return idx

    print("No se ha detectado ningun microfono de entrada.")
    return None


def obtenerNombreDispositivoEntrada(device_index):
    """Devuelve un identificador legible del microfono sin interrumpir el ciclo."""
    if device_index is None:
        return None

    try:
        dispositivo = sd.query_devices(device_index)
        nombre = str(dispositivo.get("name", "")).strip()
        return nombre or f"device-{device_index}"
    except Exception:
        return f"device-{device_index}"


def analizarCalidadAudio(
    audio_data,
    fs,
    min_rms=MIC_MIN_RMS,
    clipping_level=MIC_CLIPPING_LEVEL,
    max_clipping_ratio=MIC_MAX_CLIPPING_RATIO,
    max_dc_offset=MIC_MAX_DC_OFFSET,
):
    """
    Calcula indicadores baratos de salud del microfono.

    No filtra ni normaliza la senal: BirdNET recibe el audio original y las
    metricas permiten detectar configuraciones con poco nivel, saturacion o
    desplazamiento DC sin alterar la comparabilidad de las grabaciones.
    """
    audio = np.asarray(audio_data, dtype=np.float32).reshape(-1)
    if audio.size == 0:
        raise ValueError("No se puede diagnosticar una grabacion vacia.")
    if not np.isfinite(audio).all():
        raise ValueError("No se puede diagnosticar audio con NaN o Inf.")

    abs_audio = np.abs(audio)
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
    peak = float(np.max(abs_audio))
    dc_offset = float(np.mean(audio, dtype=np.float64))
    clipping_ratio = float(np.mean(abs_audio >= clipping_level))

    # El percentil 20 del RMS de ventanas de 50 ms aproxima el suelo de ruido
    # sin interpretar los cantos puntuales como ruido permanente.
    frame_samples = max(1, int(fs * 0.05))
    usable_samples = (audio.size // frame_samples) * frame_samples
    if usable_samples:
        frames = audio[:usable_samples].reshape(-1, frame_samples)
        frame_rms = np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1))
        noise_floor_rms = float(np.percentile(frame_rms, 20))
    else:
        noise_floor_rms = rms

    warnings = []
    if rms < min_rms:
        warnings.append("low_signal")
    if clipping_ratio > max_clipping_ratio:
        warnings.append("clipping")
    if abs(dc_offset) > max_dc_offset:
        warnings.append("dc_offset")

    status = "ok" if not warnings else "+".join(warnings)
    warning_labels = {
        "low_signal": "nivel de senal bajo",
        "clipping": "muestras saturadas",
        "dc_offset": "desplazamiento DC elevado",
    }
    detail = (
        "Captura dentro de los limites configurados."
        if not warnings
        else "Revisar microfono: "
        + ", ".join(warning_labels[warning] for warning in warnings)
    )

    return {
        "rms": rms,
        "peak": peak,
        "clipping_ratio": clipping_ratio,
        "dc_offset": dc_offset,
        "noise_floor_rms": noise_floor_rms,
        "quality_status": status,
        "quality_detail": detail,
    }


def mostrarDiagnosticoAudio(calidad):
    """Escribe un resumen compacto y un aviso accionable si hay problemas."""
    print(
        "Calidad de audio: "
        f"RMS={calidad['rms']:.5f}, pico={calidad['peak']:.3f}, "
        f"clipping={calidad['clipping_ratio'] * 100:.3f}%, "
        f"DC={calidad['dc_offset']:.5f}, estado={calidad['quality_status']}"
    )
    if calidad["quality_status"] != "ok":
        print(f"[WARN] {calidad['quality_detail']}")


def grabacionAudio(duration, fs, device_index):
    """
    Graba audio mono durante `duration` segundos a frecuencia `fs`.
    Con 60s BirdNET analiza ~40 ventanas solapadas.
    """
    if device_index is None:
        raise RuntimeError("No hay microfono de entrada disponible.")

    try:
        print(f"Grabando audio durante {duration} segundos con dispositivo [{device_index}]...")
        grab = sd.rec(
            int(duration * fs),
            samplerate=fs,
            channels=1,
            dtype="float32",
            device=device_index,
        )
        sd.wait()

        audio = grab.flatten()

        if audio.size == 0:
            raise RuntimeError("La grabacion ha devuelto un array vacio.")

        if not np.isfinite(audio).all():
            raise RuntimeError("La grabacion contiene valores no validos: NaN o Inf.")

        print("Grabacion finalizada.")
        return audio

    except Exception as e:
        raise RuntimeError(f"Error durante la grabacion de audio: {e}") from e


def guardoWAV(audio_data, fs, filename):
    """Guarda el array de audio como archivo WAV y devuelve la ruta."""
    path = os.path.join(OUTPUT_FOLDER_AUDIO, filename)
    sf.write(path, audio_data, fs)
    print(f"Archivo de audio guardado en: {path}")
    return path


def generacionEspectograma(audio_path, filename):
    """Genera y guarda un espectrograma Mel como imagen PNG."""
    y, sr = librosa.load(audio_path, sr=None)
    s = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128, fmax=10000)
    s_db = librosa.power_to_db(s, ref=np.max)

    plt.figure(figsize=(10, 4))
    librosa.display.specshow(s_db, sr=sr, x_axis="time", y_axis="mel", fmax=10000)
    plt.colorbar(format="%+2.0f db")
    plt.title(f"Espectograma - {filename}")
    plt.tight_layout()

    img_path = os.path.join(OUTPUT_FOLDER_IMG, f"{filename}.png")
    plt.savefig(img_path)
    plt.close()
    print(f"Espectrograma guardado en: {img_path}")


def calcularMetricasAcusticas(audio_path):
    """
    Calcula indices acusticos del paisaje sonoro para una grabacion WAV.
    Se ejecuta en el nodo Edge y no requiere subir el audio bruto para el analisis cientifico.
    """
    try:
        from maad import features, sound

        s, fs = sound.load(audio_path)
        sxx, tn, fn, ext = sound.spectrogram(s, fs)

        _, _, aci = features.acoustic_complexity_index(sxx)
        aci_val = float(np.sum(aci))

        adi_val = float(features.acoustic_diversity_index(sxx, fn))

        try:
            aei_val = float(features.acoustic_evenness_index(sxx, fn))
        except AttributeError:
            aei_val = float(1.0 - (adi_val / 3.0)) if not np.isnan(adi_val) else 0.5

        try:
            bio_val = float(features.bioacoustics_index(sxx, fn))
        except AttributeError:
            bio_val = float(features.bioacoustic_index(sxx, fn))

        ndsi_val, _, _, _ = features.soundscape_index(sxx, fn)
        ndsi_val = float(ndsi_val)

        e_t = np.sum(sxx, axis=0)
        if np.sum(e_t) > 0:
            p_i = e_t / np.sum(e_t)
            ht_val = float(-np.sum(p_i * np.log(p_i + 1e-12)) / np.log(len(p_i)))
        else:
            ht_val = 0.0

        e_f = np.sum(sxx, axis=1)
        if np.sum(e_f) > 0:
            p_j = e_f / np.sum(e_f)
            hf_val = float(-np.sum(p_j * np.log(p_j + 1e-12)) / np.log(len(p_j)))
        else:
            hf_val = 0.0

        h_val = float(ht_val * hf_val)

        metricas = {
            "aci": 0.0 if np.isnan(aci_val) else aci_val,
            "adi": 0.0 if np.isnan(adi_val) else adi_val,
            "aei": 0.0 if np.isnan(aei_val) else aei_val,
            "bio": 0.0 if np.isnan(bio_val) else bio_val,
            "ndsi": 0.0 if np.isnan(ndsi_val) else ndsi_val,
            "ht": 0.0 if np.isnan(ht_val) else ht_val,
            "hf": 0.0 if np.isnan(hf_val) else hf_val,
            "h": 0.0 if np.isnan(h_val) else h_val,
        }

        print(
            "Metricas acusticas calculadas: "
            f"ACI={metricas['aci']:.2f}, ADI={metricas['adi']:.2f}, "
            f"AEI={metricas['aei']:.2f}, BIO={metricas['bio']:.2f}, "
            f"NDSI={metricas['ndsi']:.2f}, H={metricas['h']:.3f}"
        )
        return metricas

    except ImportError:
        print("No se pudo calcular metricas acusticas: falta instalar scikit-maad en birdnet-env.")
        return None
    except Exception as e:
        print(f"Error calculando metricas acusticas: {e}")
        return None