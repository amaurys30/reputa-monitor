"""RF2 - Detección de país a partir del contenido (nunca del servidor)."""
from app.crawler.country_detector import detectar_pais_desde_contenido


def test_detecta_colombia_por_lang_html():
    r = detectar_pais_desde_contenido(
        url="https://www.eltiempo.com/articulo",
        titulo="Noticias de Colombia",
        texto="Contenido breve sin muchas pistas.",
        idioma_html="es-CO",
    )
    assert r.pais == "Colombia"
    assert r.automatico is True
    assert r.confianza >= 4.0


def test_detecta_colombia_por_og_locale():
    r = detectar_pais_desde_contenido(
        url="https://www.semana.com/nota",
        titulo="Última hora",
        texto="",
        og_locale="es_CO",
    )
    assert r.pais == "Colombia"
    assert r.automatico is True


def test_detecta_colombia_por_lexico_sin_metadatos():
    texto = (
        "El presidente colombiano visitó Bogotá y Medellín esta semana. "
        "Autoridades colombianas confirmaron la agenda en Cali."
    )
    r = detectar_pais_desde_contenido(
        url="https://blog-generico.com/post",  # dominio genérico, sin ccTLD útil
        titulo="Agenda presidencial",
        texto=texto,
    )
    assert r.pais == "Colombia"
    assert r.automatico is True


def test_detecta_mexico_no_colombia_por_defecto():
    """El detector debe ser genérico, no sesgado siempre hacia Colombia."""
    r = detectar_pais_desde_contenido(
        url="https://www.ejemplo.com.mx/nota",
        titulo="Noticias de México",
        texto="El presidente mexicano habló desde Ciudad de México sobre la agenda nacional mexicana.",
        idioma_html="es-MX",
    )
    assert r.pais == "México"


def test_sin_senales_no_determina_pais_automaticamente():
    r = detectar_pais_desde_contenido(
        url="https://sitio-neutro.com/pagina",
        titulo="Bienvenidos",
        texto="Contenido genérico sin ninguna referencia geográfica particular.",
    )
    assert r.automatico is False


def test_nunca_usa_ubicacion_de_servidor():
    """
    El detector solo recibe url/titulo/texto/idioma/locale -- ninguna
    de estas señales proviene de resolver DNS, whois o geolocalizar la
    IP del servidor. Se verifican llamadas/imports reales, no menciones
    en comentarios (el propio docstring del módulo explica esta garantía
    en prosa, así que buscar la palabra suelta daría un falso positivo).
    """
    import inspect
    from app.crawler import country_detector
    codigo_fuente = inspect.getsource(country_detector)
    llamadas_prohibidas = [
        "socket.gethostbyname(", "import socket", "import whois",
        "whois.whois(", "import geoip2", "GeoIP(",
    ]
    for prohibido in llamadas_prohibidas:
        assert prohibido not in codigo_fuente, f"No debería usarse: {prohibido}"


def test_dominio_edu_co_gana_aunque_locale_diga_espana():
    """
    Bug real reportado: cecar.edu.co (universidad colombiana) fue
    detectado como España porque el sitio declaraba lang="es-ES" (un
    descuido común de plantilla/CMS). El dominio institucional .edu.co
    debe ganar SIEMPRE sobre esa señal de idioma, porque solo entidades
    colombianas acreditadas pueden registrar ese dominio.
    """
    r = detectar_pais_desde_contenido(
        url="https://cecar.edu.co/programas",
        titulo="CECAR - Corporación Universitaria del Caribe",
        texto="Programas academicos, facultades e investigacion en Sincelejo, Sucre.",
        idioma_html="es-ES",  # descuido de plantilla, NO significa España
    )
    assert r.pais == "Colombia"
    assert r.automatico is True
    assert "edu.co" in r.evidencia


def test_dominio_gob_mx_gana_sobre_locale_generico():
    r = detectar_pais_desde_contenido(
        url="https://www.gob.mx/salud",
        titulo="Portal del Gobierno",
        texto="Informacion oficial.",
        idioma_html="es",  # sin región especificada
    )
    assert r.pais == "México"
