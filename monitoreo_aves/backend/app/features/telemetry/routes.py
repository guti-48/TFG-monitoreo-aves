from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...domain.models import Device, NodeStorage


router = APIRouter(tags=["node-storage"])
MAX_BYTES = 2**63 - 1


class StorageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_name: str = Field(min_length=1, max_length=120)
    measured_at: AwareDatetime
    total_bytes: int = Field(gt=0, le=MAX_BYTES, strict=True)
    free_bytes: int = Field(ge=0, le=MAX_BYTES, strict=True)
    recordings_bytes: int | None = Field(default=None, ge=0, le=MAX_BYTES, strict=True)
    recordings_count: int | None = Field(default=None, ge=0, le=MAX_BYTES, strict=True)

    @model_validator(mode="after")
    def validate_measurement(self):
        if self.free_bytes > self.total_bytes:
            raise ValueError("El espacio libre supera la capacidad")
        if (self.recordings_bytes is None) != (self.recordings_count is None):
            raise ValueError("El tamano y el numero de grabaciones deben medirse juntos")
        if self.measured_at > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("La medicion esta en el futuro")
        return self


@router.post("/node/storage")
def report_storage(report: StorageReport, db: Session = Depends(get_db)):
    device = db.query(Device).filter_by(name=report.device_name).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Nodo no registrado")
    values = report.model_dump(exclude={"device_name"})
    values.update(device_id=device.id, measured_at=report.measured_at.astimezone(timezone.utc).replace(tzinfo=None),
                  received_at=datetime.now(timezone.utc).replace(tzinfo=None))
    statement = insert(NodeStorage).values(**values)
    db.execute(statement.on_conflict_do_update(
        index_elements=[NodeStorage.device_id],
        set_={key: value for key, value in values.items() if key != "device_id"},
        where=NodeStorage.measured_at < values["measured_at"],
    ))
    db.commit()
    return {"status": "ok"}


@router.get("/node/storage")
def get_storage(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    nodes = []
    for storage, device in db.query(NodeStorage, Device).join(Device, Device.id == NodeStorage.device_id).order_by(Device.name):
        age = max(0, (now - storage.measured_at).total_seconds())
        nodes.append({
            "device_name": device.name,
            "measured_at": storage.measured_at.replace(tzinfo=timezone.utc).isoformat(),
            "age_seconds": round(age), "stale": age > 900,
            "total_bytes": storage.total_bytes, "free_bytes": storage.free_bytes,
            "recordings_bytes": storage.recordings_bytes, "recordings_count": storage.recordings_count,
        })
    return {"nodes": nodes}
