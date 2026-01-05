import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

#Aqui creamos el motor de la base de datos
BACKEND_DIR = os.path.join(BASE_DIR)
DB_PATH = os.path.join(BACKEND_DIR, "birdmonitor.db")

SQALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(SQALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependencia para obtener la sesion de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()