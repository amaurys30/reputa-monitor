"""
RF2 — Detección automática del país de una fuente A PARTIR DE SU CONTENIDO.

Requisito explícito del taller: "La asociación de una fuente con un país
deberá corresponder al ámbito de su contenido y no a la ubicación física
del servidor." Por eso este módulo NUNCA hace geolocalización de IP,
whois, ni resuelve el datacenter donde vive el sitio — analiza señales
que el propio contenido/HTML expone sobre de qué país habla.

Señales usadas, de mayor a menor confiabilidad:
  1. Atributo `lang` del HTML (ej. <html lang="es-CO">) -> el propio sitio
     declara su localización. Señal fuerte.
  2. Meta tag `og:locale` (ej. es_CO) -> igual de declarativa. Señal fuerte.
  3. TLD de código de país (ccTLD, ej. ".co") -> señal media (indicativa,
     pero varios sitios de un país usan ".com" genérico, ej. eltiempo.com).
  4. Análisis léxico: frecuencia de gentilicios y nombres de ciudades
     propios de cada país en el título + contenido textual.

El diccionario de señales es extensible por diseño (no está hardcodeado
solo para Colombia) aunque el taller solo exige soportar Colombia como
mínimo.
"""
import re
from dataclasses import dataclass
from urllib.parse import urlparse

# país -> señales conocidas
SENALES_PAIS: dict[str, dict] = {
    "Colombia": {
        "codigos_locale": {"co"},          # es-CO, es_CO
        "cctlds": {"co", "com.co"},
        "gentilicios": ["colombiano", "colombiana", "colombianos", "colombianas"],
        "ciudades": [
            "bogotá", "bogota", "medellín", "medellin", "cali", "barranquilla",
            "cartagena", "bucaramanga", "sincelejo", "pereira", "manizales",
            "cúcuta", "cucuta", "ibagué", "ibague", "villavicencio",
        ],
        "palabras_pais": ["colombia"],
    },
    "México": {
        "codigos_locale": {"mx"},
        "cctlds": {"mx", "com.mx"},
        "gentilicios": ["mexicano", "mexicana", "mexicanos", "mexicanas"],
        "ciudades": ["ciudad de méxico", "cdmx", "guadalajara", "monterrey", "puebla"],
        "palabras_pais": ["méxico", "mexico"],
    },
    "Argentina": {
        "codigos_locale": {"ar"},
        "cctlds": {"ar", "com.ar"},
        "gentilicios": ["argentino", "argentina", "argentinos", "argentinas"],
        "ciudades": ["buenos aires", "córdoba", "rosario", "mendoza"],
        "palabras_pais": ["argentina"],
    },
    "Perú": {
        "codigos_locale": {"pe"},
        "cctlds": {"pe", "com.pe"},
        "gentilicios": ["peruano", "peruana", "peruanos", "peruanas"],
        "ciudades": ["lima", "arequipa", "trujillo", "cusco"],
        "palabras_pais": ["perú", "peru"],
    },
    "Chile": {
        "codigos_locale": {"cl"},
        "cctlds": {"cl"},
        "gentilicios": ["chileno", "chilena", "chilenos", "chilenas"],
        "ciudades": ["santiago", "valparaíso", "valparaiso", "concepción"],
        "palabras_pais": ["chile"],
    },
    "España": {
        "codigos_locale": {"es"},
        "cctlds": {"es"},
        "gentilicios": ["español", "española", "españoles", "españolas"],
        "ciudades": ["madrid", "barcelona", "valencia", "sevilla"],
        "palabras_pais": ["españa", "espana"],
    },
    "Estados Unidos": {
        "codigos_locale": {"us"},
        "cctlds": {"us"},
        "gentilicios": ["estadounidense", "estadounidenses"],
        "ciudades": ["washington", "nueva york", "los ángeles", "los angeles", "miami"],
        "palabras_pais": ["estados unidos"],
    },
}

UMBRAL_MINIMO_CONFIANZA = 2.5  # por debajo de esto, se pide confirmación manual

# Dominios de segundo nivel reservados institucionalmente para un país
# específico (solo entidades acreditadas de ese país pueden registrarlos).
# Son una señal MUCHO más confiable que el idioma/locale declarado en el
# HTML, porque ese último a menudo es solo un descuido de plantilla/CMS
# (ej. muchos sitios quedan con "es-ES" por defecto sin que el contenido
# tenga nada que ver con España). Por eso estos dominios se verifican
# PRIMERO y, si coinciden, deciden el país de inmediato sin más análisis.
TLDS_INSTITUCIONALES_FUERTES: dict[str, list[str]] = {
    "Colombia": ["edu.co", "gov.co", "mil.co"],
    "México": ["edu.mx", "gob.mx"],
    "Argentina": ["edu.ar", "gob.ar"],
    "Perú": ["edu.pe", "gob.pe"],
    "Chile": ["edu.cl", "gob.cl"],
    "España": ["edu.es", "gob.es"],
}


@dataclass
class ResultadoDeteccionPais:
    pais: str | None
    confianza: float
    evidencia: str
    automatico: bool


def _extraer_codigo_locale(idioma_html: str | None, og_locale: str | None) -> str | None:
    """De 'es-CO' o 'es_CO' extrae 'co'."""
    for valor in (og_locale, idioma_html):
        if not valor:
            continue
        partes = re.split(r"[-_]", valor.strip())
        if len(partes) >= 2:
            return partes[-1].lower()
    return None


def detectar_pais_desde_contenido(
    url: str, titulo: str, texto: str,
    idioma_html: str | None = None, og_locale: str | None = None,
) -> ResultadoDeteccionPais:
    contenido = f"{titulo} {texto}".lower()
    dominio = urlparse(url).netloc.lower()

    # Paso 0 -- dominios institucionales fuertes (.edu.co, .gov.co, etc.):
    # se verifican ANTES que cualquier otra señal y, si coinciden, deciden
    # el país de inmediato. Un dominio así es más confiable que el idioma
    # declarado en el HTML (que a menudo es solo un valor por defecto de
    # la plantilla/CMS, sin relación real con el país del contenido).
    for pais, tlds in TLDS_INSTITUCIONALES_FUERTES.items():
        for tld in tlds:
            if dominio.endswith("." + tld):
                return ResultadoDeteccionPais(
                    pais, 8.0,
                    f"dominio institucional .{tld}, reservado para entidades de {pais}",
                    automatico=True,
                )

    codigo_locale = _extraer_codigo_locale(idioma_html, og_locale)

    puntajes: dict[str, float] = {}
    evidencias: dict[str, list[str]] = {}

    def sumar(pais: str, puntos: float, motivo: str):
        puntajes[pais] = puntajes.get(pais, 0) + puntos
        evidencias.setdefault(pais, []).append(motivo)

    for pais, senales in SENALES_PAIS.items():
        # 1) lang/og:locale -- señal fuerte y declarativa del propio sitio
        if codigo_locale and codigo_locale in senales["codigos_locale"]:
            sumar(pais, 4.0, f"idioma/locale del sitio indica código '{codigo_locale}'")

        # 2) ccTLD -- señal media
        for cctld in senales["cctlds"]:
            if dominio.endswith("." + cctld):
                sumar(pais, 2.0, f"dominio termina en .{cctld}")
                break

        # 3) análisis léxico -- gentilicios, ciudades, nombre del país
        conteo = 0
        for palabra in senales["gentilicios"] + senales["ciudades"] + senales["palabras_pais"]:
            apariciones = len(re.findall(rf"\b{re.escape(palabra)}\b", contenido))
            conteo += min(apariciones, 5)  # se limita para que una palabra repetida no domine
        if conteo > 0:
            peso = min(conteo * 0.5, 5.0)  # tope para no sobrevalorar el léxico solo
            sumar(pais, peso, f"{conteo} menciones de términos asociados a {pais} en el contenido")

    if not puntajes:
        return ResultadoDeteccionPais(None, 0.0, "Ninguna señal de país encontrada en el contenido",
                                       automatico=False)

    pais_ganador = max(puntajes, key=puntajes.get)
    confianza = round(puntajes[pais_ganador], 2)
    evidencia = "; ".join(evidencias[pais_ganador])

    if confianza < UMBRAL_MINIMO_CONFIANZA:
        return ResultadoDeteccionPais(
            pais_ganador, confianza,
            f"Señales insuficientes (confianza {confianza} < {UMBRAL_MINIMO_CONFIANZA}): {evidencia}",
            automatico=False,
        )

    return ResultadoDeteccionPais(pais_ganador, confianza, evidencia, automatico=True)
