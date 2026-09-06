"""
Configuración central de la base de datos.

Usamos SQLAlchemy con un pool de conexiones (QueuePool por defecto) porque
múltiples workers/threads del crawler escriben en la BD de forma concurrente
(RF4, RF6). El pool evita que cada hilo abra su propia conexión cruda y
gestiona el acceso concurrente de forma segura.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://reputa:reputa@db:5432/reputa_monitor",
)

# pool_size / max_overflow: dimensionado para soportar N workers concurrentes
# escribiendo/leyendo al mismo tiempo (ver app/core/config.py -> MAX_WORKERS).
# Estos parámetros son específicos de motores con pool "real" (Postgres,
# MySQL); SQLite (usado solo para tests locales, no en producción/Docker)
# no los soporta con su pool por defecto, así que se omiten en ese caso.
_engine_kwargs = {"pool_pre_ping": True, "future": True}
if not DATABASE_URL.startswith("sqlite"):
    _engine_kwargs.update(pool_size=20, max_overflow=20)
else:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_kwargs)

# Cada hilo debe pedir su propia sesión (las sesiones de SQLAlchemy NO son
# thread-safe). Por eso SessionLocal se usa como fábrica: cada worker llama
# SessionLocal() y obtiene una sesión propia, respaldada por una conexión
# tomada del pool.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()


def get_db():
    """Dependencia de FastAPI: una sesión por request, cerrada al final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
