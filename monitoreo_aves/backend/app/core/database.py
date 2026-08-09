import os

from .config import APP_DIR
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

#Aqui creamos el motor de la base de datos
DB_PATH = os.getenv("BIRDMONITOR_DB_PATH", str(APP_DIR / "birdmonitor.db"))

SQALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(SQALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def configurar_sqlite(dbapi_connection, _connection_record):
    """Activa integridad referencial y una espera breve ante escrituras concurrentes."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependencia para obtener la sesion de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()