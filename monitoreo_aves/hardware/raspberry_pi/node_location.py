import json

import requests

from node_config import (
    AUTO_GEOLOCATION,
    GEO_CACHE_FILE,
    NODE_LAT,
    NODE_LOCATION,
    NODE_LON,
)


def _parsearCoordenada(value, nombre, minimo, maximo):
    if not value:
        return None

    try:
        coordenada = float(value)
    except (TypeError, ValueError):
        print(f"Coordenada manual {nombre} invalida: {value!r}.")
        return None

    if not minimo <= coordenada <= maximo:
        print(f"Coordenada manual {nombre} fuera de rango: {coordenada}.")
        return None
    return coordenada


def cargarUbicacionCache():
    """Carga la ultima ubicacion conocida desde disco."""
    try:
        with open(GEO_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"No se pudo leer cache de ubicacion: {e}")
        return None


def guardarUbicacionCache(data):
    """Guarda la ubicacion detectada para reutilizarla si no hay red."""
    try:
        with open(GEO_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"No se pudo guardar cache de ubicacion: {e}")


def detectarUbicacionPorIP():
    """
    Detecta ubicacion aproximada usando la IP publica de salida a Internet.
    No usa IP local ni IP de Tailscale.
    """
    url = (
        "http://ip-api.com/json/"
        "?fields=status,message,country,regionName,city,lat,lon,query"
        "&lang=es"
    )

    try:
        print("Detectando ubicacion aproximada por IP publica...")
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()

        if data.get("status") != "success":
            print(f"No se pudo geolocalizar por IP: {data.get('message', 'respuesta invalida')}")
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
            "source": "ip_geolocation",
        }

        guardarUbicacionCache(resultado)

        print(f"Ubicacion detectada: {location}")
        print(f"Coordenadas aproximadas: {resultado['lat']}, {resultado['lon']}")
        return resultado

    except Exception as e:
        print(f"Error detectando ubicacion por IP: {e}")
        return None


def obtenerUbicacionNodo():
    """
    Prioridad: manual -> geolocalizacion por IP -> cache local -> desconocido.
    """
    if NODE_LOCATION:
        return {
            "location": NODE_LOCATION,
            "lat": _parsearCoordenada(NODE_LAT, "latitud", -90.0, 90.0),
            "lon": _parsearCoordenada(NODE_LON, "longitud", -180.0, 180.0),
            "source": "manual",
        }

    if AUTO_GEOLOCATION:
        geo = detectarUbicacionPorIP()
        if geo:
            return geo

    cache = cargarUbicacionCache()
    if cache:
        print(f"Usando ubicacion cacheada: {cache.get('location')}")
        return cache

    return {
        "location": "Ubicacion_Desconocida",
        "lat": None,
        "lon": None,
        "source": "unknown",
    }