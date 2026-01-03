from pydantic import BaseModel
from datetime import datetime
from typing import Optional

####Esquemas para detecciones####

class DetectionCreate(BaseModel):
    species: str
    confidence: float
    timestamp: datetime
    filename: str
    device_name: str  # Nombre del dispositivo que hizo la detección

#Esto es lo que se devolvera al usuario leyendolo de la DB
class Detection(DetectionCreate):
    id: int
    device_id: int

    class Config:
        from_attributes = True


# The `DeviceCreate` class is a Python class with attributes for `name` and `location`.
class DeviceCreate(BaseModel):
    name: str
    location: str


'''DOCUMENTACION CREADA AUTOMATICAMENTE POR LA EXTENSION'''
# The `DetectionResponse` class defines attributes for representing detection responses with Pydantic,
# including reading data directly from a SQL database.
class DetectionResponse(BaseModel):
    id: int
    species: str
    confidence: float
    timestamp: datetime
    filename: str
    device_id: int

    class Config:
        from_attributes = True