from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
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

    detections = relationship("Detection", back_populates="device")
    audio_metrics = relationship("AudioMetric", back_populates="device")

'''
Esta clase representa la tabla para almacenar detecciones biológicas o acústicas relevantes.
'''
class Detection(Base):
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    species = Column(String, index=True)
    confidence = Column(Float)
    filename = Column(String)
    amplitude = Column(Float, default=0.0)

    device_id = Column(Integer, ForeignKey("devices.id"))
    device = relationship("Device", back_populates="detections")

'''
Esta clase representa una muestra acústica agregada por ciclo de grabación.
No equivale a una detección de ave: guarda métricas del paisaje sonoro aunque no haya detecciones.
'''
class AudioMetric(Base):
    __tablename__ = "audio_metrics"

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