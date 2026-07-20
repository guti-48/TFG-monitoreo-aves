import os

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
    "https://app.birdweather.com/api/v1/stations/detections",
).strip()


def enviarDatosBirdWeather(species, confidence, lat, lon, timestamp):
    """Envia datos de aves a BirdWeather."""
    if not BIRDWEATHER_ENABLED or not BIRDWEATHER_TOKEN:
        return

    if lat is None or lon is None:
        print("No se envia a BirdWeather: faltan coordenadas del nodo.")
        return

    cleanSpecies = species.split("_")[1] if "_" in species else species

    datos_publicos = {
        "token": BIRDWEATHER_TOKEN,
        "timestamp": timestamp,
        "species": cleanSpecies,
        "confidence": confidence,
        "lat": lat,
        "lon": lon,
        "source": "birdmonitor",
    }

    try:
        response = requests.post(
            BIRDWEATHER_URL,
            json=datos_publicos,
            headers={"User-Agent": "BirdMonitor-TFG/1.0"},
            timeout=15,
        )
        if response.status_code in (200, 201):
            print("Datos enviados a BirdWeather correctamente.")
        else:
            print(f"BirdWeather rechazo los datos: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error al conectar con BirdWeather: {e}")