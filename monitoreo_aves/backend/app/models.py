from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    Location = Column(String)

    detections = relationship("Detection", back_populates="device")

class Detection(Base):
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.timezone.utc.now)
    species = Column(String, index=True)
    confidence = Column(Float)
    filename = Column(String)

    device_id = Column(Integer, ForeignKey("devices.id"))
    device = relationship("Device", back_populates="detections")