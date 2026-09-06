import threading
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.db.database import get_db, SessionLocal
from app.models.models import Busqueda, Persona, MetricaEjecucion
from app.schemas.schemas import BusquedaCreate, BusquedaOut
from app.crawler.crawler_manager import ejecutar_busqueda

logger = logging.getLogger("api.busquedas")
router = APIRouter(prefix="/api/busquedas", tags=["busquedas"])


def _correr_en_hilo_de_fondo(busqueda_id: int):
    """
    Corre el crawling completo en un hilo aparte del hilo que atiende el
    request HTTP, para que la API responda de inmediato (202 Accepted)
    y el usuario pueda ver el progreso consultando el estado desde RF9,
    en vez de mantener la conexión HTTP abierta minutos.
    """
    try:
        ejecutar_busqueda(busqueda_id)
    except Exception:
        logger.exception("Fallo al ejecutar busqueda_id=%s", busqueda_id)
        db = SessionLocal()
        try:
            b = db.get(Busqueda, busqueda_id)
            if b:
                b.estado = "ERROR"
                db.commit()
        finally:
            db.close()


@router.post("", response_model=BusquedaOut, status_code=202)
def iniciar_busqueda(payload: BusquedaCreate, db: Session = Depends(get_db)):
    persona = db.get(Persona, payload.persona_id)
    if not persona:
        raise HTTPException(404, "Persona no encontrada")

    # Si no se especifica max_profundidad, se calcula automáticamente
    # según qué tan grande sea el límite de URLs pedido (ver
    # crawler_manager.calcular_profundidad_automatica). No es un
    # parámetro que ningún RF exija exponer al usuario final, pero la
    # API permite fijarlo explícitamente para pruebas/benchmark.
    from app.crawler.crawler_manager import calcular_profundidad_automatica
    profundidad = payload.max_profundidad
    if profundidad is None:
        profundidad = calcular_profundidad_automatica(payload.max_urls)

    busqueda = Busqueda(
        persona_id=payload.persona_id, pais=payload.pais,
        max_workers=payload.max_workers, max_urls=payload.max_urls,
        max_profundidad=profundidad,
        estado="PENDIENTE",
    )
    db.add(busqueda)
    db.commit()
    db.refresh(busqueda)

    # Se lanza en un thread daemon independiente del ciclo de vida del
    # request; el propio crawler_manager crea luego su pool interno de
    # N workers para el crawling concurrente (RF3).
    hilo = threading.Thread(target=_correr_en_hilo_de_fondo, args=(busqueda.id,),
                             daemon=True)
    hilo.start()

    return busqueda


@router.get("", response_model=list[BusquedaOut])
def listar_busquedas(db: Session = Depends(get_db)):
    return db.query(Busqueda).order_by(Busqueda.id.desc()).all()


@router.get("/{busqueda_id}", response_model=BusquedaOut)
def obtener_busqueda(busqueda_id: int, db: Session = Depends(get_db)):
    b = db.get(Busqueda, busqueda_id)
    if not b:
        raise HTTPException(404, "Busqueda no encontrada")
    return b


@router.get("/{busqueda_id}/metricas")
def obtener_metricas(busqueda_id: int, db: Session = Depends(get_db)):
    """Soporte al requisito de 'Medición de concurrencia' de la rúbrica."""
    metricas = db.query(MetricaEjecucion).filter_by(busqueda_id=busqueda_id).all()
    return [
        {
            "etapa": m.etapa, "modo": m.modo, "num_workers": m.num_workers,
            "num_urls_procesadas": m.num_urls_procesadas,
            "tiempo_total_segundos": m.tiempo_total_segundos,
            "registrado_en": m.registrado_en,
        }
        for m in metricas
    ]
