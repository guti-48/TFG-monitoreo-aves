import os
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for path in (PROJECT_ROOT, BACKEND_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.append(path_str)

FRONTEND_DIR = PROJECT_ROOT / "frontend"
SPECTOGRAM_DIR = PROJECT_ROOT / "hardware" / "raspberry_pi" / "spectrograms"
SERVER_AUDIO_DIR = PROJECT_ROOT / "hardware" / "raspberry_pi" / "records"
STREAM_CONTROL_FILE = APP_DIR / "stream_control.json"

SERVER_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
SPECTOGRAM_DIR.mkdir(parents=True, exist_ok=True)

MAX_AUDIO_BYTES = 100 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024

ALLOWED_AUDIO_EXTENSIONS = {".wav"}
ALLOWED_IMAGE_EXTENSIONS = {".png"}

CONFIGURED_STREAM_BASE_URL = os.getenv("BIRDMONITOR_STREAM_BASE_URL")
DEFAULT_STREAM_PATH = os.getenv(
    "BIRDMONITOR_STREAM_PATH",
    "birdmonitor-audio",
).strip("/")


def get_cors_origins() -> list[str]:
    cors_origins_env = os.getenv("BIRDMONITOR_CORS_ORIGINS", "").strip()

    if cors_origins_env:
        return [
            origin.strip()
            for origin in cors_origins_env.split(",")
            if origin.strip()
        ]

    return [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost",
        "http://127.0.0.1",
    ]