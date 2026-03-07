import os, time, librosa, csv
import numpy as np
import sounddevice as sd
import soundfile as sf
import librosa.display
import matplotlib.pyplot as plt
import requests
from datetime import datetime
from analyzer import BirdAnalyzer

#### CONFIGURACION DEL NODO ####
NODE_NAME = "RaspberryPi_01"
SERVER_URL = "http://127.0.0.1:8000"

###CONFIGURACION PARA EL USO DE BIRDWEATHER####
###NODO DE ALGECIRAS
BIRDWEATHER_ID = "BgQxkL7v2DA8A3V9BwgQMwAp"
BIRDWEATHER_URL = "https://app.birdweather.com/api/v1/stations/detections"

#### CONFIGURACION AUDIO ####
SAMPLE_RATE = 48000  # Frecuencia que suele usar birdNet
DURATION    = 60     # Grabación activa por ciclo (segundos) — recomendación del profesor:
                     # ventanas más largas mejoran la precisión de ACI, ADI y NDSI
INTERVALO   = 300    # Ciclo completo en segundos (5 min).
                     # El nodo grabará 60s y esperará los 240s restantes antes del siguiente ciclo.

### UMBRALES CONFIANZA
UMBRAL_AVES       = 0.65   # Exigimos 65% para creernos que es un pájaro (evita falsos positivos)
UMBRAL_HUMANOS    = 0.35   # A la mínima que parezca voz humana (35%), lo cazamos como ruido
UMBRAL_MOTORES    = 0.40   # A la mínima que parezca motor/ruido ambiente, lo cazamos
UMBRAL_RUIDO_ALTO = 0.02   # Nivel de amplitud RMS para ruido blanco

#### RUTAS
BASER_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_FOLDER_AUDIO = os.path.join(BASER_DIR, "records")
OUTPUT_FOLDER_IMG   = os.path.join(BASER_DIR, "spectrograms")
CSV_BACKUP          = os.path.join(BASER_DIR, "backup_data.csv")

os.makedirs(OUTPUT_FOLDER_AUDIO, exist_ok=True)
os.makedirs(OUTPUT_FOLDER_IMG,   exist_ok=True)

# Se carga una única vez el modelo
brain = BirdAnalyzer()


def enviarDatosBirdWeather(species, confidence, lat, lon, timestamp):
    """Envía datos de PÁJAROS a la app BirdWeather."""
    if BIRDWEATHER_ID == "":
        return

    cleanSpecies = species.split('_')[1] if "_" in species else species

    datos_publicos = {
        "token":      BIRDWEATHER_ID,
        "timestamp":  timestamp,
        "species":    cleanSpecies,
        "confidence": confidence,
        "lat":        lat,
        "lon":        lon,
        "source":     "BirdMonitor13 Guti"
    }

    try:
        response = requests.post(BIRDWEATHER_URL, json=datos_publicos, timeout=5)
        if response.status_code == 200:
            print("Datos enviados a BirdWeather correctamente.")
        else:
            print(f"BirdWeather rechazó los datos: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error al conectar con BirdWeather: {e}")


def grabacionAudio(duration, fs):
    """
    Graba audio mono durante `duration` segundos a frecuencia `fs`.
    Con 60s BirdNET analiza ~40 ventanas solapadas → índices acústicos más precisos.
    """
    print(f"Grabando audio durante {duration} segundos...")
    grab = sd.rec(int(duration * fs), samplerate=fs, channels=1)
    sd.wait()
    print("Grabación finalizada.")
    return grab.flatten()


def guardoWAV(audio_data, fs, filename):
    """Guarda el array de audio como archivo WAV y devuelve la ruta."""
    path = os.path.join(OUTPUT_FOLDER_AUDIO, filename)
    sf.write(path, audio_data, fs)
    print(f"Archivo de audio guardado en: {path}")
    return path


def generacionEspectograma(audio_path, filename):
    """Genera y guarda un espectrograma Mel como imagen PNG."""
    y, sr = librosa.load(audio_path, sr=None)
    S     = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128, fmax=10000)
    S_db  = librosa.power_to_db(S, ref=np.max)

    plt.figure(figsize=(10, 4))
    librosa.display.specshow(S_db, sr=sr, x_axis='time', y_axis='mel', fmax=10000)
    plt.colorbar(format='%+2.0f db')
    plt.title(f"Espectograma - {filename}")
    plt.tight_layout()

    img_path = os.path.join(OUTPUT_FOLDER_IMG, f"{filename}.png")
    plt.savefig(img_path)
    plt.close()
    print(f"Espectrograma guardado en: {img_path}")


def _subir_archivos(filename_base: str) -> None:
    """Sube el WAV y el PNG asociados a `filename_base` al servidor."""
    url_archivos      = f"{SERVER_URL}/upload/"
    ruta_audio        = os.path.join(OUTPUT_FOLDER_AUDIO, f"{filename_base}.wav")
    ruta_img          = os.path.join(OUTPUT_FOLDER_IMG,   f"{filename_base}.png")
    archivos          = {}
    archivos_abiertos = []

    try:
        if os.path.exists(ruta_audio):
            f_audio = open(ruta_audio, 'rb')
            archivos['audio']  = (f"{filename_base}.wav", f_audio, 'audio/wav')
            archivos_abiertos.append(f_audio)

        if os.path.exists(ruta_img):
            f_img = open(ruta_img, 'rb')
            archivos['specto'] = (f"{filename_base}.png", f_img, 'image/png')
            archivos_abiertos.append(f_img)

        if archivos:
            r = requests.post(url_archivos, files=archivos, timeout=10)
            if r.status_code == 200:
                print(" -> Archivos subidos correctamente.")
            else:
                print(f" -> Error subiendo archivos: {r.status_code}")
    finally:
        for f in archivos_abiertos:
            f.close()


def enviarDatosServidor(species, confidence, filename, timestamp_str, amplitude):
    """Envía la detección al servidor FastAPI y sube los archivos asociados."""
    datos = {
        "species":     species,
        "confidence":  confidence,
        "timestamp":   timestamp_str,
        "filename":    f"{filename}.wav",
        "device_name": NODE_NAME,
        "amplitude":   float(amplitude),
    }

    try:
        r = requests.post(f"{SERVER_URL}/detections/", json=datos, timeout=5)
        if r.status_code == 200:
            _subir_archivos(filename)
            sincronizarRespaldo()
        else:
            print(f"Servidor rechazó la detección ({r.status_code}). Guardando local...")
            guardarBackupLocal(species, confidence, timestamp_str, amplitude, filename)

    except requests.exceptions.RequestException as e:
        print(f"Error de conexión: {e}. Guardando local...")
        guardarBackupLocal(species, confidence, timestamp_str, amplitude, filename)


def guardarBackupLocal(species, confidence, timestamp, amplitude, filename):
    """Guarda los datos en un CSV local si el servidor no está disponible."""
    existe = os.path.isfile(CSV_BACKUP)
    with open(CSV_BACKUP, mode='a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if not existe:
            w.writerow(['Timestamp', 'Species', 'Confidence', 'Amplitude', 'Filename'])
        w.writerow([timestamp, species, confidence, amplitude, filename])
    print(f"Datos guardados en respaldo local: {CSV_BACKUP}")


def limpiarArchivosAntiguos():
    """
    Mantiene la salud del sistema borrando archivos WAV y PNG antiguos.
    Con ciclos de 5 min se generan ~288 archivos/día — se conservan 72h.
    """
    carpetas    = [OUTPUT_FOLDER_AUDIO, OUTPUT_FOLDER_IMG]
    ahora       = time.time()
    TIEMPO_VIDA = 86400 * 3   # 3 días en segundos

    print("Iniciando limpieza de disco...")
    archivos_borrados = 0

    for carpeta in carpetas:
        for archivo in os.listdir(carpeta):
            ruta_completa = os.path.join(carpeta, archivo)
            if os.path.isfile(ruta_completa):
                if os.stat(ruta_completa).st_mtime < (ahora - TIEMPO_VIDA):
                    try:
                        os.remove(ruta_completa)
                        archivos_borrados += 1
                    except Exception as e:
                        print(f"Error borrando {archivo}: {e}")

    if archivos_borrados > 0:
        print(f"Limpieza completada: {archivos_borrados} archivos eliminados.")


def sincronizarRespaldo():
    """
    Revisa si hay datos pendientes en el CSV local y, si hay conexión,
    los sube al servidor y limpia el archivo.
    """
    if not os.path.isfile(CSV_BACKUP):
        return

    print("Intentando sincronizar datos offline con el servidor...")

    filasPendientes = []
    filasEnviadas   = 0

    try:
        with open(CSV_BACKUP, mode='r', encoding='utf-8') as f:
            filas = list(csv.reader(f))

        if not filas or len(filas) <= 1:
            return

        cabeceras = filas[0]
        datos     = filas[1:]

        for fila in datos:
            try:
                ts, sp, conf, amp, fname = fila

                datos_json = {
                    "species":     sp,
                    "confidence":  float(conf),
                    "timestamp":   ts,
                    "filename":    fname,
                    "device_name": NODE_NAME,
                    "amplitude":   float(amp)
                }

                response = requests.post(f"{SERVER_URL}/detections/", json=datos_json, timeout=5)

                if response.status_code == 200:
                    _subir_archivos(fname.replace(".wav", ""))
                    filasEnviadas += 1
                    print(f" -> Sincronizado offline: {sp} ({ts})")
                else:
                    filasPendientes.append(fila)

            except Exception as e:
                print(f"Error procesando fila de backup: {e}")
                filasPendientes.append(fila)

        if filasEnviadas > 0:
            with open(CSV_BACKUP, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(cabeceras)
                writer.writerows(filasPendientes)
            print(f"Sincronización: {filasEnviadas} recuperados, {len(filasPendientes)} pendientes.")

    except Exception as e:
        print(f"Error general de sincronización: {e}")


### Flujo de trabajo principal ###
if __name__ == "__main__":

    print("Verificando reloj interno de la Raspberry Pi...")
    while datetime.now().year < 2024:
        print("Esperando a que el sistema sincronice la hora por WiFi...")
        time.sleep(5)
    print("Hora correcta sincronizada. Arrancando nodo.")
    print(f"Ciclo configurado: {DURATION}s de grabación cada {INTERVALO}s ({INTERVALO//60} min).")

    try:
        # Registro inicial del dispositivo
        try:
            requests.post(
                f"{SERVER_URL}/devices/",
                json={"name": NODE_NAME, "location": "Ubicacion_Desconocida"},
                timeout=5,
            )
        except:
            print("No se pudo registrar el dispositivo en el servidor.")

        while True:
            #Marcamos el inicio del ciclo
            inicio_ciclo = time.time()

            now         = datetime.now()
            timestampDB = now.isoformat()
            timestamp   = now.strftime("%Y-%m-%d_%H-%M-%S")
            filename    = f"record_{timestamp}"
            filenameWAV = f"{filename}.wav"

            # Grabación (60 segundos)
            audio_data    = grabacionAudio(DURATION, SAMPLE_RATE)
            rms_amplitude = float(np.sqrt(np.mean(audio_data ** 2)))
            print(f"Nivel de Audio (RMS): {rms_amplitude:.4f}")

            #Guardar WAV y espectrograma
            audio_path = guardoWAV(audio_data, SAMPLE_RATE, filenameWAV)
            generacionEspectograma(audio_path, filename)
            print("Proceso completado, revisa las carpetas de salida.")

            #Análisis BirdNET
            # Con 60s BirdNET analiza ~40 ventanas solapadas → más detecciones y mejores índices
            print("Analizando especies de aves y ruidos...")
            res = brain.predict(audio_path)

            detecciones_unicas = {}

            if res:
                for r in res:
                    especie   = r['species']
                    confianza = r['confidence']

                    es_humano = "Human" in especie
                    es_motor  = "Motor" in especie or "Noise" in especie
                    es_ruido  = es_humano or es_motor

                    if es_humano and confianza >= UMBRAL_HUMANOS:
                        if especie not in detecciones_unicas or confianza > detecciones_unicas[especie]['confidence']:
                            detecciones_unicas[especie] = r

                    elif es_motor and confianza >= UMBRAL_MOTORES:
                        if especie not in detecciones_unicas or confianza > detecciones_unicas[especie]['confidence']:
                            detecciones_unicas[especie] = r

                    elif not es_ruido and confianza >= UMBRAL_AVES:
                        if especie not in detecciones_unicas or confianza > detecciones_unicas[especie]['confidence']:
                            detecciones_unicas[especie] = r

                if detecciones_unicas:
                    print(f"Captadas {len(detecciones_unicas)} fuentes sonoras.")
                elif rms_amplitude > UMBRAL_RUIDO_ALTO:
                    print("Mucho ruido, sin clasificación clara. Marcando como Ruido Ambiente.")
                    detecciones_unicas['Noise_Ambiente'] = {
                        'species':    'Noise_Ruido Ambiente',
                        'confidence': 1.0
                    }
            else:
                if rms_amplitude > UMBRAL_RUIDO_ALTO:
                    print("Ruido alto detectado. Marcando como Ruido Ambiente.")
                    detecciones_unicas['Noise_Ambiente'] = {
                        'species':    'Noise_Ruido Ambiente',
                        'confidence': 1.0
                    }

            # Enviar resultados
            if detecciones_unicas:
                print("Enviando datos...")
                for especie, datos in detecciones_unicas.items():
                    print(f" -> {especie} ({datos['confidence']*100:.1f}%) [Vol: {rms_amplitude:.3f}]")

                    enviarDatosServidor(
                        species=datos['species'],
                        confidence=datos['confidence'],
                        filename=filename,          # sin extensión — se añade dentro
                        timestamp_str=timestampDB,
                        amplitude=rms_amplitude,
                    )

                    nombre_especie = datos['species']
                    if "Human" not in nombre_especie and "Motor" not in nombre_especie and "Noise" not in nombre_especie:
                        enviarDatosBirdWeather(
                            species=nombre_especie,
                            confidence=datos['confidence'],
                            timestamp=timestampDB,
                            lat=brain.lat,
                            lon=brain.lon,
                        )
            else:
                print("Silencio o ruido bajo irrelevante. No se guarda nada.")

            limpiarArchivosAntiguos()

            # Descontamos grabación + análisis + envío para que el ciclo sea exacto.
            tiempo_usado  = time.time() - inicio_ciclo
            tiempo_espera = INTERVALO - tiempo_usado

            if tiempo_espera > 0:
                print(f"Ciclo completado en {tiempo_usado:.1f}s. "
                      f"Esperando {tiempo_espera:.1f}s hasta el siguiente ciclo...\n")
                time.sleep(tiempo_espera)
            else:
                # Si el procesado tardó más que INTERVALO (muy improbable), arrancamos ya
                print(f"Aviso: el ciclo tardó {tiempo_usado:.1f}s (>{INTERVALO}s). "
                      f"Arrancando siguiente ciclo sin espera.\n")

    except KeyboardInterrupt:
        print("\nPrograma interrumpido.")
    except Exception as e:
        print(f"\nOcurrió un error: {e}")