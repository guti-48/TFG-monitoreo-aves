import os
from datetime import datetime, timedelta
from urllib.parse import quote

import requests


def cargarTokenBirdWeather():
    """
    Carga el token sin obligar a escribirlo en el codigo.
    Prioridad: variable directa -> archivo secreto local.
    """
    for env_name in ("BIRDWEATHER_TOKEN", "BIRDWEATHER_ID"):
        token = os.getenv(env_name, "").strip()
        if token:
            return token

    for env_name in ("BIRDWEATHER_TOKEN_FILE", "BIRDWEATHER_ID_FILE"):
        token_file = os.getenv(env_name, "").strip()
        if not token_file:
            continue

        try:
            with open(token_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            print(f"No se pudo leer el token de BirdWeather desde {env_name}: {e}")

    return ""


BIRDWEATHER_ENABLED = os.getenv("BIRDWEATHER_ENABLED", "1") == "1"
BIRDWEATHER_TOKEN = cargarTokenBirdWeather()
BIRDWEATHER_URL = os.getenv(
    "BIRDWEATHER_URL",
    "https://app.birdweather.com/api/v1/stations/{token}/detections",
).strip()


def construirUrlDetecciones(token):
    """Construye la ruta autenticada sin registrar ni exponer el token."""
    safe_token = quote(token, safe="")

    if "{token}" in BIRDWEATHER_URL:
        return BIRDWEATHER_URL.replace("{token}", safe_token)

    legacy_suffix = "/stations/detections"
    if BIRDWEATHER_URL.rstrip("/").endswith(legacy_suffix):
        prefix = BIRDWEATHER_URL.rstrip("/")[:-len(legacy_suffix)]
        return f"{prefix}/stations/{safe_token}/detections"

    return BIRDWEATHER_URL


def ajustarTimestampDeteccion(timestamp, audio_start_seconds):
    try:
        detection_time = datetime.fromisoformat(timestamp)
        if audio_start_seconds is not None:
            detection_time += timedelta(seconds=float(audio_start_seconds))

        if detection_time.tzinfo is None:
            detection_time = detection_time.astimezone()

        return detection_time.isoformat()
    except (TypeError, ValueError):
        return timestamp


def enviarDatosBirdWeather(
    species,
    confidence,
    lat,
    lon,
    timestamp,
    scientific_name=None,
    audio_start_seconds=None,
):
    """Envia datos de aves a BirdWeather."""
    if not BIRDWEATHER_ENABLED or not BIRDWEATHER_TOKEN:
        return False

    if lat is None or lon is None:
        print("No se envia a BirdWeather: faltan coordenadas del nodo.")
        return False

    common_name = species
    if not scientific_name and "_" in species:
        scientific_name, common_name = species.split("_", 1)

    if not scientific_name:
        print("No se envia a BirdWeather: falta el nombre cientifico de la especie.")
        return False

    datos_publicos = {
        "timestamp": ajustarTimestampDeteccion(timestamp, audio_start_seconds),
        "commonName": common_name,
        "scientificName": scientific_name,
        "confidence": float(confidence),
        "lat": float(lat),
        "lon": float(lon),
    }

    try:
        response = requests.post(
            construirUrlDetecciones(BIRDWEATHER_TOKEN),
            json=datos_publicos,
            headers={"User-Agent": "BirdMonitor-TFG/1.0"},
            timeout=15,
        )

        try:
            response_data = response.json()
        except ValueError:
            response_data = None

        accepted = (
            response.status_code in (200, 201)
            and (not isinstance(response_data, dict) or response_data.get("success") is not False)
        )

        if accepted:
            print("Datos enviados a BirdWeather correctamente.")
            return True

        if isinstance(response_data, dict):
            detail = response_data.get("errors") or response_data.get("error") or response_data
        else:
            detail = response.text[:300].strip()

        print(f"BirdWeather rechazo los datos: {response.status_code} - {detail}")
        return False
    except Exception as e:
        print(f"Error al conectar con BirdWeather: {e}")
        return False
