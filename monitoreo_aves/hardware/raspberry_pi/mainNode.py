import os, time, librosa, csv, json
import numpy as np
import sounddevice as sd
import soundfile as sf
import librosa.display
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
from datetime import datetime
from analyzer import BirdAnalyzer

#### CONFIGURACION DEL NODO ####
NODE_NAME = os.getenv("BIRDMONITOR_NODE_NAME", "birdmonitor")
SERVER_URL = os.getenv("BIRDMONITOR_SERVER_URL", "http://100.98.248.58:8000").rstrip("/")

# Ubicación manual opcional
NODE_LOCATION = os.getenv("BIRDMONITOR_NODE_LOCATION", "").strip()
NODE_LAT = os.getenv("BIRDMONITOR_NODE_LAT", "").strip()
NODE_LON = os.getenv("BIRDMONITOR_NODE_LON", "").strip()

# Geolocalización automática por IP pública
AUTO_GEOLOCATION = os.getenv("BIRDMONITOR_AUTO_GEOLOCATION", "1") == "1"
GEO_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "node_location_cache.json")

BIRDWEATHER_ID = os.getenv("BIRDWEATHER_ID", "")
BIRDWEATHER_URL = "https://app.birdweather.com/api/v1/stations/detections"

MIC_DEVICE = os.getenv("BIRDMONITOR_MIC_DEVICE", "").strip()

#### CONFIGURACION AUDIO ####
SAMPLE_RATE = 48000  # Frecuencia que suele usar birdNet
DURATION    = 60      
INTERVALO   = 300    

### UMBRALES CONFIANZA
UMBRAL_AVES       = 0.65   
UMBRAL_HUMANOS    = 0.35   
UMBRAL_MOTORES    = 0.40   
UMBRAL_RUIDO_ALTO = 0.02   

#### RUTAS
BASER_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_FOLDER_AUDIO = os.path.join(BASER_DIR, "records")
OUTPUT_FOLDER_IMG   = os.path.join(BASER_DIR, "spectrograms")
CSV_BACKUP          = os.path.join(BASER_DIR, "backup_data.csv")

os.makedirs(OUTPUT_FOLDER_AUDIO, exist_ok=True)
os.makedirs(OUTPUT_FOLDER_IMG,   exist_ok=True)

# Se carga una única vez el modelo
def get_brain():
    return BirdAnalyzer()

def cargarUbicacionCache():
    """Carga la última ubicación conocida desde disco."""
    if not os.path.isfile(GEO_CACHE_FILE):
        return None

    try:
        with open(GEO_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"No se pudo leer caché de ubicación: {e}")
        return None


def guardarUbicacionCache(data):
    """Guarda la ubicación detectada para reutilizarla si no hay red."""
    try:
        with open(GEO_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"No se pudo guardar caché de ubicación: {e}")


def detectarUbicacionPorIP():
    """
    Detecta ubicación aproximada usando la IP pública de salida a Internet.
    No usa IP local ni IP de Tailscale.
    """
    url = (
        "http://ip-api.com/json/"
        "?fields=status,message,country,regionName,city,lat,lon,query"
        "&lang=es"
    )

    try:
        print("Detectando ubicación aproximada por IP pública...")
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()

        if data.get("status") != "success":
            print(f"No se pudo geolocalizar por IP: {data.get('message', 'respuesta inválida')}")
            return None

        city = data.get("city") or ""
        region = data.get("regionName") or ""
        country = data.get("country") or ""

        partes = [p for p in [city, region, country] if p]
        location = ", ".join(partes) if partes else "Ubicacion_Desconocida"

        resultado = {
            "location": location,
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "public_ip": data.get("query"),
            "source": "ip_geolocation"
        }

        guardarUbicacionCache(resultado)

        print(f"Ubicación detectada: {location}")
        print(f"Coordenadas aproximadas: {resultado['lat']}, {resultado['lon']}")
        return resultado

    except Exception as e:
        print(f"Error detectando ubicación por IP: {e}")
        return None


def obtenerUbicacionNodo():
    """
    Prioridad: manual --> geolocalizacion por ip --> cache local --> desconocido
    """
    if NODE_LOCATION:
        return {
            "location": NODE_LOCATION,
            "lat": float(NODE_LAT) if NODE_LAT else None,
            "lon": float(NODE_LON) if NODE_LON else None,
            "source": "manual"
        }

    if AUTO_GEOLOCATION:
        geo = detectarUbicacionPorIP()
        if geo:
            return geo

    cache = cargarUbicacionCache()
    if cache:
        print(f"Usando ubicación cacheada: {cache.get('location')}")
        return cache

    return {
        "location": "Ubicacion_Desconocida",
        "lat": None,
        "lon": None,
        "source": "unknown"
    }

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
    Devuelve el índice del micrófono de entrada, si BIRDMONITOR_MIC_DEVICE está definido, intenta usarlo.
    Si no, usamos el dispositivo de entrada por defecto.
    """
    try:
        dispositivos = sd.query_devices()
    except Exception as e:
        print(f"No se pudo consultar PortAudio/sounddevice: {e}")
        return None

    # Caso 1: dispositivo definido manualmente por variable de entorno
    if MIC_DEVICE:
        try:
            idx = int(MIC_DEVICE)
            if idx < 0 or idx >= len(dispositivos):
                print(f"BIRDMONITOR_MIC_DEVICE={idx} fuera de rango.")
                return None

            if dispositivos[idx].get("max_input_channels", 0) <= 0:
                print(f"El dispositivo {idx} no tiene canales de entrada.")
                return None

            print(f"Micrófono seleccionado por entorno: [{idx}] {dispositivos[idx]['name']}")
            return idx

        except ValueError:
            print("BIRDMONITOR_MIC_DEVICE debe ser un índice numérico, por ejemplo 1 o 2.")
            return None

    # Caso 2: dispositivo de entrada por defecto
    try:
        default_input = sd.default.device[0]

        if default_input is not None and default_input >= 0:
            dev = dispositivos[default_input]
            if dev.get("max_input_channels", 0) > 0:
                print(f"Micrófono por defecto: [{default_input}] {dev['name']}")
                return default_input
    except Exception:
        pass

    # Caso 3: primer dispositivo con canales de entrada
    for idx, dev in enumerate(dispositivos):
        if dev.get("max_input_channels", 0) > 0:
            print(f"Micrófono encontrado automáticamente: [{idx}] {dev['name']}")
            return idx

    print("No se ha detectado ningún micrófono de entrada.")
    return None


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
        "source":     "birdmonitor"
    }

    try:
        response = requests.post(BIRDWEATHER_URL, json=datos_publicos, timeout=15)
        if response.status_code == 200:
            print("Datos enviados a BirdWeather correctamente.")
        else:
            print(f"BirdWeather rechazó los datos: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error al conectar con BirdWeather: {e}")


def grabacionAudio(duration, fs, device_index):
    """
    Graba audio mono durante `duration` segundos a frecuencia `fs`.
    Con 60s BirdNET analiza ~40 ventanas solapadas
    """
    if device_index is None:
        raise RuntimeError("No hay micrófono de entrada disponible.")

    try:
        print(f"Grabando audio durante {duration} segundos con dispositivo [{device_index}]...")
        grab = sd.rec(
            int(duration * fs),
            samplerate=fs,
            channels=1,
            dtype="float32",
            device=device_index
        )
        sd.wait()

        audio = grab.flatten()

        if audio.size == 0:
            raise RuntimeError("La grabación ha devuelto un array vacío.")

        if not np.isfinite(audio).all():
            raise RuntimeError("La grabación contiene valores no válidos: NaN o Inf.")

        print("Grabación finalizada.")
        return audio

    except Exception as e:
        raise RuntimeError(f"Error durante la grabación de audio: {e}") from e


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
            r = requests.post(url_archivos, files=archivos, timeout=60)
            if r.status_code == 200:
                print(" -> Archivos subidos correctamente.")
            else:
                print(f" -> Error subiendo archivos: {r.status_code}")
    finally:
        for f in archivos_abiertos:
            f.close()

def normalizarFilenameBase(filename):
    """Devuelve el nombre sin extensión .wav."""
    return filename[:-4] if filename.endswith(".wav") else filename


def normalizarFilenameWav(filename):
    """Devuelve el nombre con extensión .wav."""
    return filename if filename.endswith(".wav") else f"{filename}.wav"

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
        r = requests.post(f"{SERVER_URL}/detections/", json=datos, timeout=60)
        if r.status_code == 200:
            _subir_archivos(filename)
            sincronizarRespaldo()
        else:
            print(f"Servidor rechazó la detección ({r.status_code}). Guardando local...")
            guardarBackupLocal(species, confidence, timestamp_str, amplitude, normalizarFilenameBase(filename))

    except requests.exceptions.RequestException as e:
        print(f"Error de conexión: {e}. Guardando local...")
        guardarBackupLocal(species, confidence, timestamp_str, amplitude, normalizarFilenameBase(filename))


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
                    "filename":    normalizarFilenameWav(fname),
                    "device_name": NODE_NAME,
                    "amplitude":   float(amp)
                }

                response = requests.post(f"{SERVER_URL}/detections/", json=datos_json, timeout=60)

                if response.status_code == 200:
                    _subir_archivos(normalizarFilenameBase(fname))
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

def esperarSiguienteCiclo(inicio_ciclo):
    """Espera hasta completar el intervalo configurado del ciclo."""
    tiempo_usado = time.time() - inicio_ciclo
    tiempo_espera = INTERVALO - tiempo_usado

    if tiempo_espera > 0:
        print(
            f"Ciclo completado en {tiempo_usado:.1f}s. "
            f"Esperando {tiempo_espera:.1f}s hasta el siguiente ciclo...\n"
        )
        time.sleep(tiempo_espera)
    else:
        print(
            f"Aviso: el ciclo tardó {tiempo_usado:.1f}s (>{INTERVALO}s). "
            f"Arrancando siguiente ciclo sin espera.\n"
        )

### Flujo de trabajo principal ###
if __name__ == "__main__":

    brain = BirdAnalyzer()
    listarDispositivosAudio()
    device_index = resolverDispositivoEntrada()
    ubicacion_nodo = obtenerUbicacionNodo()
    print("Verificando reloj interno")
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
                json={
                    "name": NODE_NAME,
                    "location": ubicacion_nodo["location"]
                },
                timeout=10,
            )
        except:
            print("No se pudo registrar el dispositivo en el servidor.")

        while True:
            #Marcamos el inicio del ciclo
            inicio_ciclo = time.time()

            try:
                now         = datetime.now()
                timestampDB = now.isoformat()
                timestamp   = now.strftime("%Y-%m-%d_%H-%M-%S")
                filename    = f"record_{timestamp}"
                filenameWAV = f"{filename}.wav"

                # Grabación (60 segundos)
                if device_index is None:
                    print("Modo centinela: no hay micrófono disponible, se reintentara en el siguiente ciclo.")
                    device_index = resolverDispositivoEntrada()
                    continue

                audio_data = grabacionAudio(DURATION, SAMPLE_RATE, device_index)
                rms_amplitude = float(np.sqrt(np.mean(audio_data ** 2)))
                print(f"Nivel de Audio (RMS): {rms_amplitude:.4f}")

                #Guardar WAV y espectrograma
                audio_path = guardoWAV(audio_data, SAMPLE_RATE, filenameWAV)
                generacionEspectograma(audio_path, filename)
                print("Proceso completado, revisa las carpetas de salida.")

                #Análisis BirdNET
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
                            filename=filename,          
                            timestamp_str=timestampDB,
                            amplitude=rms_amplitude,
                        )

                        nombre_especie = datos['species']
                        if "Human" not in nombre_especie and "Motor" not in nombre_especie and "Noise" not in nombre_especie:
                            enviarDatosBirdWeather(
                                species=nombre_especie,
                                confidence=datos['confidence'],
                                timestamp=timestampDB,
                                lat=ubicacion_nodo["lat"] if ubicacion_nodo["lat"] is not None else brain.lat,
                                lon=ubicacion_nodo["lon"] if ubicacion_nodo["lon"] is not None else brain.lon,
                            )
                else:
                    print("Silencio o ruido bajo irrelevante. No se guarda nada.")

                limpiarArchivosAntiguos()
            
            except Exception as e:
                print(f"Error controlado en el ciclo principal (el nodo continuara en el siguiente ciclo): {e}")
                device_index = resolverDispositivoEntrada()
            finally:
                esperarSiguienteCiclo(inicio_ciclo)

    except KeyboardInterrupt:
        print("\nPrograma interrumpido.")
    except Exception as e:
        print(f"\nOcurrió un error: {e}")