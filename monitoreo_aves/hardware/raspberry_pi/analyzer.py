import os, requests
from datetime import datetime
from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

# Parámetros de análisis BirdNET
MIN_CONF   = 0.5   # confianza mínima para aceptar una detección
OVERLAP    = 1.5   # solapamiento de ventana en segundos
SENSITIVITY = 1.25  # sensibilidad para aves en la lejanía

#### CONFIGURACION ####
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(CURRENT_DIR, "model", "birdnet_model.tflite")
LABELS_PATH = os.path.join(CURRENT_DIR, "model", "birdnet_labels.txt")

class BirdAnalyzer:
    def __init__(self):
        # Cargamos el model TFLite que nos permite filtros de ubicacion y fecha
        print("Motor de BirdNet Cargando...")
        try: 
            self.analyzer = Analyzer()
            print("El modelo BirdNet se ha cargado correctamente.")
        except Exception as e:
            print(f"[ERROR] No se ha podido cargar el modelo BirdNet: {e}")

        #Aqui detectaremos la ubicacion mediante geolocalizacion IP
        self.lat, self.lon = self.get_auto_location()
        print(f"Ubicación detectada: Latitud {self.lat}, Longitud {self.lon}")        

    def get_auto_location(self):
        """Aqui consulatremos una APi de localizacion basada en la IP publica"""
        try:
            # Timeout de 5s para no bloquear el arranque si no hay red
            response = requests.get('http://ip-api.com/json/', timeout=5)
            data = response.json()
            if data['status'] == 'success':
                # Devolvemos las coordenadas reales detectadas
                return data['lat'], data['lon']
        except Exception as e:
            print(f"[WARN] Fallo en geolocalización ({e}).")
        
        # FALLBACK: Si no hay internet o falla la API, usamos coordenadas centrales
        # (Madrid) para que el software no se rompa.
        print("[WARN] Usando ubicación por defecto (Centro de España).")
        return 40.4168, -3.7038

    def _load_labels(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f.readlines()]
        
    def predict(self, audio_path):
        """
        analiza el audio usando la librería oficiale e implementamos filtros avanzados
        detectando multiples especies y ruidos de fondo
        """
        if self.analyzer is None:
            print("[ERROR] Modelo no disponible — se omite el análisis.")
            return []

        try:
            recording = Recording(
                self.analyzer,
                audio_path,
                lat=self.lat,
                lon=self.lon,
                date=datetime.now(),    # filtra aves migratorias según la fecha
                min_conf=MIN_CONF,
                overlap=OVERLAP,
                sensitivity=SENSITIVITY,
            )
            recording.analyze()

            return [
                {
                    "species":    d['common_name'],
                    "confidence": d['confidence'],
                    "time_start": d['start_time'],
                    "time_end":   d['end_time'],
                }
                for d in recording.detections
            ]

        except Exception as e:
            print(f"[ERROR] Fallo en análisis de audio: {e}")
            return []