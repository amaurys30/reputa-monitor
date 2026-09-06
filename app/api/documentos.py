from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import Documento, UrlRegistro, EstadoURL
from app.schemas.schemas import DocumentoOut

router = APIRouter(prefix="/api/documentos", tags=["documentos"])


@router.get("", response_model=list[DocumentoOut])
def listar_documentos(
    busqueda_id: int | None = None,
    clasificacion_contextual: str | None = None,
    fuente_id: int | None = None,
    estado_verificacion: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    db: Session = Depends(get_db),
):
    """
    RF9: filtros mínimos requeridos -> clasificación contextual, fuente,
    fecha y estado de verificación de identidad.
    """
    q = db.query(Documento)
    if busqueda_id:
        q = q.filter(Documento.busqueda_id == busqueda_id)
    if clasificacion_contextual:
        q = q.filter(Documento.clasificacion_contextual == clasificacion_contextual)
    if fuente_id:
        q = q.filter(Documento.fuente_id == fuente_id)
    if estado_verificacion:
        q = q.filter(Documento.estado_verificacion == estado_verificacion)
    if fecha_desde:
        q = q.filter(Documento.fecha_consulta >= fecha_desde)
    if fecha_hasta:
        q = q.filter(Documento.fecha_consulta <= fecha_hasta)
    return q.order_by(Documento.fecha_consulta.desc()).all()


@router.get("/descartados")
def listar_descartados(busqueda_id: int, db: Session = Depends(get_db)):
    """RF5: permitir consultar los elementos descartados y por qué."""
    q = db.query(UrlRegistro).filter(
        UrlRegistro.busqueda_id == busqueda_id,
        UrlRegistro.estado.in_([EstadoURL.DESCARTADA, EstadoURL.ERROR]),
    )
    return [
        {"url": u.url, "estado": u.estado, "motivo": u.motivo_descarte,
         "procesada_en": u.procesada_en}
        for u in q.all()
    ]
