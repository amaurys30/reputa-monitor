from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import Persona
from app.schemas.schemas import PersonaCreate, PersonaOut

router = APIRouter(prefix="/api/personas", tags=["personas"])


@router.post("", response_model=PersonaOut)
def crear_persona(payload: PersonaCreate, db: Session = Depends(get_db)):
    """RF1: nombre completo y país son obligatorios (forzado por el schema)."""
    persona = Persona(**payload.model_dump())
    db.add(persona)
    db.commit()
    db.refresh(persona)
    return persona


@router.get("", response_model=list[PersonaOut])
def listar_personas(db: Session = Depends(get_db)):
    return db.query(Persona).order_by(Persona.id.desc()).all()


@router.get("/{persona_id}", response_model=PersonaOut)
def obtener_persona(persona_id: int, db: Session = Depends(get_db)):
    persona = db.get(Persona, persona_id)
    if not persona:
        raise HTTPException(404, "Persona no encontrada")
    return persona


@router.delete("/{persona_id}", status_code=204)
def eliminar_persona(persona_id: int, db: Session = Depends(get_db)):
    """Elimina la persona y, en cascada, sus búsquedas/documentos/métricas."""
    persona = db.get(Persona, persona_id)
    if not persona:
        raise HTTPException(404, "Persona no encontrada")
    db.delete(persona)
    db.commit()
