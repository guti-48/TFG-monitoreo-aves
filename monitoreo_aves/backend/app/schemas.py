from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Literal

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

#### Esquemas para revisión humana de detecciones ####
ReviewStatus = Literal[
    "unreviewed",
    "validated",
    "corrected",
    "noise",
    "doubtful",
    "discarded",
]

class DetectionReviewUpdate(BaseModel):
    status: ReviewStatus
    corrected_species: Optional[str] = None
    note: Optional[str] = None
    reviewer: Optional[str] = None

class DetectionReviewResponse(BaseModel):
    id: int
    detection_id: int
    status: ReviewStatus
    corrected_species: Optional[str] = None
    note: Optional[str] = None
    reviewer: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    updated_at: datetime

    class Config:
        from_attributes = True

class DeviceCreate(BaseModel):
    name: str
    location: str
    lat: Optional[float] = None
    lon: Optional[float] = None

    class Config:
        from_attributes = True


class DetectionResponse(BaseModel):
    id: int
    species: str
    confidence: float
    timestamp: datetime
    filename: str
    device_id: int
    amplitude: float
    review: Optional[DetectionReviewResponse] = None

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