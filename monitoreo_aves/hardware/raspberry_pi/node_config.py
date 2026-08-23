import os


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_ENV_FILE = os.path.join(CURRENT_DIR, "birdmonitor.env")


def cargar_env_local(path=LOCAL_ENV_FILE):
    """Carga KEY=VALUE locales sin sobrescribir variables ya definidas."""
    if not os.path.isfile(path):
        return

    try:
        with open(path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()

                if not line or line.startswith("#") or "=" not in line:
                    continue

                if line.startswith("export "):
                    line = line[len("export "):].strip()

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                if key:
                    os.environ.setdefault(key, value)
    except OSError as exc:
        print(f"No se pudo cargar la configuracion local {path}: {exc}")


cargar_env_local()

NODE_NAME = os.getenv("BIRDMONITOR_NODE_NAME", "birdmonitor")
SERVER_URL = os.getenv("BIRDMONITOR_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")
NODE_API_TOKEN = os.getenv("BIRDMONITOR_NODE_API_TOKEN", "").strip()


def getBackendAuthHeaders():
    """Cabecera Bearer del nodo; vacia durante una migracion sin token."""
    if not NODE_API_TOKEN:
        return {}
    return {"Authorization": f"Bearer {NODE_API_TOKEN}"}

NODE_LOCATION = os.getenv("BIRDMONITOR_NODE_LOCATION", "").strip()
NODE_LAT = os.getenv("BIRDMONITOR_NODE_LAT", "").strip()
NODE_LON = os.getenv("BIRDMONITOR_NODE_LON", "").strip()
SITE_CODE = os.getenv("BIRDMONITOR_SITE_CODE", "").strip().lower()
SITE_NAME = os.getenv(
    "BIRDMONITOR_SITE_NAME",
    NODE_LOCATION,
).strip()
SITE_MUNICIPALITY = os.getenv("BIRDMONITOR_SITE_MUNICIPALITY", "").strip()
SITE_REGION = os.getenv("BIRDMONITOR_SITE_REGION", "").strip()
SITE_COUNTRY_CODE = os.getenv(
    "BIRDMONITOR_SITE_COUNTRY_CODE",
    "ES",
).strip().upper()
SITE_TIMEZONE = os.getenv(
    "BIRDMONITOR_SITE_TIMEZONE",
    "Europe/Madrid",
).strip()
SITE_LOCATION_SOURCE = os.getenv(
    "BIRDMONITOR_SITE_LOCATION_SOURCE",
    "manual",
).strip().lower()
SITE_LOCATION_ACCURACY_M = os.getenv(
    "BIRDMONITOR_SITE_LOCATION_ACCURACY_M",
    "",
).strip()
DEPLOYMENT_ID = os.getenv("BIRDMONITOR_DEPLOYMENT_ID", "").strip()
DEPLOYMENT_STARTED_AT = os.getenv(
    "BIRDMONITOR_DEPLOYMENT_STARTED_AT",
    "",
).strip()
DEPLOYMENT_NOTES = os.getenv("BIRDMONITOR_DEPLOYMENT_NOTES", "").strip()
LEGACY_SITE_CODE = os.getenv(
    "BIRDMONITOR_LEGACY_SITE_CODE",
    "",
).strip().lower()
LEGACY_DEPLOYMENT_ID = os.getenv(
    "BIRDMONITOR_LEGACY_DEPLOYMENT_ID",
    "",
).strip()
AUTO_GEOLOCATION = os.getenv("BIRDMONITOR_AUTO_GEOLOCATION", "0") == "1"
GEO_CACHE_FILE = os.path.join(CURRENT_DIR, "node_location_cache.json")

MIC_DEVICE = os.getenv("BIRDMONITOR_MIC_DEVICE", "").strip()
MIC_ALSA_CARD = os.getenv("BIRDMONITOR_MIC_ALSA_CARD", "").strip()
MIC_CAPTURE_VOLUME = os.getenv("BIRDMONITOR_MIC_CAPTURE_VOLUME", "").strip()
MIC_AUTO_GAIN = os.getenv("BIRDMONITOR_MIC_AUTO_GAIN", "").strip().lower()


def leer_entero_entorno(nombre, valor_por_defecto, minimo=None):
    try:
        valor = int(os.getenv(nombre, str(valor_por_defecto)))
    except ValueError:
        return valor_por_defecto

    if minimo is not None:
        return max(minimo, valor)

    return valor


def leer_float_entorno(nombre, valor_por_defecto, minimo=None, maximo=None):
    try:
        valor = float(os.getenv(nombre, str(valor_por_defecto)))
    except ValueError:
        valor = valor_por_defecto

    if minimo is not None:
        valor = max(minimo, valor)
    if maximo is not None:
        valor = min(maximo, valor)
    return valor


def limitar(valor, minimo=None, maximo=None):
    if minimo is not None:
        valor = max(minimo, valor)
    if maximo is not None:
        valor = min(maximo, valor)
    return valor


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

UMBRAL_AVES = limitar(
    leer_float_entorno("BIRDMONITOR_BIRD_CONFIDENCE_THRESHOLD", 0.65),
    0.01,
    0.99,
)
UMBRAL_HUMANOS = limitar(
    leer_float_entorno("BIRDMONITOR_HUMAN_CONFIDENCE_THRESHOLD", 0.35),
    0.01,
    0.99,
)
UMBRAL_MOTORES = limitar(
    leer_float_entorno("BIRDMONITOR_MOTOR_CONFIDENCE_THRESHOLD", 0.40),
    0.01,
    0.99,
)
UMBRAL_RUIDO_ALTO = max(
    0.0,
    leer_float_entorno("BIRDMONITOR_HIGH_NOISE_RMS_THRESHOLD", 0.02),
)

# BirdNET debe conservar primero cualquier resultado que pueda superar alguno de
# los filtros especializados de mainNode.py. De este modo los umbrales de humano
# y motor no quedan anulados por un umbral interno mas alto.
BIRDNET_MIN_CONFIDENCE = min(UMBRAL_AVES, UMBRAL_HUMANOS, UMBRAL_MOTORES)
BIRDNET_OVERLAP = limitar(
    leer_float_entorno("BIRDMONITOR_BIRDNET_OVERLAP_SECONDS", 1.5),
    0.0,
    2.9,
)
BIRDNET_SENSITIVITY = limitar(
    leer_float_entorno("BIRDMONITOR_BIRDNET_SENSITIVITY", 1.25),
    0.5,
    1.5,
)
BIRDNET_MODEL_VERSION = os.getenv("BIRDMONITOR_BIRDNET_MODEL_VERSION", "2.4").strip() or "2.4"

# Limites usados solamente para diagnosticar la captura. No modifican el audio
# ni aumentan la carga de inferencia.
MIC_MIN_RMS = max(0.0, leer_float_entorno("BIRDMONITOR_MIC_MIN_RMS", 0.001))
MIC_MAX_CLIPPING_RATIO = limitar(
    leer_float_entorno("BIRDMONITOR_MIC_MAX_CLIPPING_RATIO", 0.001),
    0.0,
    1.0,
)
MIC_MAX_DC_OFFSET = limitar(
    leer_float_entorno("BIRDMONITOR_MIC_MAX_DC_OFFSET", 0.02),
    0.0,
    1.0,
)
MIC_CLIPPING_LEVEL = limitar(
    leer_float_entorno("BIRDMONITOR_MIC_CLIPPING_LEVEL", 0.99),
    0.5,
    1.0,
)

BASER_DIR = CURRENT_DIR
OUTPUT_FOLDER_AUDIO = os.path.join(BASER_DIR, "records")
OUTPUT_FOLDER_IMG = os.path.join(BASER_DIR, "spectrograms")
CSV_BACKUP = os.path.join(BASER_DIR, "backup_data.csv")
OUTBOX_DB = os.path.join(BASER_DIR, "offline_outbox.db")
DEPLOYMENT_STATE_FILE = os.getenv(
    "BIRDMONITOR_DEPLOYMENT_STATE_FILE",
    os.path.join(BASER_DIR, "deployment_state.json"),
).strip()

os.makedirs(OUTPUT_FOLDER_AUDIO, exist_ok=True)
os.makedirs(OUTPUT_FOLDER_IMG, exist_ok=True)