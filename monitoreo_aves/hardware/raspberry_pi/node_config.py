import os


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

NODE_NAME = os.getenv("BIRDMONITOR_NODE_NAME", "birdmonitor")
SERVER_URL = os.getenv("BIRDMONITOR_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")

NODE_LOCATION = os.getenv("BIRDMONITOR_NODE_LOCATION", "").strip()
NODE_LAT = os.getenv("BIRDMONITOR_NODE_LAT", "").strip()
NODE_LON = os.getenv("BIRDMONITOR_NODE_LON", "").strip()
AUTO_GEOLOCATION = os.getenv("BIRDMONITOR_AUTO_GEOLOCATION", "1") == "1"
GEO_CACHE_FILE = os.path.join(CURRENT_DIR, "node_location_cache.json")

MIC_DEVICE = os.getenv("BIRDMONITOR_MIC_DEVICE", "").strip()


def leer_entero_entorno(nombre, valor_por_defecto, minimo=None):
    try:
        valor = int(os.getenv(nombre, str(valor_por_defecto)))
    except ValueError:
        return valor_por_defecto

    if minimo is not None:
        return max(minimo, valor)

    return valor


def leer_float_entorno(nombre, valor_por_defecto):
    try:
        return float(os.getenv(nombre, str(valor_por_defecto)))
    except ValueError:
        return valor_por_defecto


try:
    RETENTION_DAYS = max(1, int(os.getenv("BIRDMONITOR_RETENTION_DAYS", "9")))
except ValueError:
    RETENTION_DAYS = 9

SAMPLE_RATE = 48000
DURATION = leer_entero_entorno("BIRDMONITOR_RECORD_SECONDS", 60, minimo=5)
INTERVALO = leer_entero_entorno(
    "BIRDMONITOR_RECORD_INTERVAL_SECONDS",
    300,
    minimo=DURATION,
)

UMBRAL_AVES = leer_float_entorno("BIRDMONITOR_BIRD_CONFIDENCE_THRESHOLD", 0.65)
UMBRAL_HUMANOS = leer_float_entorno("BIRDMONITOR_HUMAN_CONFIDENCE_THRESHOLD", 0.35)
UMBRAL_MOTORES = leer_float_entorno("BIRDMONITOR_MOTOR_CONFIDENCE_THRESHOLD", 0.40)
UMBRAL_RUIDO_ALTO = leer_float_entorno("BIRDMONITOR_HIGH_NOISE_RMS_THRESHOLD", 0.02)

BASER_DIR = CURRENT_DIR
OUTPUT_FOLDER_AUDIO = os.path.join(BASER_DIR, "records")
OUTPUT_FOLDER_IMG = os.path.join(BASER_DIR, "spectrograms")
CSV_BACKUP = os.path.join(BASER_DIR, "backup_data.csv")
OUTBOX_DB = os.path.join(BASER_DIR, "offline_outbox.db")

os.makedirs(OUTPUT_FOLDER_AUDIO, exist_ok=True)
os.makedirs(OUTPUT_FOLDER_IMG, exist_ok=True)