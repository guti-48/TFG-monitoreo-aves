from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from ..core.database import Base
from datetime import datetime, timezone


class SchemaMigration(Base):
    """Registro de migraciones de datos aplicadas de forma idempotente."""

    __tablename__ = "schema_migrations"

    version = Column(String, primary_key=True)
    applied_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    description = Column(String, nullable=False)

'''
Esta clase representa los nodos/dispositivos registrados en la base de datos.
'''
class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    location = Column(String)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    location_source = Column(String, nullable=True)
    location_accuracy_m = Column(Float, nullable=True)

    detections = relationship("Detection", back_populates="device")
    audio_metrics = relationship("AudioMetric", back_populates="device")
    deployments = relationship("Deployment", back_populates="device")


class Site(Base):
    """Lugar geográfico estable que puede reutilizarse en varias campañas."""

    __tablename__ = "sites"
    __table_args__ = (
        UniqueConstraint("code", name="uq_sites_code"),
        CheckConstraint(
            "(lat IS NULL AND lon IS NULL) OR "
            "(lat IS NOT NULL AND lon IS NOT NULL)",
            name="ck_sites_coordinate_pair",
        ),
        CheckConstraint(
            "lat IS NULL OR (lat >= -90 AND lat <= 90)",
            name="ck_sites_latitude_range",
        ),
        CheckConstraint(
            "lon IS NULL OR (lon >= -180 AND lon <= 180)",
            name="ck_sites_longitude_range",
        ),
        CheckConstraint(
            "location_accuracy_m IS NULL OR location_accuracy_m >= 0",
            name="ck_sites_location_accuracy",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(63), nullable=False, index=True)
    name = Column(String, nullable=False)
    municipality = Column(String, nullable=True)
    region = Column(String, nullable=True)
    country_code = Column(String(2), nullable=False, default="ES")
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    location_source = Column(String, nullable=False, default="unknown")
    location_accuracy_m = Column(Float, nullable=True)
    timezone = Column(String, nullable=False, default="Europe/Madrid")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    archived_at = Column(DateTime, nullable=True)

    deployments = relationship("Deployment", back_populates="site")
    learning_rules = relationship("LearningRule", back_populates="site")


class Deployment(Base):
    """Periodo durante el cual un dispositivo permanece instalado en un sitio."""

    __tablename__ = "deployments"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_deployments_public_id"),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="ck_deployments_time_order",
        ),
        Index(
            "uq_deployments_active_device",
            "device_id",
            unique=True,
            sqlite_where=text("ended_at IS NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = Column(String(36), nullable=False, index=True)
    device_id = Column(
        Integer,
        ForeignKey("devices.id"),
        nullable=False,
        index=True,
    )
    site_id = Column(
        Integer,
        ForeignKey("sites.id"),
        nullable=False,
        index=True,
    )
    started_at = Column(DateTime, nullable=False, index=True)
    ended_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    notes = Column(String, nullable=True)

    device = relationship("Device", back_populates="deployments")
    site = relationship("Site", back_populates="deployments")
    detections = relationship("Detection", back_populates="deployment")
    audio_metrics = relationship("AudioMetric", back_populates="deployment")

'''
Esta clase representa la tabla para almacenar detecciones biológicas o acústicas relevantes.
'''
class Detection(Base):
    __tablename__ = "detections"
    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "timestamp",
            "species",
            "filename",
            name="uq_detection_deployment_event",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    species = Column(String, index=True)
    confidence = Column(Float)
    filename = Column(String)
    amplitude = Column(Float, default=0.0)
    audio_start_seconds = Column(Float, nullable=True)
    audio_end_seconds = Column(Float, nullable=True)

    device_id = Column(Integer, ForeignKey("devices.id"))
    device = relationship("Device", back_populates="detections")
    deployment_id = Column(
        Integer,
        ForeignKey("deployments.id"),
        nullable=True,
        index=True,
    )
    deployment = relationship("Deployment", back_populates="detections")

    review = relationship(
        "DetectionReview",
        back_populates="detection",
        uselist=False,
        cascade="all, delete-orphan"
    )

'''
Esta clase resperenta la revision humana sobre el una detreccion automatica
No sobreescribe simplemente añade una capa de validacion
'''
class DetectionReview(Base):
    __tablename__ = "detection_reviews"
    __table_args__ = (
        UniqueConstraint("detection_id", name="uq_detection_review_detection_id"),
    )

    id = Column(Integer, primary_key=True, index=True)

    detection_id = Column(
        Integer,
        ForeignKey("detections.id"),
        nullable=False,
        unique=True,
        index=True
    )

    status = Column(String, default="unreviewed", nullable=False, index=True)

    corrected_species = Column(String, nullable=True)
    note = Column(String, nullable=True)
    reviewer = Column(String, nullable=True)

    reviewed_at = Column(DateTime, nullable=False) 
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    detection = relationship("Detection", back_populates="review")

'''
Esta clase representa una muestra acústica agregada por ciclo de grabación.
No equivale a una detección de ave: guarda métricas del paisaje sonoro aunque no haya detecciones.
'''
class LearningRule(Base):
    __tablename__ = "learning_rules"

    id = Column(Integer, primary_key=True, index=True)

    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=True, index=True)
    original_species = Column(String, nullable=False, index=True)
    learned_status = Column(String, nullable=False, index=True)
    corrected_species = Column(String, nullable=True, index=True)

    min_confidence = Column(Float, nullable=False, default=0.0)
    max_confidence = Column(Float, nullable=False, default=1.0)
    min_amplitude = Column(Float, nullable=True)
    max_amplitude = Column(Float, nullable=True)

    support_count = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=False, index=True)
    auto_apply = Column(Boolean, nullable=False, default=False, index=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    device = relationship("Device")
    site = relationship("Site", back_populates="learning_rules")
    examples = relationship(
        "LearningExample",
        back_populates="rule",
        cascade="all, delete-orphan"
    )

class LearningExample(Base):
    __tablename__ = "learning_examples"
    __table_args__ = (
        UniqueConstraint("detection_id", name="uq_learning_example_detection_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    detection_id = Column(
        Integer,
        ForeignKey("detections.id"),
        nullable=False,
        unique=True,
        index=True
    )
    rule_id = Column(Integer, ForeignKey("learning_rules.id"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)

    original_species = Column(String, nullable=False, index=True)
    learned_status = Column(String, nullable=False, index=True)
    corrected_species = Column(String, nullable=True, index=True)
    confidence = Column(Float, nullable=False)
    amplitude = Column(Float, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    detection = relationship("Detection")
    device = relationship("Device")
    rule = relationship("LearningRule", back_populates="examples")

class AudioMetric(Base):
    __tablename__ = "audio_metrics"
    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "timestamp",
            "filename",
            name="uq_audio_metric_deployment_event",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    filename = Column(String, index=True)

    sample_rate = Column(Integer)
    duration = Column(Float)
    rms = Column(Float, default=0.0)
    peak = Column(Float, default=0.0)
    clipping_ratio = Column(Float, default=0.0)
    dc_offset = Column(Float, default=0.0)
    noise_floor_rms = Column(Float, default=0.0)
    quality_status = Column(String, default="unknown", index=True)
    quality_detail = Column(String, nullable=True)
    mic_device = Column(String, nullable=True)

    birdnet_model = Column(String, nullable=True)
    birdnet_model_version = Column(String, nullable=True)
    birdnetlib_version = Column(String, nullable=True)
    acoustic_metrics_version = Column(String, nullable=True, index=True)

    aci = Column(Float, default=0.0)
    adi = Column(Float, default=0.0)
    aei = Column(Float, default=0.0)
    bio = Column(Float, default=0.0)
    ndsi = Column(Float, default=0.0)
    ht = Column(Float, default=0.0)
    hf = Column(Float, default=0.0)
    h = Column(Float, default=0.0)

    device_id = Column(Integer, ForeignKey("devices.id"))
    device = relationship("Device", back_populates="audio_metrics")
    deployment_id = Column(
        Integer,
        ForeignKey("deployments.id"),
        nullable=True,
        index=True,
    )
    deployment = relationship("Deployment", back_populates="audio_metrics")