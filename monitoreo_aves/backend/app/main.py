from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .core import database
from .core.config import FRONTEND_DIR, SERVER_AUDIO_DIR, SPECTOGRAM_DIR, get_cors_origins
from .core.network import get_network_settings, network_middleware
from .core.security import get_security_settings, security_middleware
from .domain import models
from .features.analytics.routes import router as analytics_router
from .features.audio_metrics.routes import router as audio_metrics_router
from .features.auth.routes import router as auth_router
from .features.detections.routes import router as detections_router
from .features.devices.routes import router as devices_router
from .features.exports.routes import router as exports_router
from .features.learning.routes import router as learning_router
from .features.streaming.routes import router as streaming_router
from .features.streaming.security import (
    get_stream_security_settings,
    router as stream_security_router,
)
from .features.uploads.routes import router as uploads_router

models.Base.metadata.create_all(bind=database.engine)


def asegurar_esquema_runtime() -> None:
    with database.engine.begin() as conn:
        columnas_devices = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(devices)").fetchall()
        }

        if "lat" not in columnas_devices:
            conn.exec_driver_sql("ALTER TABLE devices ADD COLUMN lat FLOAT")

        if "lon" not in columnas_devices:
            conn.exec_driver_sql("ALTER TABLE devices ADD COLUMN lon FLOAT")

        if "location_source" not in columnas_devices:
            conn.exec_driver_sql(
                "ALTER TABLE devices ADD COLUMN location_source VARCHAR"
            )

        if "location_accuracy_m" not in columnas_devices:
            conn.exec_driver_sql(
                "ALTER TABLE devices ADD COLUMN location_accuracy_m FLOAT"
            )

        columnas_detections = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(detections)").fetchall()
        }

        if "audio_start_seconds" not in columnas_detections:
            conn.exec_driver_sql(
                "ALTER TABLE detections ADD COLUMN audio_start_seconds FLOAT"
            )

        if "audio_end_seconds" not in columnas_detections:
            conn.exec_driver_sql(
                "ALTER TABLE detections ADD COLUMN audio_end_seconds FLOAT"
            )

        columnas_audio_metrics = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(audio_metrics)").fetchall()
        }
        nuevas_columnas_audio = {
            "peak": "FLOAT",
            "clipping_ratio": "FLOAT",
            "dc_offset": "FLOAT",
            "noise_floor_rms": "FLOAT",
            "quality_status": "VARCHAR",
            "quality_detail": "VARCHAR",
            "mic_device": "VARCHAR",
            "birdnet_model": "VARCHAR",
            "birdnet_model_version": "VARCHAR",
            "birdnetlib_version": "VARCHAR",
            "acoustic_metrics_version": "VARCHAR",
        }
        for nombre, tipo in nuevas_columnas_audio.items():
            if nombre not in columnas_audio_metrics:
                conn.exec_driver_sql(
                    f"ALTER TABLE audio_metrics ADD COLUMN {nombre} {tipo}"
                )


asegurar_esquema_runtime()

app = FastAPI(title="BirdMonitor API", version="1.0")
app.middleware("http")(security_middleware)
app.middleware("http")(network_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_origin_regex=r"http://localhost:\d+|http://127\.0\.0\.1:\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(stream_security_router)
app.include_router(streaming_router)
app.include_router(uploads_router)
app.include_router(devices_router)
app.include_router(exports_router)
app.include_router(detections_router)
app.include_router(learning_router)
app.include_router(audio_metrics_router)
app.include_router(analytics_router)


@app.get("/health", include_in_schema=False)
def health():
    security = get_security_settings()
    stream_security = get_stream_security_settings()
    network = get_network_settings()
    return {
        "status": "ok",
        "network_mode": network.mode,
        "network_configured": network.configured,
        "security": security.mode,
        "security_configured": security.configured,
        "stream_security": stream_security.mode,
        "stream_security_configured": stream_security.configured,
    }


app.mount("/spectrograms", StaticFiles(directory=SPECTOGRAM_DIR), name="spectrograms")
app.mount("/records", StaticFiles(directory=SERVER_AUDIO_DIR), name="records")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
