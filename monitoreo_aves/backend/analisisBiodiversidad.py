import sqlite3, os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

###DIRECTORIO DE LA BASE DE DATOS Y UMBRAL
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'app', 'bird_monitor.db')
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
        'Abundancia (N)': N,
        'Riqueza (S)': S,
        "Indice de Shannon (H')": round(shannon,3),
        "Indice de Simpson (D)": round(simps_index,3),
        "Indice de Pielou (J')": round(pielou_j,3)
    }

def evaluar_shannon(valor):
    if valor < 1.5: return "POBRE"
    if valor < 3.0: return "MODERADO"
    return "EXCELENTE"

def obtener_reporte_biodiversidad():
    """Esta es la función que llamará la API"""
    df = conectar_db()
    
    if df.empty:
        return []

    # Limpieza de datos (Filtros científicos)
    df = df[df['confidence'] >= UMBRA_CONFIANZA]
    df['species'] = df['species'].apply(lambda x: x.split('_')[1] if '_' in x else x)
    df = df[~df['species'].str.contains("Noise|Ruido|Human|Motor", case=False)]

    zonas = df['zona'].unique()
    informe_final = []

    for zona in zonas:
        if not zona: continue
        
        datos_zona = df[df['zona'] == zona]
        indices = calculo_de_indices(datos_zona)
        
        if indices:
            indices['zona'] = zona
            informe_final.append(indices)
            
    return informe_final