import os
import sqlite3

import pandas as pd
import numpy as np

###DIRECTORIO DE LA BASE DE DATOS Y UMBRAL
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("BIRDMONITOR_DB_PATH", os.path.join(BASE_DIR, 'app', 'birdmonitor.db'))

UMBRA_CONFIANZA = 0.0
FILTRO_RUIDO = r"Noise|Ruido|Human|Motor|Ambiente"
ACOUSTIC_METRICS_VERSION = "maad-v2"


def _radio_referencia_m():
    """Radio visual local; no representa una distancia efectiva calibrada."""
    try:
        value = float(os.getenv("BIRDMONITOR_ACOUSTIC_REFERENCE_RADIUS_M", "25"))
    except (TypeError, ValueError):
        value = 25.0
    return round(max(0.0, min(value, 200.0)), 1)


def conectar_db():
    '''Nos conectaremos a la base de datos y descargaremos las detecciones de esta'''
    conexion = sqlite3.connect(DB_PATH)
    # Leemos las detecciones y unimos con el nombre del dispositivo
    query = """
    SELECT
        d.timestamp,
        CASE
            WHEN r.status = 'corrected'
                 AND r.corrected_species IS NOT NULL
                 AND TRIM(r.corrected_species) != ''
                THEN r.corrected_species
            WHEN r.status IN ('noise', 'discarded', 'doubtful')
                THEN 'Noise_Revision Humana'
            ELSE d.species
        END AS species,
        d.confidence,
        dev.id AS device_id,
        dev.name AS device_name,
        dev.location AS zona,
        dev.lat,
        dev.lon
    FROM detections d
    JOIN devices dev ON d.device_id = dev.id
    LEFT JOIN detection_reviews r ON r.detection_id = d.id
    """
    res = pd.read_sql_query(query, conexion)
    conexion.close()
    return res


def _limpiar_detecciones(df):
    """Aplica a todas las vistas el mismo alcance de detecciones de aves."""
    if df.empty:
        return df.copy()

    limpio = df[df['confidence'] >= UMBRA_CONFIANZA].copy()
    limpio['species'] = limpio['species'].fillna('').astype(str).apply(
        lambda value: value.split('_', 1)[1] if '_' in value else value
    )
    return limpio[
        ~limpio['species'].str.contains(FILTRO_RUIDO, case=False, na=False)
    ].copy()


def calculo_de_indices(zona):
    """Describe la distribución de eventos BirdNET; no estima individuos."""
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
        pielou_j = None

    return {
        'abundancia': N,
        'riqueza': S,
        'shannon': round(shannon,3),
        'simpson': round(simps_index,3),
        'pielou': round(pielou_j,3) if pielou_j is not None else None,
        'calidad': evaluar_shannon(shannon)
    }

def evaluar_shannon(_valor):
    """No existen umbrales universales de calidad ecológica para Shannon."""
    return "DESCRIPTIVO"

def _media_segura(df, columna, decimales):
    if columna not in df.columns or df[columna].dropna().empty:
        return None
    valor = float(df[columna].mean())
    return round(valor, decimales) if np.isfinite(valor) else None


def _metricas_no_disponibles(legacy_samples=0):
    return {
        'rms_avg': None,
        'aci_avg': None,
        'adi_avg': None,
        'aei_avg': None,
        'bio_avg': None,
        'ndsi_avg': None,
        'ht_avg': None,
        'hf_avg': None,
        'h_avg': None,
        'metrics_available': False,
        'metrics_status': 'pending_maad_v2',
        'metrics_version': ACOUSTIC_METRICS_VERSION,
        'metric_samples': 0,
        'metric_duration_seconds': 0.0,
        'metric_period_start': None,
        'metric_period_end': None,
        'legacy_metric_samples': int(legacy_samples),
    }


def calcular_indices_acusticos_desde_db(device_id):
    """
    Calcula las últimas 100 medias del mismo nodo y método.

    Las filas heredadas no se mezclan con ``maad-v2``: el cálculo anterior
    usaba unidades incorrectas y un AEI sintético, por lo que combinarlas
    produciría una serie sin significado comparable.
    """
    try:
        with sqlite3.connect(DB_PATH) as conexion:
            legacy_samples = conexion.execute(
                """
                SELECT COUNT(*)
                FROM audio_metrics
                WHERE device_id = ?
                  AND COALESCE(acoustic_metrics_version, 'legacy-v1') != ?
                """,
                (int(device_id), ACOUSTIC_METRICS_VERSION),
            ).fetchone()[0]
            df = pd.read_sql_query(
                """
                SELECT
                    am.timestamp,
                    am.duration,
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
                WHERE am.device_id = ?
                  AND am.acoustic_metrics_version = ?
                ORDER BY am.timestamp DESC
                LIMIT 100
                """,
                conexion,
                params=(int(device_id), ACOUSTIC_METRICS_VERSION),
            )
    except Exception as e:
        print(f"No se pudieron leer métricas acústicas desde la base de datos: {e}")
        return _metricas_no_disponibles()

    if df.empty:
        return _metricas_no_disponibles(legacy_samples)

    timestamps = pd.to_datetime(df['timestamp'], errors='coerce').dropna()
    duration = pd.to_numeric(df['duration'], errors='coerce').fillna(0).sum()

    return {
        'rms_avg':  _media_segura(df, 'rms', 4),
        'aci_avg':  _media_segura(df, 'aci', 3),
        'adi_avg':  _media_segura(df, 'adi', 3),
        'aei_avg':  _media_segura(df, 'aei', 3),
        'bio_avg':  _media_segura(df, 'bio', 3),
        'ndsi_avg': _media_segura(df, 'ndsi', 3),
        'ht_avg':   _media_segura(df, 'ht', 3),
        'hf_avg':   _media_segura(df, 'hf', 3),
        'h_avg':    _media_segura(df, 'h', 3),
        'metrics_available': True,
        'metrics_status': 'current',
        'metrics_version': ACOUSTIC_METRICS_VERSION,
        'metric_samples': int(len(df)),
        'metric_duration_seconds': round(float(duration), 1),
        'metric_period_start': (
            timestamps.min().isoformat() if not timestamps.empty else None
        ),
        'metric_period_end': (
            timestamps.max().isoformat() if not timestamps.empty else None
        ),
        'legacy_metric_samples': int(legacy_samples),
    }


def calcular_indices_acusticos(device_id):
    return calcular_indices_acusticos_desde_db(device_id)


def obtener_reporte_biodiversidad():
    """Genera un resumen independiente para cada nodo de grabación."""
    df = _limpiar_detecciones(conectar_db())

    if df.empty:
        return []

    informe_final = []
    for device_id, datos_nodo in df.groupby('device_id', sort=True):
        indices = calculo_de_indices(datos_nodo)
        if indices:
            primera = datos_nodo.iloc[0]
            timestamps = pd.to_datetime(
                datos_nodo['timestamp'], errors='coerce'
            ).dropna()
            indices.update(
                {
                    'device_id': int(device_id),
                    'node_name': primera['device_name'],
                    'zona': primera['zona'] or 'Sin ubicación configurada',
                    'detection_period_start': (
                        timestamps.min().isoformat()
                        if not timestamps.empty
                        else None
                    ),
                    'detection_period_end': (
                        timestamps.max().isoformat()
                        if not timestamps.empty
                        else None
                    ),
                }
            )
            indices.update(calcular_indices_acusticos(device_id))
            informe_final.append(indices)

    return informe_final


def obetenerDatosMapa(device_id=None):
    """Devuelve el punto real del nodo y un entorno visual no calibrado."""
    try:
        with sqlite3.connect(DB_PATH) as conexion:
            if device_id is not None:
                row = conexion.execute(
                    """
                    SELECT
                        id, name, location, lat, lon,
                        location_source, location_accuracy_m
                    FROM devices
                    WHERE id = ?
                    LIMIT 1
                    """,
                    (int(device_id),),
                ).fetchone()
            else:
                row = conexion.execute(
                    """
                    SELECT
                        id, name, location, lat, lon,
                        location_source, location_accuracy_m
                    FROM devices
                    WHERE lat IS NOT NULL AND lon IS NOT NULL
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()
    except Exception as e:
        print(f"No se pudieron leer coordenadas del nodo desde DB: {e}")
        return {
            "available": False,
            "error": "No se pudo consultar la ubicación configurada del nodo.",
        }

    if not row:
        return {
            "available": False,
            "error": "El nodo no existe o todavía no tiene coordenadas configuradas.",
        }

    (
        selected_id,
        node_name,
        location,
        lat,
        lon,
        location_source,
        location_accuracy_m,
    ) = row
    if lat is None or lon is None:
        return {
            "available": False,
            "device_id": int(selected_id),
            "node_name": node_name,
            "error": (
                "Configura la latitud y longitud del nodo para mostrar su "
                "ubicación. No se estimará a partir de la IP del servidor."
            ),
        }

    df = _limpiar_detecciones(conectar_db())
    datos_nodo = df[df['device_id'] == selected_id] if not df.empty else df
    indices = calculo_de_indices(datos_nodo)
    requested_radius_m = _radio_referencia_m()
    location_source = location_source or "unknown"
    location_is_precise = location_source in {"manual", "gps"}
    radius_m = requested_radius_m if location_is_precise else 0.0

    return {
        "available": True,
        "device_id": int(selected_id),
        "node_name": node_name,
        "ciudad": location or "Sin ubicación nominal",
        "lat": float(lat),
        "lon": float(lon),
        "location_source": location_source,
        "location_accuracy_m": (
            float(location_accuracy_m)
            if location_accuracy_m is not None
            else None
        ),
        "location_is_precise": location_is_precise,
        "shannon": indices['shannon'] if indices else None,
        "event_count": indices['abundancia'] if indices else 0,
        "species_count": indices['riqueza'] if indices else 0,
        "reference_radius_m": radius_m,
        "requested_reference_radius_m": requested_radius_m,
        "reference_area_hectares": round(np.pi * radius_m ** 2 / 10000, 2),
        "radio_km": radius_m / 1000,
        "range_basis": "uncalibrated_local_reference",
        "range_label": (
            "Entorno local orientativo; radio no calibrado"
            if location_is_precise
            else "Círculo oculto: coordenadas sin precisión documentada"
        ),
        "disclaimer": (
            "El círculo no garantiza detección dentro de él ni excluye sonidos "
            "más lejanos. El alcance depende de la especie, el ruido, el "
            "hábitat, la ganancia y el micrófono. Solo se dibuja con "
            "coordenadas manuales o GPS."
        ),
    }

def obetenerActividadDiaria(fecha_str):
    '''Agruparemos las actividades de la avifauna por horas del dia para ver su actividad y sus horas mas propensas a salir'''
    df = conectar_db()

    if df.empty:
        return [{"hora": h, "total_detecciones": 0, "confianza_media": 0.0, "especies_activas": 0, "lista_especies": []} for h in range(24)]
    
    # Aplicamos el mismo filtro usado por el resto del análisis.
    df = _limpiar_detecciones(df)

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