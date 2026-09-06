"""
Script de siembra (seed): fuentes públicas de ejemplo para Colombia (RF2).

Uso (dentro del contenedor):
    python -m app.db.seed

Este script SÍ pasa por la detección automática de país (RF2: el país
se determina por el ámbito del contenido, no se asume a mano ni siquiera
aquí), descargando cada URL real para analizarla. Por eso requiere
acceso a internet desde el contenedor y puede tardar unos segundos.

Nota: algunas fuentes bloquean crawlers agresivos o requieren
JavaScript para renderizar contenido (esto es intencional que lo
descubran y lo discutan en la sustentación: limitaciones reales de
crawling estático con requests+BeautifulSoup vs. un navegador headless).
"""
from app.db.database import SessionLocal, Base, engine
from app.models.models import Fuente, TipoFuente
from app.crawler.fetcher import descargar_pagina
from app.crawler.country_detector import detectar_pais_desde_contenido

FUENTES_A_SEMBRAR = [
    {"nombre": "El Tiempo", "url_inicial": "https://www.eltiempo.com", "tipo": TipoFuente.NOTICIAS},
    {"nombre": "El Espectador", "url_inicial": "https://www.elespectador.com", "tipo": TipoFuente.NOTICIAS},
    {"nombre": "Semana", "url_inicial": "https://www.semana.com", "tipo": TipoFuente.NOTICIAS},
    {"nombre": "La Silla Vacía", "url_inicial": "https://www.lasillavacia.com", "tipo": TipoFuente.BLOG},
]


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        creadas, fallidas = 0, 0
        for datos in FUENTES_A_SEMBRAR:
            existe = db.query(Fuente).filter_by(url_inicial=datos["url_inicial"]).first()
            if existe:
                continue

            print(f"Analizando {datos['url_inicial']} para determinar su país...")
            pagina = descargar_pagina(datos["url_inicial"])
            if not pagina.ok:
                print(f"  ADVERTENCIA: no se pudo descargar ({pagina.error}); se omite.")
                fallidas += 1
                continue

            resultado = detectar_pais_desde_contenido(
                datos["url_inicial"], pagina.titulo, pagina.texto,
                idioma_html=pagina.idioma_html, og_locale=pagina.og_locale,
            )
            if not resultado.automatico:
                print(f"  ADVERTENCIA: no se pudo determinar el país con confianza "
                      f"({resultado.evidencia}); se omite. Agrégala manualmente desde /fuentes.")
                fallidas += 1
                continue

            print(f"  País detectado: {resultado.pais} (confianza {resultado.confianza})")
            db.add(Fuente(
                nombre=datos["nombre"], url_inicial=datos["url_inicial"],
                pais=resultado.pais, tipo=datos["tipo"], activa=True,
                pais_detectado_automaticamente=True,
                confianza_deteccion_pais=resultado.confianza,
                evidencia_deteccion_pais=resultado.evidencia,
            ))
            creadas += 1
        db.commit()
        print(f"\nFuentes creadas: {creadas} | omitidas por fallo de detección/red: {fallidas}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
