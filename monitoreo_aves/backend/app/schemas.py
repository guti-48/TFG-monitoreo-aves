from pydantic import BaseModel
from datetime import datetime

#### Esquemas para detecciones ####

class DetectionCreate(BaseModel):
    species: str
    confidence: float
    timestamp: datetime
    filename: str
    device_name: str
    amplitude: float


class Detection(DetectionCreate):
    id: int
    device_id: int

    class Config:
        from_attributes = True


class DeviceCreate(BaseModel):
    name: str
    location: str


class DetectionResponse(BaseModel):
    id: int
    species: str
    confidence: float
    timestamp: datetime
    filename: str
    device_id: int

    class Config:
        from_attributes = True


#Esquemas para métricas acústicas por ciclo
class AudioMetricCreate(BaseModel):
    timestamp: datetime
    filename: str
    device_name: str
    sample_rate: int
    duration: float
    rms: float
    aci: float
    adi: float
    aei: float
    bio: float
    ndsi: float
    ht: float
    hf: float
    h: float


class AudioMetricResponse(BaseModel):
    id: int
    timestamp: datetime
    filename: str
    device_id: int
    sample_rate: int
    duration: float
    rms: float
    aci: float
    adi: float
    aei: float
    bio: float
    ndsi: float
    ht: float
    hf: float
    h: float

    class Config:
        from_attributes = True