import sqlite3
import numpy as np
import pandas as pd

try:
    from backend.analisisBiodiversidad import ACOUSTIC_METRICS_VERSION, DB_PATH, _limpiar_detecciones, conectar_db
except ModuleNotFoundError:
    from analisisBiodiversidad import ACOUSTIC_METRICS_VERSION, DB_PATH, _limpiar_detecciones, conectar_db

INDICES_ACUSTICOS = (
    ("aci", "ACI", "Complejidad acustica: variacion de la intensidad entre tramos de tiempo."),
    ("adi", "ADI", "Diversidad acustica: reparto de la energia entre bandas de frecuencia."),
    ("aei", "AEI", "Uniformidad acustica: cuan parejo es el reparto entre bandas."),
    ("bio", "BIO", "Bioacustica: energia en la banda donde cantan las aves."),
    ("ndsi", "NDSI", "Paisaje sonoro: -1 dominado por ruido humano, +1 por sonidos biologicos."),
    ("h", "H", "Entropia acustica total."),
)
_CLAVES = [clave for clave, _, _ in INDICES_ACUSTICOS]

# Por debajo de este numero de muestras en un dia (unos 12 min a 60 s cada una) la media diaria
# se marca como poco fiable en lugar de ocultarla.
MUESTRAS_MINIMAS_DIA = 12
#Lo mismo con menos detecciones de 10, se marcara como poco fiable
DETECCIONES_MINIMAS_SEMANA = 10

def _vacio(motivo, legacy_excluidas=0):
    return {
        "available": False,
        "reason": motivo,
        "metrics_version": ACOUSTIC_METRICS_VERSION,
        "legacy_excluded": legacy_excluidas,
        "indices": [],
        "daily": [],
        "hourly": [],
    }

def _limpio(valor, decimales):
    return None if valor is None or pd.isna(valor) else round(float(valor), decimales)

def serie_indices_acusticos(
    site_id=None, deployment_id=None, device_id=None, db_path=None
):
    """
    Media diaria y perfil por hora de cada indice acustico (solo ``maad-v2``).
    Las horas son las del nodo tal como las guarda (hora local de la Raspberry).
    """
    filtros, params = [], []
    if site_id is not None:
        filtros.append("p.site_id = ?")
        params.append(int(site_id))
    if deployment_id is not None:
        filtros.append("am.deployment_id = ?")
        params.append(int(deployment_id))
    if device_id is not None:
        filtros.append("am.device_id = ?")
        params.append(int(device_id))
    donde = (" AND " + " AND ".join(filtros)) if filtros else ""

    try:
        with sqlite3.connect(db_path or DB_PATH) as conexion:
            legacy = conexion.execute(
                f"""SELECT COUNT(*) FROM audio_metrics am
                    JOIN deployments p ON am.deployment_id = p.id
                    WHERE COALESCE(am.acoustic_metrics_version, 'legacy-v1') != ?{donde}""",
                (ACOUSTIC_METRICS_VERSION, *params),
            ).fetchone()[0]
            df = pd.read_sql_query(
                f"""SELECT am.timestamp, am.rms, {", ".join("am." + c for c in _CLAVES)}
                    FROM audio_metrics am
                    JOIN deployments p ON am.deployment_id = p.id
                    WHERE am.acoustic_metrics_version = ?{donde}
                    ORDER BY am.timestamp""",
                conexion,
                params=(ACOUSTIC_METRICS_VERSION, *params),
            )
    except sqlite3.Error as error:
        return _vacio(f"No se pudo leer la base de datos: {error}")

    df["ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["ts"])
    if df.empty:
        return _vacio("Sin metricas del metodo actual en este alcance", legacy)

    df["fecha"] = df["ts"].dt.strftime("%Y-%m-%d")
    df["hora"] = df["ts"].dt.hour

    diario = []
    for fecha, grupo in df.groupby("fecha"):
        fila = {"date": fecha, "n": int(len(grupo)), "low_sample": bool(len(grupo) < MUESTRAS_MINIMAS_DIA)}
        for clave in _CLAVES:
            fila[clave] = _limpio(grupo[clave].mean(), 3)
        diario.append(fila)

    por_hora = []
    for hora, grupo in df.groupby("hora"):
        fila = {"hour": int(hora), "n": int(len(grupo))}
        for clave in _CLAVES:
            fila[clave] = _limpio(grupo[clave].mean(), 3)
        por_hora.append(fila)

    return {
        "available": True,
        "metrics_version": ACOUSTIC_METRICS_VERSION,
        "legacy_excluded": int(legacy),
        "samples": int(len(df)),
        "days": int(df["fecha"].nunique()),
        "period_start": df["ts"].min().isoformat(),
        "period_end": df["ts"].max().isoformat(),
        "min_samples_per_day": MUESTRAS_MINIMAS_DIA,
        "indices": [{"key": k, "label": l, "description": d} for k, l, d in INDICES_ACUSTICOS],
        "daily": diario,
        "hourly": por_hora,
    }


def actividad_por_hora(site_id=None, deployment_id=None, device_id=None):
    #deteccion de aves y especies distintas por hora del dia
    df = _limpiar_detecciones(conectar_db(site_id, deployment_id, device_id))
    df["ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["ts"])
    if df.empty:
        return {"available":False, "reason": "Sin detecciones de aves en este alcance", "hourly":[]}

    df["hora"] = df["ts"].dt.hour
    porHora = df.groupby("hora").agg(detections=("species", "size"), species=("species", "nunique"))
    horas = [
        {
            "hour": hora,
            "detections": int(porHora.loc[hora, "detections"]) if hora in porHora.index else 0,
            "species": int(porHora.loc[hora, "species"]) if hora in porHora.index else 0,
        }
        for hora in range(24)
    ]
    return {
        "available": True,
        "total": int(len(df)),
        "days": int(df["ts"].dt.date.nunique()), 
        "period_start": df["ts"].min().isoformat(),
        "period_end": df["ts"].max().isoformat(),
        "hourly": horas,
    }

def _shannon(conteos):
    #conteos: serie de detecciones por especie
    p = conteos / conteos.sum()
    return max(0.0, float(-(p * np.log(p)).sum())) 

def diversidad_semanal(site_id = None, deployment_id = None, device_id = None):
    #riqueza por semana (shannon)
    df = _limpiar_detecciones(conectar_db(site_id, deployment_id, device_id))
    df["ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["ts"])
    if df.empty:
        return {"available":False, "reason": "Sin detecciones de ave en este alacance", "weekly":[]}
    df["semana"] = df["ts"].dt.to_period("W-SUN").dt.start_time
    semanal = []
    for semana, grupo in df.groupby("semana"):
        conteos = grupo["species"].value_counts()
        semanal.append({
            "week": semana.date().isoformat(),
            "detections": int(len(grupo)),
            "richness": int(len(conteos)),
            "shannon": round(_shannon(conteos), 3),
            "low_sample": bool(len(grupo) < DETECCIONES_MINIMAS_SEMANA),
        })

    return {
        "available": True,
        "total": int(len(df)),
        "species": int(df["species"].nunique()),
        "weeks": len(semanal),
        "period_start": df["ts"].min().isoformat(),
        "period_end": df["ts"].max().isoformat(),
        "min_detections_per_week": DETECCIONES_MINIMAS_SEMANA,
        "weekly": semanal,
    }