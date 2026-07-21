from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models, database
from .config import FRONTEND_DIR, SERVER_AUDIO_DIR, SPECTOGRAM_DIR, get_cors_origins
from .analytics import router as analytics_router
from .audio_metrics import router as audio_metrics_router
from .detections import router as detections_router
from .devices import router as devices_router
from .learning_routes import router as learning_router
from .streaming import router as streaming_router
from .uploads import router as uploads_router

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


asegurar_esquema_runtime()

app = FastAPI(title="BirdMonitor API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_origin_regex=r"http://localhost:\d+|http://127\.0\.0\.1:\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(streaming_router)
app.include_router(uploads_router)
app.include_router(devices_router)
app.include_router(detections_router)
app.include_router(learning_router)
app.include_router(audio_metrics_router)
app.include_router(analytics_router)

app.mount("/spectrograms", StaticFiles(directory=SPECTOGRAM_DIR), name="spectrograms")
app.mount("/records", StaticFiles(directory=SERVER_AUDIO_DIR), name="records")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")