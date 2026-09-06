"""
Fixtures compartidas de pytest.

Usamos SQLite en memoria (no Postgres) para que los tests corran
rápido y sin depender de Docker. Esto es válido porque lo que se
prueba es la LÓGICA de concurrencia y de negocio (matching, identidad,
clasificación, exclusión mutua), no características específicas de
PostgreSQL.
"""
import os

# IMPORTANTE: debe fijarse ANTES de que cualquier módulo de la app
# importe app.db.database (que crea un engine al importarse). Así se
# evita depender de psycopg2/Postgres para correr los tests localmente.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def db_session(monkeypatch, tmp_path):
    # Un archivo SQLite temporal (no :memory:): con :memory: cada conexión
    # nueva (cada hilo abre la suya) obtiene una base VACÍA distinta, lo
    # cual rompe justamente las pruebas de concurrencia entre threads que
    # necesitan ver el mismo estado compartido.
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    import app.db.database as dbmod
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "SessionLocal", TestingSessionLocal)

    import app.crawler.crawler_manager as cm
    import app.crawler.worker as wk
    monkeypatch.setattr(cm, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(wk, "SessionLocal", TestingSessionLocal)

    from app.models import models  # noqa: F401 registra tablas
    dbmod.Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    yield session
    session.close()
