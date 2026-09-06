"""Verifica que URLs equivalentes (trailing slash, utm_*, fragmentos) se normalicen igual."""
from app.crawler.url_utils import normalizar_url


def test_normaliza_trailing_slash():
    a = normalizar_url("https://www.clubvivamos.com/")
    b = normalizar_url("https://www.clubvivamos.com")
    assert a == b


def test_normaliza_parametros_utm():
    a = normalizar_url("https://www.elespectador.com/mundo/?utm_source=interno&utm_medium=boton")
    b = normalizar_url("https://www.elespectador.com/mundo/")
    assert a == b


def test_normaliza_fragmento():
    a = normalizar_url("https://sitio.com/articulo#comentarios")
    b = normalizar_url("https://sitio.com/articulo")
    assert a == b


def test_no_afecta_urls_ya_distintas():
    a = normalizar_url("https://sitio.com/articulo-1")
    b = normalizar_url("https://sitio.com/articulo-2")
    assert a != b


def test_preserva_parametros_no_tracking():
    # un parámetro que SÍ cambia el contenido (ej. paginación) debe conservarse
    a = normalizar_url("https://sitio.com/noticias?pagina=2")
    b = normalizar_url("https://sitio.com/noticias?pagina=3")
    assert a != b


def test_dedup_real_al_registrar(db_session):
    from app.models.models import Busqueda
    from app.crawler.state_manager import URLStateManager

    busqueda = Busqueda(persona_id=1, pais="Colombia", max_workers=5,
                         max_urls=10, estado="PENDIENTE")
    db_session.add(busqueda)
    db_session.commit()
    db_session.refresh(busqueda)

    sm = URLStateManager()
    r1 = sm.registrar_url_si_nueva(db_session, busqueda.id,
                                    "https://www.clubvivamos.com/", None, 0)
    r2 = sm.registrar_url_si_nueva(db_session, busqueda.id,
                                    "https://www.clubvivamos.com", None, 0)
    assert r1 is not None
    assert r2 is None  # ya normalizada, debe reconocerse como duplicada
