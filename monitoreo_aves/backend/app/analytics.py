from fastapi import APIRouter

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
def get_biodiversity_report():
    try:
        return obtener_reporte_biodiversidad()
    except Exception as e:
        print(f"Error al obtener el reporte de biodiversidad: {e}")
        return []

@router.get("/analytics/map")
def get_map_data():
    try:
        return obetenerDatosMapa()
    except Exception as e:
        print(f"Error en mapa: {e}")
        return {"error": str(e)}

@router.get("/analytics/daily-activity")
def get_daily_activity(date: str):
    try:
        return obetenerActividadDiaria(date)
    except Exception as e:
        print(f"Error generando informe diario: {e}")
        return []