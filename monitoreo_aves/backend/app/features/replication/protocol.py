from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...domain import schemas

Kind = Literal["detections", "audio_metrics"]
MediaKind = Literal["audio", "spectrogram"]
PROTOCOL_VERSION = 1
PAGE_SIZE = 100


def naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def safe_filename(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,199}", value):
        raise ValueError("Nombre de archivo no permitido")
    if not value.lower().endswith(".wav") and "." in value:
        raise ValueError("Se esperaba un WAV o su nombre sin extension")
    return value


def event_key(kind: str, payload: dict) -> str:
    values = [kind, str(payload["deployment_public_id"]), payload["device_name"],
              naive_utc(datetime.fromisoformat(str(payload["timestamp"]))).isoformat(),
              payload["filename"]]
    if kind == "detections":
        values.append(payload["species"])
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


class Context(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_name: str = Field(min_length=1, max_length=120)
    public_id: UUID
    site: schemas.SiteCreate
    started_at: datetime
    ended_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_dates(self):
        self.started_at = naive_utc(self.started_at)
        if self.ended_at is not None:
            self.ended_at = naive_utc(self.ended_at)
            if self.ended_at < self.started_at:
                raise ValueError("Fechas de despliegue inconsistentes")
        return self


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    event_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    context: Context
    data: dict

    def validate_data(self, kind: Kind) -> dict:
        schema = schemas.DetectionCreate if kind == "detections" else schemas.AudioMetricCreate
        expected = set(schema.model_fields)
        if set(self.data) - expected:
            raise ValueError("Campos de evento desconocidos")
        data = schema.model_validate(self.data).model_dump(mode="json")
        safe_filename(data["filename"])
        if (data["device_name"] != self.context.device_name
                or data["deployment_public_id"] != str(self.context.public_id)
                or data["site_code"] != self.context.site.code
                or self.event_id != event_key(kind, data)):
            raise ValueError("El evento no coincide con su contexto o identidad")
        if kind == "detections":
            start, end = data["audio_start_seconds"], data["audio_end_seconds"]
            if (start is None) != (end is None) or (start is not None and end <= start):
                raise ValueError("Ventana de audio invalida")
        return schema.model_validate(data).model_dump()


class Page(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol: Literal[1] = PROTOCOL_VERSION
    source_id: UUID
    kind: Kind
    after: int = Field(ge=0)
    records: list[Record] = Field(max_length=PAGE_SIZE)

    @model_validator(mode="after")
    def validate_order(self):
        last = self.after
        for record in self.records:
            if record.sequence <= last:
                raise ValueError("Pagina fuera de orden")
            record.validate_data(self.kind)
            last = record.sequence
        return self
