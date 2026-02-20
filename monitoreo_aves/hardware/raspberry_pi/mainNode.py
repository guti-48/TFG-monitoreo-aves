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

###CONFIGFURACION PARA EL USO DE BIRDWEATHER####
###NODO DE ALGECIRAS
BIRDWEATHER_ID = "BgQxkL7v2DA8A3V9BwgQMwAp" # Aqui va el ID que nos proporciona BirdWeather para este nodo registrado
BIRDWEATHER_URL = "https://app.birdweather.com/api/v1/stations/detections"

#### CONFIGURACION AUDIO####
SAMPLE_RATE = 48000 # Frecuencia que suele usar birdNet
DURATION = 10  # Duracion de la grabacion en segundos

BASER_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_FOLDER_AUDIO = os.path.join(BASER_DIR, "records") 
OUTPUT_FOLDER_IMG = os.path.join(BASER_DIR, "spectrograms")

# Aqui lo que haremos sera un check para ver que existen las carpetas
os.makedirs(OUTPUT_FOLDER_AUDIO, exist_ok=True)
os.makedirs(OUTPUT_FOLDER_IMG, exist_ok=True)

# Se carga un aunica vez el modelo
brain = BirdAnalyzer()

def enviarDatosBirdWeather(species, confidence, lat, lon, timestamp):
    """
    Enviaremos todos los datos sobre PAJAROS a la app BirdWeather
    """

    if BIRDWEATHER_ID == "":
        return
    
    ##Con esto resulvo el problema de los guiones bajos
    if "_" in species:
        cleanSpecies = species.split('_')[1]
    else:
        cleanSpecies = species

    datos_publicos = {
        "token": BIRDWEATHER_ID,
        "timestamp": timestamp,
        "species": cleanSpecies,
        "confidence": confidence,
        "lat": lat,
        "lon": lon,
        "source": "BirdMonitor13 Guti"
    } 

    try:
        response = requests.post(BIRDWEATHER_URL, json=datos_publicos, timeout=5)

        if response.status_code == 200:
            print(f"Datos enviados a BirdWeather correctamente.")
        else:
            print(f"BirdWeather rechazó los datos: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"Error al conectar con BirdWeather: {e}")


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

####FUNCION DONDE ENVIAREMOS LOS DATOS AL SERVIDOR ####
def enviarDatosServidor(species, confidence, filename, timestamp_str, amplitude):
    #datos en json
    url = f"{SERVER_URL}/detections/"

    datos = {
        "species": species,
        "confidence": confidence,
        "timestamp": timestamp_str,
        "filename": f"{filename}.wav",
        "device_name": NODE_NAME,
        "amplitude":float(amplitude)
    }

    try:
        response = requests.post(url, json=datos, timeout=5)
        if response.status_code == 200:
            url_archivos = f"{SERVER_URL}/upload/"
            ruta_audio = os.path.join(OUTPUT_FOLDER_AUDIO, f"{filename}.wav")
            ruta_img = os.path.join(OUTPUT_FOLDER_IMG, f"{filename}.png")
            
            # Preparamos los archivos para enviarlos por HTTP (Multipart form data)
            archivos = {}
            archivos_abiertos = [] # Para cerrarlos después
            
            try:
                if os.path.exists(ruta_audio):
                    f_audio = open(ruta_audio, 'rb')
                    archivos['audio_file'] = (f"{filename}.wav", f_audio, 'audio/wav')
                    archivos_abiertos.append(f_audio)
                    
                if os.path.exists(ruta_img):
                    f_img = open(ruta_img, 'rb')
                    archivos['img_file'] = (f"{filename}.png", f_img, 'image/png')
                    archivos_abiertos.append(f_img)
                
                if archivos:
                    # Hacemos el POST de los archivos
                    response_archivos = requests.post(url_archivos, files=archivos, timeout=10)
                    if response_archivos.status_code == 200:
                        print(" -> Archivos de audio e imagen subidos correctamente.")
                    else:
                        print(f" -> Error subiendo archivos: {response_archivos.status_code}")
            finally:
                for f in archivos_abiertos:
                    f.close()
            
            sincronizarRespaldo()

        else:
            print(f"Servidor rechazó ({response.status_code}). Guardando local...")
            guardarBackupLocal(species, confidence, timestamp_str, amplitude, filename)
            
    except Exception as e:
        print(f"Error de conexión con servidor: {e}. Guardando local...")
        guardarBackupLocal(species, confidence, timestamp_str, amplitude, filename)

#Con esta funcioon crearemos una backup local, de la tarjetaSD los recogeremos posteriormente
def guardarBackupLocal(species, confidence, timestamp, amplitude, filename):
    '''Guardaremos los datos en un csv local si el servidor lo apgamos'''
    csvDeBackup = "backup_data.csv"
    existe = os.path.isfile(csvDeBackup)

    with open(csvDeBackup, mode='a', newline='') as f:
        escritura = csv.writer(f)
        if not existe:
            escritura.writerow(['Timestamp', 'Species', 'Confidence', 'Amplitude', 'Filename'])
        escritura.writerow([timestamp, species, confidence, amplitude, filename])
    print(f"Datos guardados en el respalado local {csvDeBackup}")

def limpiarArchivosAntiguos():
    """
    Mantiene la salud del sistema borrando archivos WAV y PNG antiguos
    para no llenar la tarjeta SD.
    Se conservan los archivos de las últimas 24 horas (ajustable).
    """
    carpetas = [OUTPUT_FOLDER_AUDIO, OUTPUT_FOLDER_IMG]
    ahora = time.time()
    # 86400 segundos = 1 dia. Borramos lo que tenga más de 1 día.
    # Si quieres guardar más días, multiplica 86400 * dias
    TIEMPO_VIDA = 86400 * 2 

    print("Iniciando limpieza de disco...")
    archivos_borrados = 0
    
    for carpeta in carpetas:
        for archivo in os.listdir(carpeta):
            ruta_completa = os.path.join(carpeta, archivo)
            # Si es un archivo (no carpeta)
            if os.path.isfile(ruta_completa):
                stat = os.stat(ruta_completa)
                # Si la fecha de creación es más antigua que el TIEMPO_VIDA
                if stat.st_mtime < (ahora - TIEMPO_VIDA):
                    try:
                        os.remove(ruta_completa)
                        archivos_borrados += 1
                    except Exception as e:
                        print(f"Error borrando {archivo}: {e}")
    
    if archivos_borrados > 0:
        print(f"Limpieza completada: {archivos_borrados} archivos eliminados para liberar espacio.")

#Sincronizacion del respaldo de backup
def sincronizarRespaldo():
    '''Revisa si hay datos pendientes en el csv local, y si tentemos conexion sube al servidor y limpia el archivo'''
    csvDeBackup = "backup_data.csv"

    # sin nada escrito en este csv no se hara nada
    if not os.path.isfile(csvDeBackup):
        return

    print("Intento de sincronizacion de datos offline con el servidor...")

    filasPendientes = []
    filasEnviadas = 0

    try:
        with open(csvDeBackup, mode='r')as f:
            lectura = csv.reader(f)
            filas = list(lectura)

            if not filas or len(filas) <= 1:
                return
            
            cabeceras = filas[0]
            datos = filas[1:]

            for fila in datos:
                try:
                    ts, sp, conf, amp, fname = fila
                    
                    datos_json = {
                        "species": sp,
                        "confidence": float(conf),
                        "timestamp": ts,
                        "filename": fname,
                        "device_name": NODE_NAME,
                        "amplitude": float(amp)
                    }

                    response = requests.post(f"{SERVER_URL}/detections/", json=datos_json, timeout=5)

                    if response.status_code == 200:
                        # enviamos archivos retrasados
                        filename_base = fname.replace(".wav", "")
                        url_archivos = f"{SERVER_URL}/upload/"
                        ruta_audio = os.path.join(OUTPUT_FOLDER_AUDIO, f"{filename_base}.wav")
                        ruta_img = os.path.join(OUTPUT_FOLDER_IMG, f"{filename_base}.png")
                        
                        archivos = {}
                        archivos_abiertos = []
                        
                        try:
                            if os.path.exists(ruta_audio):
                                f_audio = open(ruta_audio, 'rb')
                                archivos['audio_file'] = (f"{filename_base}.wav", f_audio, 'audio/wav')
                                archivos_abiertos.append(f_audio)
                                
                            if os.path.exists(ruta_img):
                                f_img = open(ruta_img, 'rb')
                                archivos['img_file'] = (f"{filename_base}.png", f_img, 'image/png')
                                archivos_abiertos.append(f_img)
                            
                            if archivos:
                                requests.post(url_archivos, files=archivos, timeout=15)
                        finally:
                            for arc in archivos_abiertos:
                                arc.close()

                        filasEnviadas += 1
                        print(f" -> Sincronizado offline: {sp} ({ts}) con sus archivos.")
                    else:
                        #si el servidor falló de nuevo, lo dejamos en la lista de pendientes
                        filasPendientes.append(fila)
                        
                except Exception as e:
                    print(f"Error procesando una fila de backup: {e}")
                    filasPendientes.append(fila)
        
        #reescribimos el CSV solo con los que NO se pudieron enviar
        if filasEnviadas > 0:
            with open(csvDeBackup, mode='w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(cabeceras)
                writer.writerows(filasPendientes)
            print(f"Sincronizacion terminada: {filasEnviadas} recuperados, {len(filasPendientes)} aún pendientes.")

    except Exception as e:
        print(f"Error general de sincronizacion: {e}")



### Flujo de trabajo principal ###
if __name__ == "__main__":

    print("Verificando reloj interno de la Raspberry Pi...")
    while datetime.now().year < 2024:
        print("Esperando a que el sistema sincronice la hora por WiFi...")
        time.sleep(5)
    print("Hora correcta sincronizada. Arrancando nodo.")
    
    try:
        # Registro inicial del dispositivo
        try:
            requests.post(f"{SERVER_URL}/devices/", json={"name": NODE_NAME, "location": "Ubicacion_Desconocida"})
        except:
            print("No se pudo registrar el dispositivo en el servidor.")

        while True:
            now = datetime.now()
            timestampDB = now.isoformat() 
            timestamp = now.strftime("%Y-%m-%d_%H-%M-S")
            filename = f"record_{timestamp}"
            filenameWAV = f"{filename}.wav"

            #Grabacion de audio
            audio_data = grabacionAudio(DURATION, SAMPLE_RATE)

            #Aqui calcularemos el ruido mediante RMS
            # Calculamos la energía del audio que acabamos de grabar
            rms_amplitude = np.sqrt(np.mean(audio_data**2))
            print(f"Nivel de Audio (RMS): {rms_amplitude:.4f}")

            #Guardado de archivo
            audio_path = guardoWAV(audio_data, SAMPLE_RATE, filenameWAV)
            generacionEspectograma(audio_path, filename)
            print("Proceso completado, revisa las carpetas de salida.")

            # Analisis de BirdNET
            print("Analizando especie de ave...")
            res = brain.predict(audio_path)

            detecciones_unicas = {}
            
            # Umbral que decidira el ruido (ajustable)
            UMBRAL_RUIDO_ALTO = 0.02 

            if res:
                print(f"Detecciones brutas: {len(res)}")
                for r in res:
                    especie = r['species']
                    confianza = r['confidence']
                    if especie not in detecciones_unicas or confianza > detecciones_unicas[especie]['confidence']:
                        detecciones_unicas[especie] = r
            else:
                if rms_amplitude > UMBRAL_RUIDO_ALTO:
                    print("Mucho ruido pero sin clasificación. Marcando como Ruido Ambiente.")
                    detecciones_unicas['Noise_Ambiente'] = {
                        'species': 'Noise_Ruido Ambiente',
                        'confidence': 1.0
                    }

            #Aqui enviamos los resultados
            if detecciones_unicas:
                print("Enviando datos...")
                for especie, datos in detecciones_unicas.items():
                    print(f" -> {especie} ({datos['confidence']*100:.1f}%) [Vol: {rms_amplitude:.3f}]")
                    
                    # Estos seran los datos que seran enviados a mi servidor
                    enviarDatosServidor(
                        species=datos['species'],
                        confidence=datos['confidence'],
                        filename=filenameWAV, 
                        timestamp_str=timestampDB,
                        amplitude=rms_amplitude 
                    )

                    # Solo enviaremos a BirdWeather datos de pajaros
                    nombre_especie = datos['species']
                    if "Human" not in nombre_especie and "Motor" not in nombre_especie and "Noise" not in nombre_especie:
                        enviarDatosBirdWeather( 
                            species=nombre_especie,
                            confidence=datos['confidence'],
                            timestamp=timestampDB,
                            lat=brain.lat, 
                            lon=brain.lon
                        )
            else:
                print("Silencio o ruido bajo irrelevante. No se guarda nada.")
            
            limpiarArchivosAntiguos()

    except KeyboardInterrupt:
        print("\nPrograma interrumpido")
    except Exception as e:
        print(f"\nOcurrio un error: {e}")