"""
RF3 - Orquestador principal del crawler concurrente.

Arma el pool de workers (threads), la cola compartida y el gestor de
estados, siembra las URLs iniciales (seed URLs) de las fuentes activas
del país, y espera a que todo el trabajo (incluidas las URLs
descubiertas dinámicamente) termine.

`max_workers` es completamente configurable (parámetro de la Busqueda),
lo cual es requisito explícito de RF3 y es indispensable para el
requisito de "Medición de concurrencia" (correr 1 vs. N workers bajo
las mismas condiciones).
"""
import logging
import threading
import time

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import SessionLocal
from app.models.models import (
    Busqueda, Fuente, UrlRegistro, EstadoURL, MetricaEjecucion
)
from app.crawler.state_manager import URLStateManager
from app.crawler.url_queue import ColaURLsCompartida
from app.crawler.worker import ciclo_de_vida_worker
from app.crawler.context import construir_contexto
from app.crawler.metrics_accumulator import AcumuladorTiempos

logger = logging.getLogger("crawler.manager")


def calcular_profundidad_automatica(max_urls: int | None) -> int:
    """
    Ajusta la profundidad de exploración (saltos de enlaces) según qué
    tan grande es el límite de URLs pedido. No es un parámetro que el
    usuario deba entender ni configurar -- es un detalle interno del
    crawler -- pero si alguien pide explorar 1000 URLs con solo 2 saltos
    de profundidad, es probable que el sitio se agote mucho antes de
    llegar a ese número (la mayoría de sitios no tienen miles de páginas
    a solo 2 clics de la portada). Se compensa subiendo la profundidad
    automáticamente cuando el límite pedido es alto.
    """
    if max_urls is None:
        return 5  # "sin límite": conviene explorar bien hondo
    if max_urls <= 100:
        return 2
    if max_urls <= 300:
        return 3
    if max_urls <= 700:
        return 4
    return 5  # límites muy altos (ej. 1000+)


def ejecutar_busqueda(busqueda_id: int) -> dict:
    """
    Punto de entrada único para correr una búsqueda completa.
    Se puede invocar desde la API (en un hilo/tarea de fondo) o desde el
    script de benchmark (app/crawler/benchmark.py) para la medición de
    concurrencia.
    """
    db = SessionLocal()
    try:
        busqueda = db.get(Busqueda, busqueda_id)
        if not busqueda:
            raise ValueError(f"Busqueda {busqueda_id} no existe")

        max_profundidad = busqueda.max_profundidad or 2

        busqueda.estado = "EN_CURSO"
        db.commit()

        fuentes_activas = db.query(Fuente).filter(
            func.lower(func.trim(Fuente.pais)) == busqueda.pais.strip().lower(),
            Fuente.activa == True,  # noqa: E712
        ).all()
        if not fuentes_activas:
            logger.warning("No hay fuentes activas para el país %s", busqueda.pais)

        # Contexto plano e inmutable: se lee UNA sola vez aquí (con la
        # sesión del hilo principal) para poder pasarlo con seguridad a
        # todos los workers sin compartir objetos ORM entre threads.
        contexto = construir_contexto(busqueda)

        state_manager = URLStateManager()
        cola = ColaURLsCompartida(max_urls=busqueda.max_urls)
        info_url_por_id: dict[int, dict] = {}
        lock_url_por_id = threading.Lock()

        # --- Siembra de URLs iniciales (seed URLs) ---
        for fuente in fuentes_activas:
            if not cola.intentar_reservar_slot():
                break  # límite de exploración alcanzado desde el inicio (caso borde)
            registro = state_manager.registrar_url_si_nueva(
                db, busqueda.id, fuente.url_inicial, fuente.id, profundidad=0
            )
            if registro:
                info_url_por_id[registro.id] = {"url": registro.url, "fuente_id": fuente.id}
                cola.put((registro.id, 0))

        n_workers = max(1, busqueda.max_workers)
        logger.info("Lanzando %d workers para busqueda_id=%s (pais=%s)",
                    n_workers, busqueda_id, busqueda.pais)

        acumulador = AcumuladorTiempos()  # tiempos por etapa (RF3/RF4/RF5/RF7/RF8)

        t0 = time.perf_counter()
        hilos = []
        for i in range(n_workers):
            hilo = threading.Thread(
                target=ciclo_de_vida_worker,
                name=f"CrawlerWorker-{i+1}",
                args=(i, contexto, state_manager, cola, max_profundidad,
                      info_url_por_id, lock_url_por_id, acumulador),
                daemon=True,
            )
            hilos.append(hilo)
            hilo.start()

        # Bloquea hasta que TODO el trabajo (incluido el descubierto sobre
        # la marcha) haya sido procesado. Ver docstring de ColaURLsCompartida.
        cola.join()

        # Ya no hay trabajo pendiente -> enviar sentinelas y esperar a que
        # cada hilo termine su ciclo de vida limpiamente.
        cola.enviar_sentinelas(n_workers)
        for hilo in hilos:
            hilo.join(timeout=5)

        tiempo_total = time.perf_counter() - t0

        # --- Métricas para el requisito de "Medición de concurrencia" ---
        urls_procesadas = db.query(UrlRegistro).filter(
            UrlRegistro.busqueda_id == busqueda.id,
            UrlRegistro.estado.in_([EstadoURL.PROCESADA, EstadoURL.DESCARTADA])
        ).count()

        metrica = MetricaEjecucion(
            busqueda_id=busqueda.id,
            etapa="CRAWLING_COMPLETO",  # incluye RF3-RF8 en el pipeline por-URL
            modo="THREADS",
            num_workers=n_workers,
            num_urls_procesadas=urls_procesadas,
            tiempo_total_segundos=round(tiempo_total, 3),
        )
        db.add(metrica)

        # Métricas GRANULARES por sub-etapa (nota de la rúbrica: RF3, RF4,
        # RF5, RF7 y RF8 deben registrar sus propios tiempos, no solo el
        # tiempo total del pipeline).
        for etapa, datos in acumulador.snapshot().items():
            db.add(MetricaEjecucion(
                busqueda_id=busqueda.id,
                etapa=etapa,
                modo="THREADS",
                num_workers=n_workers,
                num_urls_procesadas=int(datos["cuenta"]),
                tiempo_total_segundos=round(datos["tiempo_total"], 4),
            ))

        busqueda.estado = "FINALIZADA"
        busqueda.conflictos_evitados = state_manager.conflictos_evitados
        from datetime import datetime
        busqueda.finalizado_en = datetime.utcnow()
        db.commit()

        logger.info(
            "Busqueda %s finalizada: %d URLs procesadas en %.2fs con %d workers "
            "(conflictos de concurrencia evitados: %d)",
            busqueda_id, urls_procesadas, tiempo_total, n_workers,
            state_manager.conflictos_evitados,
        )

        return {
            "busqueda_id": busqueda_id,
            "workers": n_workers,
            "urls_procesadas": urls_procesadas,
            "tiempo_total_segundos": round(tiempo_total, 3),
            "conflictos_evitados": state_manager.conflictos_evitados,
        }
    finally:
        db.close()
