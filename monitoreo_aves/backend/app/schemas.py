from pydantic import BaseModel, Field
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
    audio_start_seconds: Optional[float] = Field(default=None, ge=0)
    audio_end_seconds: Optional[float] = Field(default=None, ge=0)


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
    audio_start_seconds: Optional[float] = None
    audio_end_seconds: Optional[float] = None
    review: Optional[DetectionReviewResponse] = None
    learned_suggestion: Optional[LearningSuggestionResponse] = None

    class Config:
        from_attributes = True


class DetectionAudioDiagnostics(BaseModel):
    status: Literal["ok", "review"]
    summary: str
    warnings: list[str]
    low_frequency_ratio: float = Field(ge=0, le=1)
    mains_hum_prominence_db: float
    bird_band_snr_db: Optional[float] = None
    high_pass_hz: float = Field(gt=0)


class DetectionReviewMediaResponse(BaseModel):
    audio_url: str
    clean_audio_url: str
    spectrogram_url: str
    clean_audio_description: str
    spectrogram_description: str
    audio_duration_seconds: float
    review_start_seconds: float
    review_end_seconds: float
    review_duration_seconds: float
    audio_start_seconds: Optional[float] = None
    audio_end_seconds: Optional[float] = None
    timing_available: bool
    diagnostics: DetectionAudioDiagnostics

#Esquemas para métricas acústicas por ciclo
class AudioMetricCreate(BaseModel):
    timestamp: datetime
    filename: str
    device_name: str
    sample_rate: int
    duration: float
    rms: float
    peak: float = Field(default=0.0, ge=0)
    clipping_ratio: float = Field(default=0.0, ge=0, le=1)
    dc_offset: float = 0.0
    noise_floor_rms: float = Field(default=0.0, ge=0)
    quality_status: str = "unknown"
    quality_detail: Optional[str] = None
    mic_device: Optional[str] = None
    birdnet_model: Optional[str] = None
    birdnet_model_version: Optional[str] = None
    birdnetlib_version: Optional[str] = None
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
    peak: Optional[float] = None
    clipping_ratio: Optional[float] = None
    dc_offset: Optional[float] = None
    noise_floor_rms: Optional[float] = None
    quality_status: Optional[str] = None
    quality_detail: Optional[str] = None
    mic_device: Optional[str] = None
    birdnet_model: Optional[str] = None
    birdnet_model_version: Optional[str] = None
    birdnetlib_version: Optional[str] = None
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