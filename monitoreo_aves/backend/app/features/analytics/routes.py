import logging

from fastapi import APIRouter, Query

try:
    from backend.analisisBiodiversidad import (
        obetenerActividadDiaria,
        obetenerDatosMapa,
        obtener_reporte_biodiversidad,
    )
except ModuleNotFoundError:
    from analisisBiodiversidad import (
        obetenerActividadDiaria,
        obetenerDatosMapa,
        obtener_reporte_biodiversidad,
    )

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/analytics/biodiversity")
def get_biodiversity_report(
    site_id: int | None = Query(default=None, ge=1),
    deployment_id: int | None = Query(default=None, ge=1),
    device_id: int | None = Query(default=None, ge=1),
):
    try:
        return obtener_reporte_biodiversidad(
            site_id=site_id,
            deployment_id=deployment_id,
            device_id=device_id,
        )
    except Exception:
        logger.exception("No se pudo generar el reporte de biodiversidad")
        return []


@router.get("/analytics/map")
def get_map_data(
    device_id: int | None = Query(default=None, ge=1),
    site_id: int | None = Query(default=None, ge=1),
    deployment_id: int | None = Query(default=None, ge=1),
):
    try:
        return obetenerDatosMapa(
            device_id=device_id,
            site_id=site_id,
            deployment_id=deployment_id,
        )
    except Exception:
        logger.exception("No se pudieron obtener los datos del mapa")
        return {"error": "No se pudo generar el mapa"}


@router.get("/analytics/daily-activity")
def get_daily_activity(
    date: str,
    site_id: int | None = Query(default=None, ge=1),
    deployment_id: int | None = Query(default=None, ge=1),
    device_id: int | None = Query(default=None, ge=1),
):
    try:
        return obetenerActividadDiaria(
            date,
            site_id=site_id,
            deployment_id=deployment_id,
            device_id=device_id,
        )
    except Exception:
        logger.exception("No se pudo generar el informe diario")
        return []
