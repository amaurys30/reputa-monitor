"""
Normalización de URLs.

Problema real de crawling (detectado probando contra sitios reales de
noticias, ej. El Espectador): la MISMA página se descubre con distintas
URLs "de superficie":
    https://www.elespectador.com/mundo/
    https://www.elespectador.com/mundo/?utm_source=interno&utm_medium=...
    https://www.elespectador.com/mundo   (sin barra final)

Sin normalizar, cada una se trata como una URL distinta, generando
duplicados/ruido en la exploración y en los descartados. Esto NO es un
fallo de RF4 (exclusión mutua entre workers): ese mecanismo protege
correctamente contra que la MISMA cadena de URL sea tomada por dos
workers a la vez, y eso ya está probado. Este es un problema distinto
y anterior: decidir qué cuenta como "la misma URL" en primer lugar.

Se normaliza:
  - esquema y dominio a minúsculas
  - se quita el fragmento (#seccion)
  - se quitan parámetros de tracking conocidos (utm_*, fbclid, gclid, etc.)
  - se quita la barra final del path (excepto en la raíz "/")
"""
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

PARAMS_DE_TRACKING = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "igshid", "spm",
}


def normalizar_url(url: str) -> str:
    try:
        partes = urlparse(url)
    except Exception:
        return url

    esquema = partes.scheme.lower()
    dominio = partes.netloc.lower()

    path = partes.path
    if path == "":
        path = "/"  # raíz sin slash == raíz con slash
    elif len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query_filtrada = [
        (k, v) for k, v in parse_qsl(partes.query, keep_blank_values=True)
        if k.lower() not in PARAMS_DE_TRACKING
    ]
    query = urlencode(query_filtrada)

    return urlunparse((esquema, dominio, path, "", query, ""))  # sin params, sin fragment
