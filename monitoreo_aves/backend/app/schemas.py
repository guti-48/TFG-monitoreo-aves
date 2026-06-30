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

class LearningSuggestionResponse(BaseModel):
    rule_id: int
    status: ReviewStatus
    corrected_species: Optional[str] = None
    effective_species: Optional[str] = None
    learning_confidence: float
    support_count: int
    auto_apply: bool
    reason: str

class LearningRuleResponse(BaseModel):
    id: int
    device_id: int
    original_species: str
    learned_status: ReviewStatus
    corrected_species: Optional[str] = None
    min_confidence: float
    max_confidence: float
    min_amplitude: Optional[float] = None
    max_amplitude: Optional[float] = None
    support_count: int
    active: bool
    auto_apply: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class LearningRebuildResponse(BaseModel):
    rules: int
    examples: int

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
    learned_suggestion: Optional[LearningSuggestionResponse] = None

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