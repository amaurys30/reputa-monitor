"""Al eliminar una persona, deben desaparecer también sus búsquedas,
URLs, documentos y métricas asociadas (integridad referencial)."""
from app.models.models import Persona, Busqueda, UrlRegistro, Documento, MetricaEjecucion, EstadoURL


def test_eliminar_persona_borra_en_cascada(db_session):
    persona = Persona(nombre_completo="Test Persona", pais="Colombia")
    db_session.add(persona)
    db_session.commit()
    db_session.refresh(persona)

    busqueda = Busqueda(persona_id=persona.id, pais="Colombia", max_workers=1,
                         max_urls=5, estado="FINALIZADA")
    db_session.add(busqueda)
    db_session.commit()
    db_session.refresh(busqueda)

    db_session.add(UrlRegistro(busqueda_id=busqueda.id, url="https://x.com",
                                estado=EstadoURL.PROCESADA))
    db_session.add(Documento(busqueda_id=busqueda.id, persona_id=persona.id,
                              url="https://x.com", titulo="t"))
    db_session.add(MetricaEjecucion(busqueda_id=busqueda.id, etapa="TEST", modo="THREADS",
                                     num_workers=1, num_urls_procesadas=1,
                                     tiempo_total_segundos=1.0))
    db_session.commit()

    db_session.delete(persona)
    db_session.commit()

    assert db_session.query(Busqueda).count() == 0
    assert db_session.query(UrlRegistro).count() == 0
    assert db_session.query(Documento).count() == 0
    assert db_session.query(MetricaEjecucion).count() == 0
