"""
RF4 - Verifica que URLStateManager garantiza exclusión mutua: bajo alta
concurrencia (muchos threads compitiendo por la misma URL), exactamente
uno debe "ganarla".
"""
import threading

from app.models.models import Busqueda, UrlRegistro, EstadoURL
from app.crawler.state_manager import URLStateManager


def test_exclusion_mutua_bajo_concurrencia(db_session):
    from app.db.database import SessionLocal

    busqueda = Busqueda(persona_id=1, pais="Colombia", max_workers=20,
                         max_urls=5, estado="PENDIENTE")
    db_session.add(busqueda)
    db_session.commit()
    db_session.refresh(busqueda)

    url = UrlRegistro(busqueda_id=busqueda.id, url="http://ejemplo.com/x",
                       estado=EstadoURL.PENDIENTE, profundidad=0)
    db_session.add(url)
    db_session.commit()
    db_session.refresh(url)
    url_id = url.id

    state_manager = URLStateManager()
    ganadores = []
    lock = threading.Lock()

    def intentar(worker_id):
        db = SessionLocal()
        try:
            if state_manager.intentar_tomar_url(db, url_id, f"W{worker_id}"):
                with lock:
                    ganadores.append(worker_id)
        finally:
            db.close()

    N = 25
    hilos = [threading.Thread(target=intentar, args=(i,)) for i in range(N)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert len(ganadores) == 1, f"Se esperaba exactamente 1 ganador, hubo {len(ganadores)}"
    assert state_manager.conflictos_evitados == N - 1


def test_registrar_url_evita_duplicados(db_session):
    busqueda = Busqueda(persona_id=1, pais="Colombia", max_workers=5,
                         max_urls=10, estado="PENDIENTE")
    db_session.add(busqueda)
    db_session.commit()
    db_session.refresh(busqueda)

    state_manager = URLStateManager()
    primero = state_manager.registrar_url_si_nueva(db_session, busqueda.id,
                                                     "http://ejemplo.com/a", None, 0)
    segundo = state_manager.registrar_url_si_nueva(db_session, busqueda.id,
                                                     "http://ejemplo.com/a", None, 0)
    assert primero is not None
    assert segundo is None  # ya existía -> RF6 evita duplicados
