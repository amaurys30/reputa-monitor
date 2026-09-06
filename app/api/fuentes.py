from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import Fuente, TipoFuente
from app.schemas.schemas import FuenteCreate, FuenteOut
from app.crawler.fetcher import descargar_pagina
from app.crawler.country_detector import detectar_pais_desde_contenido

router = APIRouter(prefix="/api/fuentes", tags=["fuentes"])


def _detectar_o_fallar(url_inicial: str, pais_manual: str | None):
    """
    RF2: el país de una fuente se determina a partir del ÁMBITO DE SU
    CONTENIDO (lang del HTML, og:locale, ccTLD, léxico de la página),
    nunca de la ubicación física del servidor.

    Si la detección automática no alcanza confianza suficiente, se exige
    `pais_manual` como respaldo explícito (análogo a cómo RF6 trata
    `fecha_publicacion`: mejor esfuerzo, con salida honesta si no hay
    evidencia suficiente en vez de inventar un valor).
    """
    pagina = descargar_pagina(url_inicial)
    if not pagina.ok:
        if pais_manual:
            return (pais_manual, False, 0.0,
                    f"No se pudo descargar la URL para analizarla ({pagina.error}); "
                    "país asignado manualmente")
        raise HTTPException(
            422,
            f"No se pudo acceder a la URL para detectar el país automáticamente ({pagina.error}). "
            "Reintenta o incluye 'pais_manual' para asignarlo tú mismo.",
        )

    resultado = detectar_pais_desde_contenido(
        url_inicial, pagina.titulo, pagina.texto,
        idioma_html=pagina.idioma_html, og_locale=pagina.og_locale,
    )

    if resultado.automatico:
        return resultado.pais, True, resultado.confianza, resultado.evidencia

    if pais_manual:
        return (pais_manual, False, resultado.confianza,
                f"Detección automática inconclusa ({resultado.evidencia}); país asignado manualmente")

    raise HTTPException(
        422,
        f"No se pudo determinar el país automáticamente a partir del contenido "
        f"({resultado.evidencia}). Incluye 'pais_manual' para asignarlo tú mismo.",
    )


@router.post("", response_model=FuenteOut)
def crear_fuente(payload: FuenteCreate, db: Session = Depends(get_db)):
    """RF2: nombre, URL inicial, país (autodetectado del contenido), tipo y estado."""
    try:
        tipo = TipoFuente(payload.tipo)
    except ValueError:
        raise HTTPException(400, f"Tipo de fuente inválido: {payload.tipo}")

    pais, automatico, confianza, evidencia = _detectar_o_fallar(
        payload.url_inicial, payload.pais_manual
    )

    fuente = Fuente(
        nombre=payload.nombre, url_inicial=payload.url_inicial,
        pais=pais, tipo=tipo, activa=payload.activa,
        pais_detectado_automaticamente=automatico,
        confianza_deteccion_pais=confianza,
        evidencia_deteccion_pais=evidencia,
    )
    db.add(fuente)
    db.commit()
    db.refresh(fuente)
    return fuente


@router.get("", response_model=list[FuenteOut])
def listar_fuentes(pais: str | None = None, activa: bool | None = None,
                    db: Session = Depends(get_db)):
    q = db.query(Fuente)
    if pais:
        q = q.filter(Fuente.pais == pais)
    if activa is not None:
        q = q.filter(Fuente.activa == activa)
    return q.order_by(Fuente.id.desc()).all()


@router.patch("/{fuente_id}/estado", response_model=FuenteOut)
def cambiar_estado_fuente(fuente_id: int, activa: bool, db: Session = Depends(get_db)):
    fuente = db.get(Fuente, fuente_id)
    if not fuente:
        raise HTTPException(404, "Fuente no encontrada")
    fuente.activa = activa
    db.commit()
    db.refresh(fuente)
    return fuente
