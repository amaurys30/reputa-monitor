"""
RF3 - Lógica ejecutada por cada worker (hilo) del pool.

Cada worker, de forma independiente y en paralelo con los demás:
  1. Toma una URL de la cola compartida.
  2. Intenta "tomarla" en el state_manager (sección crítica corta).
  3. Si la ganó -> descarga y procesa (I/O-bound, fuera de cualquier lock).
  4. Aplica RF5 (matching), RF7 (identidad) y RF8 (clasificación).
  5. Persiste resultados y encola los nuevos enlaces descubiertos.

Todo el logging incluye threading.current_thread().name para poder
DEMOSTRAR en la sustentación (con logs en vivo) que varios workers están
efectivamente corriendo al mismo tiempo, no en secuencia.
"""
import logging
import threading
import time
from datetime import datetime

from app.db.database import SessionLocal
from app.models.models import Documento
from app.crawler.context import BusquedaContexto
from app.crawler.fetcher import descargar_pagina
from app.crawler.matcher import evaluar_contenido_relacionado
from app.crawler.identity import verificar_identidad
from app.crawler.classifier import clasificar_contexto
from app.crawler.state_manager import URLStateManager
from app.crawler.url_queue import ColaURLsCompartida
from app.crawler.metrics_accumulator import AcumuladorTiempos

logger = logging.getLogger("crawler.worker")


def _parsear_fecha(valor: str | None):
    """Intenta interpretar la fecha de publicación extraída del HTML.
    Los metadatos de fecha vienen en formatos variados entre sitios; si
    no se puede interpretar, se guarda None en vez de fallar (RF6: la
    fecha de publicación es 'cuando esté disponible', no obligatoria)."""
    if not valor:
        return None
    valor = valor.strip().replace("Z", "+00:00")
    for fmt_intento in (None, "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            if fmt_intento is None:
                return datetime.fromisoformat(valor)
            return datetime.strptime(valor[:len(fmt_intento) + 10], fmt_intento)
        except (ValueError, TypeError):
            continue
    return None


def ciclo_de_vida_worker(worker_index: int, contexto: BusquedaContexto,
                          state_manager: URLStateManager, cola: ColaURLsCompartida,
                          max_profundidad: int, info_url_por_id: dict, lock_url_por_id,
                          acumulador: AcumuladorTiempos):
    """
    Cuerpo de un hilo del pool (RF3): saca ítems de la cola compartida en
    bucle hasta recibir el sentinel de apagado. Cada `get()` que retorna
    un item real DEBE emparejarse con exactamente un `task_done()`
    (incluyendo el sentinel), o `cola.join()` nunca terminaría.

    `info_url_por_id` mapea url_id -> {"url": str, "fuente_id": int|None}.
    Se guarda también el fuente_id para poder propagarlo a los enlaces
    descubiertos (RF6: el documento debe registrar de qué fuente vino).
    """
    nombre_hilo = threading.current_thread().name
    logger.info("[%s] Worker iniciado", nombre_hilo)
    while True:
        item = cola.get()
        if item is None:  # sentinel de apagado
            cola.task_done()
            break
        url_id, profundidad_actual = item
        try:
            with lock_url_por_id:
                info = info_url_por_id.get(url_id, {"url": "", "fuente_id": None})
            _procesar_una_url(url_id, info["url"], info["fuente_id"], contexto,
                               state_manager, cola, profundidad_actual, max_profundidad,
                               info_url_por_id, lock_url_por_id, acumulador)
        except Exception:
            logger.exception("[%s] Error inesperado procesando url_id=%s", nombre_hilo, url_id)
        finally:
            cola.task_done()
    logger.info("[%s] Worker finalizado", nombre_hilo)


def _procesar_una_url(url_id: int, url: str, fuente_id: int | None, contexto: BusquedaContexto,
                       state_manager: URLStateManager, cola: ColaURLsCompartida,
                       profundidad_actual: int, max_profundidad: int,
                       info_url_por_id: dict, lock_url_por_id, acumulador: AcumuladorTiempos):
    """
    Pipeline completo (RF3->RF8) para UNA url. Corre dentro de un thread.

    `contexto` es un objeto plano (no ORM) — ver app/crawler/context.py —
    por lo que es seguro leerlo desde múltiples hilos simultáneamente sin
    ningún lock: es inmutable (frozen dataclass) y no está atado a
    ninguna sesión de SQLAlchemy.

    Cada sub-etapa se cronometra por separado en `acumulador` (Nota de
    la rúbrica: "registrar los tiempos de ejecución" de RF3, RF4, RF5,
    RF7 y RF8, no solo un tiempo total del pipeline).
    """
    nombre_hilo = threading.current_thread().name
    db = SessionLocal()  # sesión propia por hilo (no se comparten sesiones)
    t0 = time.perf_counter()
    try:
        t_rf4 = time.perf_counter()
        gano = state_manager.intentar_tomar_url(db, url_id, nombre_hilo)
        acumulador.registrar("RF4_control_estado_url", time.perf_counter() - t_rf4)
        if not gano:
            logger.info("[%s] URL %s ya tomada por otro worker, se omite", nombre_hilo, url)
            return

        logger.info("[%s] Descargando %s", nombre_hilo, url)
        t_rf3 = time.perf_counter()
        pagina = descargar_pagina(url)
        acumulador.registrar("RF3_descarga_html", time.perf_counter() - t_rf3)

        if not pagina.ok:
            state_manager.marcar_error(db, url_id, pagina.error[:490])
            logger.warning("[%s] Error descargando %s: %s", nombre_hilo, url, pagina.error)
            return

        persona = contexto.persona
        t_rf5 = time.perf_counter()
        matching = evaluar_contenido_relacionado(pagina.texto, pagina.titulo,
                                                   persona.palabras_clave())
        acumulador.registrar("RF5_matching_contenido", time.perf_counter() - t_rf5)

        if not matching.relacionado:
            state_manager.marcar_descartada(db, url_id, matching.motivo_descarte)
        else:
            t_rf7 = time.perf_counter()
            verificacion = verificar_identidad(pagina.texto, pagina.titulo, persona)
            acumulador.registrar("RF7_verificacion_identidad", time.perf_counter() - t_rf7)

            t_rf8 = time.perf_counter()
            clasificacion = clasificar_contexto(pagina.texto, pagina.titulo,
                                                 persona.nombre_completo)
            acumulador.registrar("RF8_clasificacion_contextual", time.perf_counter() - t_rf8)
            doc = Documento(
                busqueda_id=contexto.id,
                persona_id=persona.id,
                fuente_id=fuente_id,
                titulo=pagina.titulo,
                url=url,
                pais=contexto.pais,
                fecha_publicacion=_parsear_fecha(pagina.fecha_publicacion),
                contenido_texto=pagina.texto,
                coincidencias_encontradas=", ".join(matching.terminos_encontrados),
                score_identidad=verificacion.score,
                estado_verificacion=verificacion.estado,
                clasificacion_contextual=clasificacion.clasificacion,
                justificacion_clasificacion=clasificacion.justificacion,
            )
            db.add(doc)
            try:
                db.commit()  # RF6: UniqueConstraint evita duplicados por búsqueda
            except Exception:
                db.rollback()  # ya existía (misma url en esta búsqueda) -> se ignora

            state_manager.marcar_procesada(db, url_id)

        # RF3: descubrir e incorporar nuevos enlaces a la cola compartida.
        # El fuente_id se PROPAGA al hijo (RF6: todo documento debe poder
        # rastrearse hasta la fuente pública de la que se originó, aunque
        # se haya llegado a él por varios saltos de enlaces).
        #
        # IMPORTANTE (bug corregido): se reserva el cupo del límite de
        # exploración ANTES de registrar la URL en la BD, no después. Si
        # ya no hay cupo, se deja de explorar esta página sin crear
        # registros PENDIENTE que nunca serían procesados.
        if profundidad_actual < max_profundidad:
            for enlace in pagina.enlaces:
                if not cola.intentar_reservar_slot():
                    break  # límite de exploración alcanzado (RF3)

                nuevo = state_manager.registrar_url_si_nueva(
                    db, contexto.id, enlace, fuente_id=fuente_id,
                    profundidad=profundidad_actual + 1
                )
                if nuevo:
                    with lock_url_por_id:
                        info_url_por_id[nuevo.id] = {"url": nuevo.url, "fuente_id": fuente_id}
                    cola.put((nuevo.id, profundidad_actual + 1))
                # Si `nuevo` es None (la URL ya existía, era duplicada),
                # el cupo reservado se consume igual: es un margen
                # conservador aceptable a cambio de simplicidad -- nunca
                # se crean registros huérfanos, en el peor caso se
                # exploran unas pocas URLs menos de las permitidas.

    finally:
        db.close()
        elapsed = time.perf_counter() - t0
        logger.info("[%s] Terminó %s en %.2fs", nombre_hilo, url, elapsed)
