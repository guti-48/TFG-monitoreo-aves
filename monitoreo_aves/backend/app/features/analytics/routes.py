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
    except Exception as e:
        print(f"Error al obtener el reporte de biodiversidad: {e}")
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
    except Exception as e:
        print(f"Error en mapa: {e}")
        return {"error": str(e)}

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
    except Exception as e:
        print(f"Error generando informe diario: {e}")
        return []