from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from datetime import datetime
from typing import Optional, Literal
from uuid import UUID


LocationSource = Literal["manual", "gps", "ip_geolocation", "unknown"]

#### Esquemas para detecciones ####

class DetectionCreate(BaseModel):
    species: str
    confidence: float
    timestamp: datetime
    filename: str
    device_name: str
    amplitude: float
    site_code: Optional[str] = Field(
        default=None,
        pattern=r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    )
    deployment_public_id: Optional[UUID] = None
    audio_start_seconds: Optional[float] = Field(default=None, ge=0)
    audio_end_seconds: Optional[float] = Field(default=None, ge=0)


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
    model_config = ConfigDict(from_attributes=True)

    id: int
    detection_id: int
    status: ReviewStatus
    corrected_species: Optional[str] = None
    note: Optional[str] = None
    reviewer: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    updated_at: datetime

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
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    site_id: Optional[int] = None
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

class LearningRebuildResponse(BaseModel):
    rules: int
    examples: int

class DeviceCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    location: str
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    location_source: Optional[LocationSource] = None
    location_accuracy_m: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validar_coordenadas_completas(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat y lon deben proporcionarse juntas")
        if self.location_accuracy_m is not None and self.lat is None:
            raise ValueError(
                "location_accuracy_m requiere coordenadas lat y lon"
            )
        return self


class SiteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        pattern=r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
        min_length=1,
        max_length=63,
    )
    name: str = Field(min_length=1, max_length=200)
    municipality: Optional[str] = Field(default=None, max_length=120)
    region: Optional[str] = Field(default=None, max_length=120)
    country_code: str = Field(default="ES", pattern=r"^[A-Z]{2}$")
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    location_source: LocationSource = "unknown"
    location_accuracy_m: Optional[float] = Field(default=None, ge=0)
    timezone: str = Field(default="Europe/Madrid", min_length=1, max_length=80)

    @field_validator(
        "code",
        "name",
        "municipality",
        "region",
        "timezone",
        mode="before",
    )
    @classmethod
    def strip_site_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country_code(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_site_coordinates(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat y lon deben proporcionarse juntas")
        if self.location_accuracy_m is not None and self.lat is None:
            raise ValueError(
                "location_accuracy_m requiere coordenadas lat y lon"
            )
        return self


class SiteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    municipality: Optional[str] = Field(default=None, max_length=120)
    region: Optional[str] = Field(default=None, max_length=120)
    country_code: Optional[str] = Field(default=None, pattern=r"^[A-Z]{2}$")
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    location_source: Optional[LocationSource] = None
    location_accuracy_m: Optional[float] = Field(default=None, ge=0)
    timezone: Optional[str] = Field(default=None, min_length=1, max_length=80)
    archived: Optional[bool] = None

    @field_validator(
        "name",
        "municipality",
        "region",
        "timezone",
        mode="before",
    )
    @classmethod
    def strip_site_update_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_site_update_country(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_updated_coordinates(self):
        lat_set = "lat" in self.model_fields_set
        lon_set = "lon" in self.model_fields_set
        if lat_set != lon_set:
            raise ValueError("lat y lon deben actualizarse juntas")
        return self


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    municipality: Optional[str] = None
    region: Optional[str] = None
    country_code: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    location_source: LocationSource
    location_accuracy_m: Optional[float] = None
    timezone: str
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None
    deployment_count: int = 0
    active_deployment_count: int = 0
    detection_count: int = 0
    audio_metric_count: int = 0


class DeploymentActivate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_name: str = Field(min_length=1, max_length=120)
    deployment_public_id: UUID
    site: SiteCreate
    started_at: datetime
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("device_name", "notes", mode="before")
    @classmethod
    def strip_deployment_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class DeploymentResponse(BaseModel):
    id: int
    public_id: UUID
    device_id: int
    device_name: str
    site_id: int
    site_code: str
    site_name: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    active: bool
    created_at: datetime
    updated_at: datetime
    notes: Optional[str] = None


NodeLocationCommandStatus = Literal[
    "pending",
    "delivered",
    "applied",
    "failed",
    "cancelled",
]


class NodeLocationCommandCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_site_id: int = Field(ge=1)
    confirm_site_code: str = Field(
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    )
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("confirm_site_code", "notes", mode="before")
    @classmethod
    def strip_location_command_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class NodeLocationCommandAck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_public_id: UUID
    status: Literal["applied", "failed"]
    deployment_started_at: Optional[datetime] = None
    error_detail: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("error_detail", mode="before")
    @classmethod
    def strip_location_command_error(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_location_command_ack(self):
        if self.status == "applied":
            if self.deployment_started_at is None:
                raise ValueError(
                    "deployment_started_at es obligatorio al aplicar la orden"
                )
            if (
                self.deployment_started_at.tzinfo is None
                or self.deployment_started_at.utcoffset() is None
            ):
                raise ValueError(
                    "deployment_started_at debe incluir zona horaria"
                )
        elif not self.error_detail:
            raise ValueError("error_detail es obligatorio si la orden falla")
        return self


class NodeLocationCommandResponse(BaseModel):
    id: int
    public_id: UUID
    device_id: int
    device_name: str
    target_site_id: int
    target_site_code: str
    target_site_name: str
    target_site_municipality: Optional[str] = None
    target_site_region: Optional[str] = None
    target_site_country_code: str
    target_site_lat: float
    target_site_lon: float
    target_site_location_source: LocationSource
    target_site_location_accuracy_m: Optional[float] = None
    target_site_timezone: str
    deployment_public_id: UUID
    status: NodeLocationCommandStatus
    requested_by: str
    requested_at: datetime
    delivered_at: Optional[datetime] = None
    deployment_started_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    delivery_count: int
    notes: Optional[str] = None
    error_detail: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class DetectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    species: str
    confidence: float
    timestamp: datetime
    filename: str
    device_id: int
    deployment_id: Optional[int] = None
    deployment_public_id: Optional[UUID] = None
    site_id: Optional[int] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    amplitude: float
    audio_start_seconds: Optional[float] = None
    audio_end_seconds: Optional[float] = None
    review: Optional[DetectionReviewResponse] = None
    learned_suggestion: Optional[LearningSuggestionResponse] = None

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
    spectrogram_url: str
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
    site_code: Optional[str] = Field(
        default=None,
        pattern=r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    )
    deployment_public_id: Optional[UUID] = None
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
    acoustic_metrics_version: str = "legacy-v1"
    aci: float
    adi: float
    aei: float
    bio: float
    ndsi: float
    ht: float
    hf: float
    h: float

class AudioMetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    filename: str
    device_id: int
    deployment_id: Optional[int] = None
    deployment_public_id: Optional[UUID] = None
    site_id: Optional[int] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
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
    acoustic_metrics_version: Optional[str] = None
    aci: float
    adi: float
    aei: float
    bio: float
    ndsi: float
    ht: float
    hf: float
    h: float