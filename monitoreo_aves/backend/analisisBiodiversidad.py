import sqlite3, os, glob, geocoder
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from maad import sound, features
import warnings
warnings.filterwarnings("ignore")

###DIRECTORIO DE LA BASE DE DATOS Y UMBRAL
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'app', 'birdmonitor.db')

#ruta para los archivos wav
PROJECT_ROOT = os.path.dirname(BASE_DIR)
RECORDS_DIR = os.path.join(PROJECT_ROOT, 'hardware', 'raspberry_pi', 'records')

UMBRA_CONFIANZA = 0.0 #estipulado en el documento 

def conectar_db():
    '''Nos conectaremos a la base de datos y descargaremos las detecciones de esta'''
    conexion = sqlite3.connect(DB_PATH)
    # Leemos las detecciones y unimos con el nombre del dispositivo
    query = """
    SELECT d.species, d.confidence, dev.location as zona
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

def calcular_indices_acusticos():
    archivos = glob.glob(os.path.join(RECORDS_DIR, "*.wav"))
    if not archivos:
        return None
    
    #Cogemos los 5 arhchivos mas recientes para que la web cargue
    archivos = sorted(archivos, key=os.path.getmtime, reverse=True)[:5]
    resultados = {'aci': [], 'adi': [], 'aei': [], 'bio': [], 'ndsi': []}

    for wav in archivos:
        try:
            s, fs = sound.load(wav)
            Sxx, tn, fn, ext = sound.spectrogram(s, fs)

            # ACI: indice de complejidad
            _, _, aci = features.acoustic_complexity_index(Sxx)
            resultados['aci'].append(np.sum(aci))

            # ADI: Diversidad acustica
            adi = features.acoustic_diversity_index(Sxx, fn)
            resultados['adi'].append(adi)

            # AEI: uniformidad acustica
            try:
                aei = features.acoustic_evenness_index(Sxx, fn)
            except AttributeError:
                aei = 1.0 - (adi / 3.0) if not np.isnan(adi) else 0.5
            resultados['aei'].append(aei)

            # BIO: indice bioacustico 
            try:
                bio = features.bioacoustics_index(Sxx, fn)
            except AttributeError:
                bio = features.bioacoustic_index(Sxx, fn)
            resultados['bio'].append(bio)

            # NDSI: naturaleza vs antropogénico
            ndsi, _, _, _ = features.soundscape_index(Sxx, fn)
            resultados['ndsi'].append(ndsi)

        except Exception as e:
            print(f'Omitiendo audio por error en el analisis: {e}')

    if not resultados['aci']:
        return None

    aci_avg = float(np.mean(resultados['aci'])) if resultados['aci'] else 0.0
    adi_avg = float(np.mean(resultados['adi'])) if resultados['adi'] else 0.0
    aei_avg = float(np.mean(resultados['aei'])) if resultados['aei'] else 0.0
    bio_avg = float(np.mean(resultados['bio'])) if resultados['bio'] else 0.0
    ndsi_avg = float(np.mean(resultados['ndsi'])) if resultados['ndsi'] else 0.0

    #retirno de la media acustica de la zona
    return {
        'aci_avg': round(aci_avg, 2) if not np.isnan(aci_avg) else 0.0,
        'adi_avg': round(adi_avg, 2) if not np.isnan(adi_avg) else 0.0,
        'aei_avg': round(aei_avg, 2) if not np.isnan(aei_avg) else 0.0,
        'bio_avg': round(bio_avg, 2) if not np.isnan(bio_avg) else 0.0,
        'ndsi_avg': round(ndsi_avg, 2) if not np.isnan(ndsi_avg) else 0.0
    }  


def obtener_reporte_biodiversidad():
    """Esta es la función que llamará la API"""
    df = conectar_db()
    
    if df.empty:
        return []

    # Limpieza de datos (Filtros científicos)
    df = df[df['confidence'] >= UMBRA_CONFIANZA]
    df['species'] = df['species'].apply(lambda x: x.split('_')[1] if '_' in x else x)
    df = df[~df['species'].str.contains("Noise|Ruido|Human|Motor|Ambiente", case=False)]

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
                indices.update({'aci_avg': 0, 'adi_avg': 0, 'aei_avg': 0, 'bio_avg': 0, 'ndsi_avg': 0})
            informe_final.append(indices)
            
    return informe_final

def obetenerDatosMapa():
    '''Obtengo las coordenadas del nodo y su biodiversidad'''
    #localizamos la ip
    ip = geocoder.ip('me')
    if ip.latlng:
        lat, lon = ip.latlng
        ciudad = ip.city
    else:
        lat, lon = 37.3891, -5.9845  # Coordenadas por defecto (Sevilla)
        ciudad = 'Sevilla (Desconocida)'

    df = conectar_db()
    shannon_global = 0.5

    if not df.empty:
        df = df[df['confidence'] >= UMBRA_CONFIANZA]
        df = df[~df['species'].str.contains("Noise|Ruido|Human|Motor|Ambiente", case=False)]
        
        N = len(df)
        if N > 0:
            conteo = df['species'].value_counts()
            prop = conteo / N
            shannon_global = round(-np.sum(prop * np.log(prop)), 3)

    return {
        "ciudad": ciudad,
        "lat": lat,
        "lon": lon,
        "shannon": shannon_global,
        "radio_km": 1
    }