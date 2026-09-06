from datetime import datetime
from pydantic import BaseModel, ConfigDict


class PersonaCreate(BaseModel):
    nombre_completo: str
    pais: str
    ciudad: str | None = None
    profesion_cargo: str | None = None
    empresa_organizacion: str | None = None
    alias: str | None = None
    palabras_relacionadas: str | None = None


class PersonaOut(PersonaCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    creado_en: datetime


class FuenteCreate(BaseModel):
    nombre: str
    url_inicial: str
    tipo: str = "OTRO"
    activa: bool = True
    pais_manual: str | None = None  # solo se usa si la detección automática falla


class FuenteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    url_inicial: str
    pais: str
    tipo: str
    activa: bool
    pais_detectado_automaticamente: bool
    confianza_deteccion_pais: float | None
    evidencia_deteccion_pais: str | None


class BusquedaCreate(BaseModel):
    persona_id: int
    pais: str
    max_workers: int = 5
    max_urls: int | None = 60  # None = sin límite (explorar hasta agotar URLs pendientes)
    max_profundidad: int | None = None  # None = se calcula automáticamente según max_urls


class BusquedaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    persona_id: int
    pais: str
    max_workers: int
    max_urls: int | None
    max_profundidad: int
    estado: str
    iniciado_en: datetime
    finalizado_en: datetime | None = None


class DocumentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    persona_id: int
    fuente_id: int | None
    titulo: str | None
    url: str
    pais: str | None
    fecha_publicacion: datetime | None
    fecha_consulta: datetime
    estado_verificacion: str
    clasificacion_contextual: str
    score_identidad: float
    justificacion_clasificacion: str | None
    contenido_texto: str | None = None
