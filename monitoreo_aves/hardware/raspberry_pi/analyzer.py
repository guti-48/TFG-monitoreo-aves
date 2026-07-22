from datetime import datetime
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

from node_config import (
    BIRDNET_MIN_CONFIDENCE,
    BIRDNET_MODEL_VERSION,
    BIRDNET_OVERLAP,
    BIRDNET_SENSITIVITY,
)


DEFAULT_LAT = 40.4168
DEFAULT_LON = -3.7038


def _coordenadas_validas(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


class BirdAnalyzer:
    def __init__(self, lat=None, lon=None):
        print("Motor de BirdNET cargando...")
        self.analyzer = None

        if _coordenadas_validas(lat, lon):
            self.lat = float(lat)
            self.lon = float(lon)
            self.location_source = "node"
        else:
            self.lat = DEFAULT_LAT
            self.lon = DEFAULT_LON
            self.location_source = "default"
            print(
                "[WARN] BirdNET no recibio coordenadas validas del nodo; "
                "se usa la ubicacion de respaldo del centro de Espana."
            )

        try:
            self.analyzer = Analyzer(version=BIRDNET_MODEL_VERSION)
            info = self.get_model_info()
            print(
                "BirdNET cargado: "
                f"{info['model_name']} v{info['model_version']} "
                f"(birdnetlib {info['birdnetlib_version']}, "
                f"modelo={info['model_file']})."
            )
        except Exception as exc:
            print(f"[ERROR] No se ha podido cargar BirdNET: {exc}")

        print(
            f"Ubicacion usada por BirdNET: {self.lat}, {self.lon} "
            f"(origen={self.location_source})."
        )

    def get_model_info(self):
        """Devuelve metadatos reproducibles del motor activo para telemetria."""
        try:
            birdnetlib_version = package_version("birdnetlib")
        except PackageNotFoundError:
            birdnetlib_version = "unknown"

        if self.analyzer is None:
            return {
                "model_name": "BirdNET-Analyzer",
                "model_version": BIRDNET_MODEL_VERSION,
                "model_file": None,
                "birdnetlib_version": birdnetlib_version,
            }

        model_path = getattr(self.analyzer, "model_path", None)
        return {
            "model_name": getattr(self.analyzer, "model_name", "BirdNET-Analyzer"),
            "model_version": str(
                getattr(self.analyzer, "version", BIRDNET_MODEL_VERSION)
            ),
            "model_file": Path(model_path).name if model_path else None,
            "birdnetlib_version": birdnetlib_version,
        }

    def predict(self, audio_path):
        """Analiza el WAV con BirdNET y conserva todos los filtros posteriores."""
        if self.analyzer is None:
            print("[ERROR] Modelo no disponible; se omite el analisis.")
            return []

        try:
            recording = Recording(
                self.analyzer,
                audio_path,
                lat=self.lat,
                lon=self.lon,
                date=datetime.now(),
                min_conf=BIRDNET_MIN_CONFIDENCE,
                overlap=BIRDNET_OVERLAP,
                sensitivity=BIRDNET_SENSITIVITY,
            )
            recording.analyze()

            return [
                {
                    "species": detection["common_name"],
                    "scientific_name": detection["scientific_name"],
                    "confidence": detection["confidence"],
                    "time_start": detection["start_time"],
                    "time_end": detection["end_time"],
                }
                for detection in recording.detections
            ]

        except Exception as exc:
            print(f"[ERROR] Fallo en analisis de audio: {exc}")
            return []