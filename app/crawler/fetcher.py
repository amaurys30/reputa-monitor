"""
Descarga y extracción de contenido de una página.

Esta es la parte "lenta" (I/O-bound) del pipeline: la latencia de red es
justamente lo que justifica usar concurrencia (RF3). Por diseño, esta
función NO toca la base de datos ni el estado compartido: solo hace
requests.get() y parsea con BeautifulSoup. Así la sección crítica
(state_manager) se mantiene mínima y el tiempo bajo lock es casi cero.
"""
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.crawler.url_utils import normalizar_url

HEADERS = {
    "User-Agent": "ReputaMonitorBot/1.0 (+proyecto academico CECAR - Sistemas Distribuidos)"
}
TIMEOUT_SEGUNDOS = 8


@dataclass
class PaginaDescargada:
    url: str
    ok: bool
    titulo: str = ""
    texto: str = ""
    enlaces: list[str] = field(default_factory=list)
    fecha_publicacion: str | None = None
    idioma_html: str | None = None   # atributo lang de <html> -- señal de país (RF2)
    og_locale: str | None = None     # meta og:locale -- señal de país (RF2)
    error: str = ""


# Metadatos comunes donde los sitios de noticias publican la fecha del
# artículo (RF6: "fecha de publicación cuando esté disponible" -> mejor
# esfuerzo, no todos los sitios la exponen de forma estructurada).
_META_FECHA_CANDIDATOS = [
    ("meta", {"property": "article:published_time"}),
    ("meta", {"property": "og:article:published_time"}),
    ("meta", {"name": "publish-date"}),
    ("meta", {"name": "date"}),
    ("meta", {"itemprop": "datePublished"}),
]


def _extraer_fecha_publicacion(soup: BeautifulSoup) -> str | None:
    for tag_name, attrs in _META_FECHA_CANDIDATOS:
        tag = soup.find(tag_name, attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"][:40]
    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        return time_tag["datetime"][:40]
    return None


def descargar_pagina(url: str, mismo_dominio_solo: bool = False) -> PaginaDescargada:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SEGUNDOS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        titulo = soup.title.string.strip() if soup.title and soup.title.string else ""
        fecha_publicacion = _extraer_fecha_publicacion(soup)

        html_tag = soup.find("html")
        idioma_html = html_tag.get("lang") if html_tag else None
        og_locale_tag = soup.find("meta", attrs={"property": "og:locale"})
        og_locale = og_locale_tag.get("content") if og_locale_tag else None

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        texto = " ".join(soup.get_text(separator=" ").split())[:20000]

        dominio_base = urlparse(url).netloc
        enlaces_vistos = set()  # dedup dentro de la MISMA página (menús repiten enlaces)
        enlaces = []
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            parsed = urlparse(href)
            if parsed.scheme not in ("http", "https"):
                continue
            if mismo_dominio_solo and parsed.netloc != dominio_base:
                continue
            href_normalizado = normalizar_url(href)
            if href_normalizado in enlaces_vistos:
                continue
            enlaces_vistos.add(href_normalizado)
            enlaces.append(href_normalizado)

        return PaginaDescargada(url=url, ok=True, titulo=titulo, texto=texto,
                                 enlaces=enlaces[:50], fecha_publicacion=fecha_publicacion,
                                 idioma_html=idioma_html, og_locale=og_locale)
    except Exception as e:
        return PaginaDescargada(url=url, ok=False, error=str(e))
