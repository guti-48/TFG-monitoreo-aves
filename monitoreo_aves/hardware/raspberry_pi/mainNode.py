import os, time, librosa
import numpy as np
import sounddevice as sd
import soundfile as sf
import librosa.display
import matplotlib.pyplot as plt
from datetime import datetime

#### CONFIGURACION ####

SAMPLE_RATE = 48000 # Frecuencia que suele usar birdNet
DURATION = 10  # Duracion de la grabacion en segundos
OUTPUT_FOLDER_AUDIO = "records"
OUTPUT_FOLDER_IMG = "spectrograms"

# Aqui lo que haremos sera un check para ver que existen las carpetas
os.makedirs(OUTPUT_FOLDER_AUDIO, exist_ok=True)
os.makedirs(OUTPUT_FOLDER_IMG, exist_ok=True)

def grabacionAudio(duration, fs):
    """
    Esta funcion grabara el audio del microfono por defecto durante X segundos a una frecuencia fs
    Se devolvera los datos del audio como un array de numpy aplanado. (juntamos dos canales en uno por vector)
    """
    print(f"Grabando audio durante {duration} segundos...")
    grab = sd.rec(int(duration * fs), samplerate=fs, channels=1)
    sd.wait()
    print("Grabacion finalizada")
    return grab.flatten()

def guardoWAV(audio_data, fs, filename):
    """
    Con esta funcion lo que voy ha hacer será guardar el array de audio como archivo .WAV
    """
    path = os.path.join(OUTPUT_FOLDER_AUDIO, filename)
    sf.write(path, audio_data, fs)
    print(f"Archivo de audio guardado en: {path}")
    return path

def generacionEspectograma(audio_path, filename):
    """
    Generaremos un MEl-Spectogram usando librosa y luego lo guardaremos como imagen
    """
    # Cargamos el audio con librosa
    y, sr = librosa.load(audio_path, sr = None)

    # Creamos el espectograma de Mel
    S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128, fmax=10000)
    S_db = librosa.power_to_db(S, ref=np.max)

    # Plot del espectrograma
    plt.figure(figsize=(10, 4))
    librosa.display.specshow(S_db, sr=sr, x_axis='time', y_axis='mel', fmax=10000)
    plt.colorbar(format='%+2.0f db')
    plt.title(f"Espectograma - {filename}")
    plt.tight_layout()

    img_path = os.path.join(OUTPUT_FOLDER_IMG, f"{filename}.png")
    plt.savefig(img_path)
    plt.close()
    print(f"Espectrograma guardado en: {img_path}")

### Flujo de trabajo principal ###
if __name__ == "__main__":
    try:
        # Aqui para cada grabacion lo correcto es generar un nombre unico con la fecha y hora de grabacion
        timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        filename = f"record_{timestamp}"
        filenameWAV = f"{filename}.wav"

        # 1. Grabaremos el audio
        audio_data = grabacionAudio(DURATION, SAMPLE_RATE)

        # 2. Guardamos el audio como archivo WAV
        audio_path = guardoWAV(audio_data, SAMPLE_RATE, filenameWAV)

        # 3. Generaremos un espectograma
        generacionEspectograma(audio_path, filename)
        print("Proceso completado, revisa las carpetas de salida.")

    except KeyboardInterrupt:
        print("\nPrograma interrumpido")
    except Exception as e:
        print(f"\nOcurrio un error: {e}")