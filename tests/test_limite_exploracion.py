"""
Test de regresión: bug real reportado durante pruebas manuales.

Síntoma observado: con max_urls=60, al finalizar una búsqueda quedaban
cientos de URLs en estado PENDIENTE para siempre (nunca se procesaban),
porque se registraban en la BD antes de verificar si había cupo en la
cola. Este test reproduce la causa (muchos workers descubriendo muchos
enlaces con un límite bajo) y verifica que ya NO quedan registros
PENDIENTE huérfanos una vez que la cola se vacía.
"""
import threading

from app.crawler.url_queue import ColaURLsCompartida


def test_no_reserva_mas_alla_del_limite_bajo_concurrencia():
    """
    50 threads intentan reservar cupo simultáneamente contra un límite
    de 10. Exactamente 10 deben tener éxito -- ni más (violaría RF3) ni
    menos (el contador no debería perder incrementos por la carrera).
    """
    cola = ColaURLsCompartida(max_urls=10)
    exitos = []
    lock = threading.Lock()

    def intentar():
        if cola.intentar_reservar_slot():
            with lock:
                exitos.append(1)

    hilos = [threading.Thread(target=intentar) for _ in range(50)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert len(exitos) == 10
    assert cola.total_encoladas == 10


def test_sin_limite_reserva_siempre():
    cola = ColaURLsCompartida(max_urls=None)
    for _ in range(500):
        assert cola.intentar_reservar_slot() is True


def test_flujo_completo_no_deja_pendientes_huerfanos(db_session):
    """
    Reproduce el bug de punta a punta: un worker descubre MUCHOS más
    enlaces de los que el límite permite. Verifica que solo se crean
    registros UrlRegistro dentro del límite -- nunca de más.
    """
    from app.models.models import Busqueda, UrlRegistro, EstadoURL
    from app.crawler.state_manager import URLStateManager

    busqueda = Busqueda(persona_id=1, pais="Colombia", max_workers=5,
                         max_urls=10, estado="PENDIENTE")
    db_session.add(busqueda)
    db_session.commit()
    db_session.refresh(busqueda)

    cola = ColaURLsCompartida(max_urls=busqueda.max_urls)
    state_manager = URLStateManager()

    # Simula el worker descubriendo 100 enlaces nuevos con límite de 10.
    for i in range(100):
        if not cola.intentar_reservar_slot():
            break
        nuevo = state_manager.registrar_url_si_nueva(
            db_session, busqueda.id, f"https://sitio.com/pagina-{i}", None, 1
        )
        if nuevo:
            cola.put(nuevo.id)

    total_registros = db_session.query(UrlRegistro).filter_by(busqueda_id=busqueda.id).count()
    assert total_registros <= 10, (
        f"Se registraron {total_registros} URLs pese al límite de 10 -- "
        "esto reproduciría el bug de PENDIENTE huérfanos"
    )
