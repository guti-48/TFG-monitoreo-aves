import sqlite3, os, glob, geocoder
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from maad import sound, features
import warnings
warnings.filterwarnings("ignore")

###DIRECTORIO DE LA BASE DE DATOS Y UMBRAL
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("BIRDMONITOR_DB_PATH", os.path.join(BASE_DIR, 'app', 'birdmonitor.db'))

#ruta para los archivos wav
PROJECT_ROOT = os.path.dirname(BASE_DIR)
RECORDS_DIR = os.path.join(PROJECT_ROOT, 'hardware', 'raspberry_pi', 'records')

UMBRA_CONFIANZA = 0.0 #estipulado en el documento 
FILTRO_RUIDO = r"Noise|Ruido|Human|Motor|Ambiente"


def conectar_db():
    '''Nos conectaremos a la base de datos y descargaremos las detecciones de esta'''
    conexion = sqlite3.connect(DB_PATH)
    # Leemos las detecciones y unimos con el nombre del dispositivo
    query = """
    SELECT d.timestamp, d.species, d.confidence, dev.location as zona
    FROM detections d
    JOIN devices dev ON d.device_id = dev.id
    """
    res = pd.read_sql_query(query, conexion)
    conexion.close()
    return res

def calculo_de_indices(zona):
    """Calculo los indices de biodiversidad para un DataFrame de una zona especifica"""
    N = len(zona)
    if N == 0:
        return None
    
    #Conteo de las especies (ni)
    conteoEspecies = zona['species'].value_counts()

    #Numero de especies unicas (S)
    S = len(conteoEspecies)

    #Preparacion de proporciones (pi)
    proporciones = conteoEspecies / N

    #Indice de Shannon (H')
    shannon = -np.sum(proporciones * np.log(proporciones))

    #Indice de Simpson (D)
    numer = np.sum(conteoEspecies * (conteoEspecies - 1))
    den = N * (N - 1)
    if den > 0:
        D = numer / den
        simps_index = 1 - D
    else:
        simps_index = 0

    #Indice de Pielou (J')
    if S > 1:
        pielou_j = shannon / np.log(S)
    else:
        pielou_j = 0

    return {
        'abundancia': N,
        'riqueza': S,
        'shannon': round(shannon,3),
        'simpson': round(simps_index,3),
        'pielou': round(pielou_j,3),
        'calidad': evaluar_shannon(shannon)
    }

def evaluar_shannon(valor):
    if valor < 1.5: return "POBRE"
    if valor < 3.0: return "MODERADO"
    return "EXCELENTE"

def _media_segura(df, columna, decimales):
    if columna not in df.columns or df[columna].dropna().empty:
        return 0.0
    valor = float(df[columna].mean())
    return round(valor, decimales) if not np.isnan(valor) else 0.0


def calcular_indices_acusticos_desde_db():
    """
    Calcula medias acústicas desde la tabla audio_metrics.
    Esta es la fuente principal: contiene una fila por ciclo de grabación,
    aunque no haya detección de ave.
    """
    try:
        conexion = sqlite3.connect(DB_PATH)
        query = """
        SELECT
            am.timestamp,
            am.rms,
            am.aci,
            am.adi,
            am.aei,
            am.bio,
            am.ndsi,
            am.ht,
            am.hf,
            am.h
        FROM audio_metrics am
        JOIN devices dev ON am.device_id = dev.id
        ORDER BY am.timestamp DESC
        LIMIT 100
        """
        df = pd.read_sql_query(query, conexion)
        conexion.close()
    except Exception as e:
        print(f"No se pudieron leer métricas acústicas desde la base de datos: {e}")
        return None

    if df.empty:
        return None

    return {
        'rms_avg':  _media_segura(df, 'rms', 4),
        'aci_avg':  _media_segura(df, 'aci', 2),
        'adi_avg':  _media_segura(df, 'adi', 2),
        'aei_avg':  _media_segura(df, 'aei', 2),
        'bio_avg':  _media_segura(df, 'bio', 2),
        'ndsi_avg': _media_segura(df, 'ndsi', 2),
        'ht_avg':   _media_segura(df, 'ht', 3),
        'hf_avg':   _media_segura(df, 'hf', 3),
        'h_avg':    _media_segura(df, 'h', 3),
    }


def calcular_indices_acusticos_desde_wav():
    """
    Fallback temporal: calcula índices a partir de WAV disponibles en servidor.
    Se mantiene para no romper el dashboard si todavía no hay filas en audio_metrics.
    """
    archivos = glob.glob(os.path.join(RECORDS_DIR, "*.wav"))
    if not archivos:
        return None

    archivos = sorted(archivos, key=os.path.getmtime, reverse=True)[:100]
    resultados = {'aci': [], 'adi': [], 'aei': [], 'bio': [], 'ndsi': [], 'ht': [], 'hf': [], 'h': []}

    for wav in archivos:
        try:
            s, fs = sound.load(wav)
            Sxx, tn, fn, ext = sound.spectrogram(s, fs)

            _, _, aci = features.acoustic_complexity_index(Sxx)
            resultados['aci'].append(np.sum(aci))

            adi = features.acoustic_diversity_index(Sxx, fn)
            resultados['adi'].append(adi)

            try:
                aei = features.acoustic_evenness_index(Sxx, fn)
            except AttributeError:
                aei = 1.0 - (adi / 3.0) if not np.isnan(adi) else 0.5
            resultados['aei'].append(aei)

            try:
                bio = features.bioacoustics_index(Sxx, fn)
            except AttributeError:
                bio = features.bioacoustic_index(Sxx, fn)
            resultados['bio'].append(bio)

            ndsi, _, _, _ = features.soundscape_index(Sxx, fn)
            resultados['ndsi'].append(ndsi)

            E_t = np.sum(Sxx, axis=0)
            if np.sum(E_t) > 0:
                p_i = E_t / np.sum(E_t)
                ht = -np.sum(p_i * np.log(p_i + 1e-12)) / np.log(len(p_i))
            else:
                ht = 0.0

            E_f = np.sum(Sxx, axis=1)
            if np.sum(E_f) > 0:
                p_j = E_f / np.sum(E_f)
                hf = -np.sum(p_j * np.log(p_j + 1e-12)) / np.log(len(p_j))
            else:
                hf = 0.0

            h = ht * hf

            resultados['ht'].append(ht)
            resultados['hf'].append(hf)
            resultados['h'].append(h)

        except Exception as e:
            print(f'Omitiendo audio por error en el analisis: {e}')

    if not resultados['aci']:
        return None

    aci_avg = float(np.mean(resultados['aci'])) if resultados['aci'] else 0.0
    adi_avg = float(np.mean(resultados['adi'])) if resultados['adi'] else 0.0
    aei_avg = float(np.mean(resultados['aei'])) if resultados['aei'] else 0.0
    bio_avg = float(np.mean(resultados['bio'])) if resultados['bio'] else 0.0
    ndsi_avg = float(np.mean(resultados['ndsi'])) if resultados['ndsi'] else 0.0
    ht_avg = float(np.mean(resultados['ht'])) if resultados['ht'] else 0.0
    hf_avg = float(np.mean(resultados['hf'])) if resultados['hf'] else 0.0
    h_avg = float(np.mean(resultados['h'])) if resultados['h'] else 0.0

    return {
        'aci_avg': round(aci_avg, 2) if not np.isnan(aci_avg) else 0.0,
        'adi_avg': round(adi_avg, 2) if not np.isnan(adi_avg) else 0.0,
        'aei_avg': round(aei_avg, 2) if not np.isnan(aei_avg) else 0.0,
        'bio_avg': round(bio_avg, 2) if not np.isnan(bio_avg) else 0.0,
        'ndsi_avg': round(ndsi_avg, 2) if not np.isnan(ndsi_avg) else 0.0,
        'ht_avg': round(ht_avg, 3) if not np.isnan(ht_avg) else 0.0,
        'hf_avg': round(hf_avg, 3) if not np.isnan(hf_avg) else 0.0,
        'h_avg': round(h_avg, 3) if not np.isnan(h_avg) else 0.0
    }


def calcular_indices_acusticos():
    """
    primero revisa: tabla audio_metrics
    sino: WAVs locales del servidor, para compatibilidad con datos previos
    """
    datos_db = calcular_indices_acusticos_desde_db()
    if datos_db:
        return datos_db

    return calcular_indices_acusticos_desde_wav()

def obtener_reporte_biodiversidad():
    """Esta es la función que llamará la API"""
    df = conectar_db()
    
    if df.empty:
        return []

    # Limpieza de datos (Filtros científicos)
    df = df[df['confidence'] >= UMBRA_CONFIANZA]
    df['species'] = df['species'].apply(lambda x: x.split('_')[1] if '_' in x else x)
    df = df[~df['species'].str.contains(FILTRO_RUIDO, case=False)]

    datosAcusticos = calcular_indices_acusticos()
    zonas = df['zona'].unique()
    informe_final = []

    for zona in zonas:
        if not zona: continue
        datos_zona = df[df['zona'] == zona]

        indices = calculo_de_indices(datos_zona)
        if indices:
            indices['zona'] = zona
            if datosAcusticos:
                indices.update(datosAcusticos)
            else:
                indices.update({'aci_avg': 0, 'adi_avg': 0, 'aei_avg': 0, 'bio_avg': 0, 'ndsi_avg': 0,'ht_avg': 0, 'hf_avg': 0, 'h_avg': 0})
            informe_final.append(indices)
            
    return informe_final

def obetenerDatosMapa():
    '''Obtengo las coordenadas del nodo y su biodiversidad'''
    lat, lon, ciudad = None, None, None

    try:
        conexion = sqlite3.connect(DB_PATH)
        row = conexion.execute(
            """
            SELECT location, lat, lon
            FROM devices
            WHERE lat IS NOT NULL AND lon IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        conexion.close()

        if row:
            ciudad, lat, lon = row
    except Exception as e:
        print(f"No se pudieron leer coordenadas del nodo desde DB: {e}")

    if lat is None or lon is None:
        ip = geocoder.ip('me')
        if ip.latlng:
            lat, lon = ip.latlng
            ciudad = ip.city or "Desconocida"
        else:
            lat, lon = 40.4168, -3.7038   # fallback: Madrid
            ciudad = "Madrid (Desconocida)"

    df = conectar_db()
    shannon_global = 0.5

    if not df.empty:
        df = df[df['confidence'] >= UMBRA_CONFIANZA]
        df = df[~df['species'].str.contains(FILTRO_RUIDO, case=False, na=False)]
        N  = len(df)
        if N > 0:
            conteo = df['species'].value_counts()
            prop   = conteo / N
            shannon_global = round(float(-np.sum(prop * np.log(prop))), 3)

    return {
        "ciudad":   ciudad,
        "lat":      lat,
        "lon":      lon,
        "shannon":  shannon_global,
        "radio_km": 1,
    }

def obetenerActividadDiaria(fecha_str):
    '''Agruparemos las actividades de la avifauna por horas del dia para ver su actividad y sus horas mas propensas a salir'''
    df = conectar_db()

    if df.empty:
        return [{"hora": h, "total_detecciones": 0, "confianza_media": 0.0, "especies_activas": 0, "lista_especies": []} for h in range(24)]
    
    #Aplicamos filtro
    df = df[df['confidence'] >= UMBRA_CONFIANZA]
    df['species'] = df['species'].apply(lambda x: x.split('_')[1] if '_' in x else x)
    df = df[~df['species'].str.contains(FILTRO_RUIDO, case=False, na=False)]

    #convertimos a datetime y filtramos por fecha
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df_dia = df[df['timestamp'].dt.date.astype(str) == fecha_str]

    #agrupamos por hora
    df_dia.loc[:, 'hora'] = df_dia['timestamp'].dt.hour

    informe_diario = []

    #iteramos sobre las 24 horas
    for hora in range(24):
        datos_hora = df_dia[df_dia['hora'] == hora]
        conteo = len(datos_hora)
        especies_unicas = datos_hora['species'].unique().tolist()
        conf_media = datos_hora['confidence'].mean() if conteo > 0 else 0.0
        
        informe_diario.append({
            "hora": hora,
            "total_detecciones": conteo,
            "confianza_media": round(float(conf_media), 3),
            "especies_activas": len(especies_unicas),
            "lista_especies": especies_unicas
        })    

    return informe_diario
