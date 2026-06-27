from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime, timezone

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

    detections = relationship("Detection", back_populates="device")
    audio_metrics = relationship("AudioMetric", back_populates="device")

'''
Esta clase representa la tabla para almacenar detecciones biológicas o acústicas relevantes.
'''
class Detection(Base):
    __tablename__ = "detections"
    __table_args__ = (
        UniqueConstraint("device_id", "timestamp", "species", "filename", name="uq_detection_event"),
    )

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    species = Column(String, index=True)
    confidence = Column(Float)
    filename = Column(String)
    amplitude = Column(Float, default=0.0)

    device_id = Column(Integer, ForeignKey("devices.id"))
    device = relationship("Device", back_populates="detections")

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
class AudioMetric(Base):
    __tablename__ = "audio_metrics"
    __table_args__ = (
        UniqueConstraint("device_id", "timestamp", "filename", name="uq_audio_metric_event"),
    )

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    filename = Column(String, index=True)

    sample_rate = Column(Integer)
    duration = Column(Float)
    rms = Column(Float, default=0.0)

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