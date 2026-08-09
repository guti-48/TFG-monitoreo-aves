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


def conectar_db(site_id=None, deployment_id=None, device_id=None):
    """Carga detecciones con su sitio y despliegue sin mezclar campañas."""
    conexion = sqlite3.connect(DB_PATH)
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
        s.id AS site_id,
        s.code AS site_code,
        s.name AS site_name,
        s.name AS zona,
        s.lat,
        s.lon,
        p.id AS deployment_id,
        p.public_id AS deployment_public_id
    FROM detections d
    JOIN devices dev ON d.device_id = dev.id
    JOIN deployments p ON d.deployment_id = p.id
    JOIN sites s ON p.site_id = s.id
    LEFT JOIN detection_reviews r ON r.detection_id = d.id
    WHERE 1 = 1
    """
    params = []
    if site_id is not None:
        query += " AND s.id = ?"
        params.append(int(site_id))
    if deployment_id is not None:
        query += " AND p.id = ?"
        params.append(int(deployment_id))
    if device_id is not None:
        query += " AND dev.id = ?"
        params.append(int(device_id))

    res = pd.read_sql_query(query, conexion, params=params)
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


def calcular_indices_acusticos_desde_db(
    device_id,
    site_id=None,
    deployment_id=None,
):
    """
    Calcula las últimas 100 medias del mismo nodo y método.

    Las filas heredadas no se mezclan con ``maad-v2``: el cálculo anterior
    usaba unidades incorrectas y un AEI sintético, por lo que combinarlas
    produciría una serie sin significado comparable.
    """
    try:
        with sqlite3.connect(DB_PATH) as conexion:
            filters = ["am.device_id = ?"]
            params = [int(device_id)]
            if site_id is not None:
                filters.append("p.site_id = ?")
                params.append(int(site_id))
            if deployment_id is not None:
                filters.append("am.deployment_id = ?")
                params.append(int(deployment_id))
            where_sql = " AND ".join(filters)

            legacy_samples = conexion.execute(
                f"""
                SELECT COUNT(*)
                FROM audio_metrics am
                JOIN deployments p ON am.deployment_id = p.id
                WHERE {where_sql}
                  AND COALESCE(am.acoustic_metrics_version, 'legacy-v1') != ?
                """,
                (*params, ACOUSTIC_METRICS_VERSION),
            ).fetchone()[0]
            df = pd.read_sql_query(
                f"""
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
                JOIN deployments p ON am.deployment_id = p.id
                WHERE {where_sql}
                  AND am.acoustic_metrics_version = ?
                ORDER BY am.timestamp DESC
                LIMIT 100
                """,
                conexion,
                params=(*params, ACOUSTIC_METRICS_VERSION),
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


def calcular_indices_acusticos(device_id, site_id=None, deployment_id=None):
    return calcular_indices_acusticos_desde_db(
        device_id,
        site_id=site_id,
        deployment_id=deployment_id,
    )


def obtener_reporte_biodiversidad(
    site_id=None,
    deployment_id=None,
    device_id=None,
):
    """Genera un resumen independiente para cada nodo de grabación."""
    df = _limpiar_detecciones(
        conectar_db(
            site_id=site_id,
            deployment_id=deployment_id,
            device_id=device_id,
        )
    )

    if df.empty:
        return []

    informe_final = []
    for (current_site_id, current_device_id), datos_nodo in df.groupby(
        ['site_id', 'device_id'],
        sort=True,
    ):
        indices = calculo_de_indices(datos_nodo)
        if indices:
            primera = datos_nodo.iloc[0]
            timestamps = pd.to_datetime(
                datos_nodo['timestamp'], errors='coerce'
            ).dropna()
            indices.update(
                {
                    'device_id': int(current_device_id),
                    'site_id': int(current_site_id),
                    'site_code': primera['site_code'],
                    'site_name': primera['site_name'],
                    'deployment_id': (
                        int(primera['deployment_id'])
                        if deployment_id is not None
                        else None
                    ),
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
            indices.update(
                calcular_indices_acusticos(
                    current_device_id,
                    site_id=current_site_id,
                    deployment_id=deployment_id,
                )
            )
            informe_final.append(indices)

    return informe_final


def _obetenerDatosMapa_legacy(device_id=None):
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

def obetenerDatosMapa(device_id=None, site_id=None, deployment_id=None):
    """Devuelve el sitio solicitado y un entorno visual no calibrado."""
    try:
        with sqlite3.connect(DB_PATH) as conexion:
            deployment_row = None
            if deployment_id is not None:
                deployment_row = conexion.execute(
                    """
                    SELECT p.id, p.device_id, p.site_id, d.name
                    FROM deployments p
                    JOIN devices d ON d.id = p.device_id
                    WHERE p.id = ?
                    LIMIT 1
                    """,
                    (int(deployment_id),),
                ).fetchone()
            elif site_id is not None:
                deployment_row = conexion.execute(
                    """
                    SELECT p.id, p.device_id, p.site_id, d.name
                    FROM deployments p
                    JOIN devices d ON d.id = p.device_id
                    WHERE p.site_id = ?
                    ORDER BY (p.ended_at IS NULL) DESC, p.started_at DESC
                    LIMIT 1
                    """,
                    (int(site_id),),
                ).fetchone()
            elif device_id is not None:
                deployment_row = conexion.execute(
                    """
                    SELECT p.id, p.device_id, p.site_id, d.name
                    FROM deployments p
                    JOIN devices d ON d.id = p.device_id
                    WHERE p.device_id = ?
                    ORDER BY (p.ended_at IS NULL) DESC, p.started_at DESC
                    LIMIT 1
                    """,
                    (int(device_id),),
                ).fetchone()
            else:
                deployment_row = conexion.execute(
                    """
                    SELECT p.id, p.device_id, p.site_id, d.name
                    FROM deployments p
                    JOIN devices d ON d.id = p.device_id
                    ORDER BY (p.ended_at IS NULL) DESC, p.started_at DESC
                    LIMIT 1
                    """
                ).fetchone()

            if deployment_id is not None and deployment_row is None:
                return {
                    "available": False,
                    "error": "El despliegue solicitado no existe.",
                }
            if (
                deployment_row is not None
                and site_id is not None
                and int(deployment_row[2]) != int(site_id)
            ):
                return {
                    "available": False,
                    "error": "El despliegue no pertenece al sitio solicitado.",
                }
            if (
                deployment_row is not None
                and device_id is not None
                and int(deployment_row[1]) != int(device_id)
            ):
                return {
                    "available": False,
                    "error": "El despliegue no pertenece al nodo solicitado.",
                }

            selected_site_id = (
                int(site_id)
                if site_id is not None
                else (int(deployment_row[2]) if deployment_row else None)
            )
            site_row = None
            if selected_site_id is not None:
                site_row = conexion.execute(
                    """
                    SELECT
                        id, code, name, lat, lon,
                        location_source, location_accuracy_m
                    FROM sites
                    WHERE id = ?
                    LIMIT 1
                    """,
                    (selected_site_id,),
                ).fetchone()
    except Exception as exc:
        print(f"No se pudieron leer coordenadas del sitio desde DB: {exc}")
        return {
            "available": False,
            "error": "No se pudo consultar la ubicacion configurada del sitio.",
        }

    if not site_row:
        if device_id is not None and site_id is None and deployment_id is None:
            return _obetenerDatosMapa_legacy(device_id=device_id)
        return {
            "available": False,
            "error": "El sitio no existe o no tiene un despliegue seleccionable.",
        }

    (
        selected_site_id,
        site_code,
        location,
        lat,
        lon,
        location_source,
        location_accuracy_m,
    ) = site_row
    selected_deployment_id = int(deployment_row[0]) if deployment_row else None
    selected_device_id = int(deployment_row[1]) if deployment_row else None
    node_name = deployment_row[3] if deployment_row else "Sin nodo asociado"

    if lat is None or lon is None:
        return {
            "available": False,
            "device_id": selected_device_id,
            "site_id": int(selected_site_id),
            "site_code": site_code,
            "node_name": node_name,
            "error": "Configura latitud y longitud para mostrar este sitio.",
        }

    datos_sitio = _limpiar_detecciones(
        conectar_db(
            site_id=selected_site_id,
            deployment_id=deployment_id,
            device_id=device_id,
        )
    )
    indices = calculo_de_indices(datos_sitio)
    requested_radius_m = _radio_referencia_m()
    location_source = location_source or "unknown"
    location_is_precise = location_source in {"manual", "gps"}
    radius_m = requested_radius_m if location_is_precise else 0.0

    return {
        "available": True,
        "device_id": selected_device_id,
        "site_id": int(selected_site_id),
        "site_code": site_code,
        "deployment_id": selected_deployment_id,
        "node_name": node_name,
        "ciudad": location or "Sin ubicacion nominal",
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
            else "Circulo oculto: coordenadas sin precision documentada"
        ),
        "disclaimer": (
            "El circulo es una referencia visual no calibrada; el alcance real "
            "depende de la especie, el ruido, el habitat y el microfono."
        ),
    }


def obetenerActividadDiaria(
    fecha_str,
    site_id=None,
    deployment_id=None,
    device_id=None,
):
    '''Agruparemos las actividades de la avifauna por horas del dia para ver su actividad y sus horas mas propensas a salir'''
    df = conectar_db(
        site_id=site_id,
        deployment_id=deployment_id,
        device_id=device_id,
    )

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