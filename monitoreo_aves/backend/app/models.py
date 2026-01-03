from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime, timezone

'''
Esta clase pues realizamos al tabla de la db con sus columnas para almacenar la informacion
'''
class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    Location = Column(String)

    detections = relationship("Detection", back_populates="device")


'''
Esta clase representa la tabla db para almacenar la informacion sobre las especies detectadas con sus
respectivos metadatos
'''
class Detection(Base):
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    species = Column(String, index=True)
    confidence = Column(Float)
    filename = Column(String)

    device_id = Column(Integer, ForeignKey("devices.id"))
    device = relationship("Device", back_populates="detections")