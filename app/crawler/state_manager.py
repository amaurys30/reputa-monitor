"""
RF4 - Control concurrente de URLs.

Este es el módulo más importante del taller para la rúbrica: aquí se
demuestra la sincronización real sobre un recurso compartido.

Problema clásico (race condition "check-then-act"):
    Worker A: lee estado de la URL -> PENDIENTE
    Worker B: lee estado de la URL -> PENDIENTE   (antes de que A la marque)
    Worker A: marca EN_PROCESAMIENTO y empieza a descargar
    Worker B: marca EN_PROCESAMIENTO y TAMBIÉN empieza a descargar
    -> la misma URL se procesa dos veces, se puede duplicar en la BD,
       se desperdicia ancho de banda y tiempo de CPU.

Solución: el "check" (¿está pendiente?) y el "act" (marcarla como
EN_PROCESAMIENTO) deben ejecutarse como una única operación atómica.
Usamos un threading.Lock global de bajo tiempo de retención: se toma
justo para la transición de estado en la BD y se libera inmediatamente
(la descarga HTTP, que es lo lento, ocurre FUERA del lock).
"""
import threading
from datetime import datetime
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.models.models import UrlRegistro, EstadoURL
from app.crawler.url_utils import normalizar_url


class URLStateManager:
    """
    Encapsula todas las transiciones de estado de UrlRegistro bajo un
    Lock, de modo que sin importar cuántos threads/workers existan,
    una URL nunca sea tomada por más de uno.
    """

    def __init__(self):
        # Un único lock para todas las transiciones de estado. Es
        # intencionalmente "grueso" (coarse-grained) por simplicidad y
        # porque la sección crítica es muy corta (una consulta + un
        # commit), así que el costo de contención es bajo.
        self._lock = threading.Lock()
        self._contador_conflictos = 0  # cuántas veces un worker "llegó tarde"

    @property
    def conflictos_evitados(self) -> int:
        """Cuántas veces se evitó que una URL se procesara duplicada."""
        return self._contador_conflictos

    def intentar_tomar_url(self, db: Session, url_id: int, worker_id: str) -> bool:
        """
        Intenta pasar una URL de PENDIENTE -> EN_PROCESAMIENTO.

        Devuelve True si este worker "ganó" la URL y debe procesarla.
        Devuelve False si otro worker ya la tomó (o ya no existe / ya
        se procesó), en cuyo caso el llamador debe descartarla y pasar
        a la siguiente sin hacer trabajo adicional.
        """
        with self._lock:  # <-- sección crítica: check + act atómico
            registro = db.get(UrlRegistro, url_id)
            if registro is None or registro.estado != EstadoURL.PENDIENTE:
                self._contador_conflictos += 1
                return False
            registro.estado = EstadoURL.EN_PROCESAMIENTO
            registro.worker_id = worker_id
            registro.intentos += 1
            db.commit()
            return True

    def marcar_procesada(self, db: Session, url_id: int):
        with self._lock:
            registro = db.get(UrlRegistro, url_id)
            if registro:
                registro.estado = EstadoURL.PROCESADA
                registro.procesada_en = datetime.utcnow()
                db.commit()

    def marcar_descartada(self, db: Session, url_id: int, motivo: str):
        with self._lock:
            registro = db.get(UrlRegistro, url_id)
            if registro:
                registro.estado = EstadoURL.DESCARTADA
                registro.motivo_descarte = motivo
                registro.procesada_en = datetime.utcnow()
                db.commit()

    def marcar_error(self, db: Session, url_id: int, motivo: str):
        with self._lock:
            registro = db.get(UrlRegistro, url_id)
            if registro:
                registro.estado = EstadoURL.ERROR
                registro.motivo_descarte = motivo
                registro.procesada_en = datetime.utcnow()
                db.commit()

    def registrar_url_si_nueva(self, db: Session, busqueda_id: int, url: str,
                                fuente_id: int | None, profundidad: int) -> UrlRegistro | None:
        """
        Inserta una URL nueva a la cola de trabajo evitando duplicados.

        También es una sección crítica: dos workers pueden descubrir la
        MISMA url (ej. un enlace que aparece en dos páginas distintas)
        casi al mismo tiempo. Usamos el lock + la restricción UNIQUE de
        BD como doble protección (defensa en profundidad).

        La URL se normaliza (ver url_utils.normalizar_url) ANTES de
        comparar/guardar: así "https://sitio.com/x/" y
        "https://sitio.com/x/?utm_source=menu" se reconocen como la
        misma página y no generan duplicados en la exploración.
        """
        url = normalizar_url(url)
        with self._lock:
            existe = db.query(UrlRegistro).filter_by(
                busqueda_id=busqueda_id, url=url
            ).first()
            if existe:
                return None
            registro = UrlRegistro(
                busqueda_id=busqueda_id,
                url=url,
                fuente_id=fuente_id,
                estado=EstadoURL.PENDIENTE,
                profundidad=profundidad,
            )
            db.add(registro)
            try:
                db.commit()
            except Exception:
                db.rollback()
                return None
            db.refresh(registro)
            return registro
