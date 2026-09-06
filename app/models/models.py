"""
Modelo de datos (ver docs/MODELO_DATOS.md para el diagrama entidad-relación).

Entidades:
- Persona: RF1
- Fuente: RF2
- Busqueda: agrupa una ejecución de crawling para una persona
- UrlRegistro: RF3/RF4 - control de estado de cada URL descubierta
- Documento: RF5/RF6/RF7/RF8 - contenido extraído + verificación + clasificación
- MetricaEjecucion: soporte para el requisito de "Medición de concurrencia"
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Enum, Boolean,
    UniqueConstraint, Float
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class EstadoURL(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    EN_PROCESAMIENTO = "EN_PROCESAMIENTO"
    PROCESADA = "PROCESADA"
    DESCARTADA = "DESCARTADA"
    ERROR = "ERROR"


class EstadoVerificacion(str, enum.Enum):
    MISMA_PERSONA = "MISMA_PERSONA"
    POSIBLE_COINCIDENCIA = "POSIBLE_COINCIDENCIA"
    PERSONA_DIFERENTE = "PERSONA_DIFERENTE"
    NO_DETERMINADO = "NO_DETERMINADO"


class ClasificacionContextual(str, enum.Enum):
    POSITIVO = "POSITIVO"
    NEUTRO = "NEUTRO"
    NEGATIVO = "NEGATIVO"
    NO_DETERMINADO = "NO_DETERMINADO"


class TipoFuente(str, enum.Enum):
    NOTICIAS = "NOTICIAS"
    RED_SOCIAL = "RED_SOCIAL"
    BLOG = "BLOG"
    DIRECTORIO = "DIRECTORIO"
    OTRO = "OTRO"


class Persona(Base):
    """RF1 - Registro de persona a consultar."""
    __tablename__ = "personas"

    id = Column(Integer, primary_key=True)
    nombre_completo = Column(String(255), nullable=False)
    pais = Column(String(100), nullable=False)
    ciudad = Column(String(100), nullable=True)
    profesion_cargo = Column(String(255), nullable=True)
    empresa_organizacion = Column(String(255), nullable=True)
    alias = Column(String(255), nullable=True)  # separados por coma
    palabras_relacionadas = Column(String(500), nullable=True)  # separadas por coma
    creado_en = Column(DateTime, default=datetime.utcnow)

    busquedas = relationship("Busqueda", back_populates="persona",
                              cascade="all, delete-orphan")

    def palabras_clave(self) -> list[str]:
        """Devuelve todos los términos usables para matching (RF5/RF7).
        Incluye variantes realistas del nombre -- ver app/crawler/nombre_utils.py."""
        from app.crawler.nombre_utils import generar_variantes_nombre
        terminos = [v for v, _p in generar_variantes_nombre(self.nombre_completo)]
        campos = [self.ciudad, self.profesion_cargo, self.empresa_organizacion]
        terminos += [c.strip() for c in campos if c]
        if self.alias:
            terminos += [a.strip() for a in self.alias.split(",") if a.strip()]
        if self.palabras_relacionadas:
            terminos += [p.strip() for p in self.palabras_relacionadas.split(",") if p.strip()]
        return terminos


class Fuente(Base):
    """RF2 - Administración de fuentes por país."""
    __tablename__ = "fuentes"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(255), nullable=False)
    url_inicial = Column(String(1000), nullable=False)
    pais = Column(String(100), nullable=False)  # ámbito del contenido, no del servidor
    tipo = Column(Enum(TipoFuente), nullable=False, default=TipoFuente.OTRO)
    activa = Column(Boolean, default=True)
    creado_en = Column(DateTime, default=datetime.utcnow)

    # Evidencia de CÓMO se determinó el país (RF2: debe corresponder al
    # ámbito del contenido, no a la ubicación del servidor). Se guarda
    # para poder mostrarlo/auditarlo en la sustentación.
    pais_detectado_automaticamente = Column(Boolean, default=False)
    confianza_deteccion_pais = Column(Float, nullable=True)
    evidencia_deteccion_pais = Column(String(500), nullable=True)


class Busqueda(Base):
    """Una ejecución de búsqueda/crawling para una persona en un país."""
    __tablename__ = "busquedas"

    id = Column(Integer, primary_key=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    pais = Column(String(100), nullable=False)
    max_workers = Column(Integer, default=5)
    max_urls = Column(Integer, default=100)
    max_profundidad = Column(Integer, default=2)  # saltos de enlaces desde la seed URL
    estado = Column(String(50), default="PENDIENTE")  # PENDIENTE/EN_CURSO/FINALIZADA
    grupo_benchmark = Column(String(50), nullable=True)  # agrupa corridas 1-vs-N workers
    conflictos_evitados = Column(Integer, nullable=True)  # evidencia RF4 (ver state_manager)
    iniciado_en = Column(DateTime, default=datetime.utcnow)
    finalizado_en = Column(DateTime, nullable=True)

    persona = relationship("Persona", back_populates="busquedas")
    urls = relationship("UrlRegistro", back_populates="busqueda",
                         cascade="all, delete-orphan")
    documentos = relationship("Documento", back_populates="busqueda",
                               cascade="all, delete-orphan")
    metricas = relationship("MetricaEjecucion", back_populates="busqueda",
                             cascade="all, delete-orphan")


class UrlRegistro(Base):
    """
    RF3/RF4 - Registro y control concurrente de cada URL descubierta.

    El campo `estado` es el recurso crítico compartido: múltiples workers
    pueden descubrir la misma URL casi simultáneamente. La transición
    PENDIENTE -> EN_PROCESAMIENTO debe hacerse de forma atómica (ver
    app/crawler/state_manager.py) para que ningún worker procese una URL
    ya tomada por otro.
    """
    __tablename__ = "urls"
    __table_args__ = (UniqueConstraint("busqueda_id", "url", name="uq_busqueda_url"),)

    id = Column(Integer, primary_key=True)
    busqueda_id = Column(Integer, ForeignKey("busquedas.id"), nullable=False)
    url = Column(String(2000), nullable=False)
    fuente_id = Column(Integer, ForeignKey("fuentes.id"), nullable=True)
    estado = Column(Enum(EstadoURL), default=EstadoURL.PENDIENTE, nullable=False)
    profundidad = Column(Integer, default=0)
    motivo_descarte = Column(String(500), nullable=True)
    worker_id = Column(String(50), nullable=True)  # qué hilo la procesó (evidencia RF3/RF4)
    intentos = Column(Integer, default=0)
    descubierta_en = Column(DateTime, default=datetime.utcnow)
    procesada_en = Column(DateTime, nullable=True)

    busqueda = relationship("Busqueda", back_populates="urls")


class Documento(Base):
    """RF5/RF6/RF7/RF8 - Documento extraído, verificado y clasificado."""
    __tablename__ = "documentos"
    __table_args__ = (UniqueConstraint("busqueda_id", "url", name="uq_doc_busqueda_url"),)

    id = Column(Integer, primary_key=True)
    busqueda_id = Column(Integer, ForeignKey("busquedas.id"), nullable=False)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    fuente_id = Column(Integer, ForeignKey("fuentes.id"), nullable=True)

    titulo = Column(String(500), nullable=True)
    url = Column(String(2000), nullable=False)
    pais = Column(String(100), nullable=True)
    fecha_publicacion = Column(DateTime, nullable=True)
    fecha_consulta = Column(DateTime, default=datetime.utcnow)
    contenido_texto = Column(Text, nullable=True)

    coincidencias_encontradas = Column(String(500), nullable=True)  # RF5
    score_identidad = Column(Float, default=0.0)  # RF7
    estado_verificacion = Column(Enum(EstadoVerificacion),
                                  default=EstadoVerificacion.NO_DETERMINADO)
    clasificacion_contextual = Column(Enum(ClasificacionContextual),
                                       default=ClasificacionContextual.NO_DETERMINADO)  # RF8
    justificacion_clasificacion = Column(String(500), nullable=True)

    busqueda = relationship("Busqueda", back_populates="documentos")


class MetricaEjecucion(Base):
    """
    Soporta el requisito de 'Medición de concurrencia': tiempos de ejecución
    de RF3/RF4/RF5/RF7/RF8, y el comparativo 1 vs. múltiples workers.
    """
    __tablename__ = "metricas_ejecucion"

    id = Column(Integer, primary_key=True)
    busqueda_id = Column(Integer, ForeignKey("busquedas.id"), nullable=False)
    etapa = Column(String(50), nullable=False)  # CRAWLING, MATCHING, VERIFICACION, CLASIFICACION
    modo = Column(String(50), nullable=False)   # SECUENCIAL, THREADS, PROCESOS
    num_workers = Column(Integer, nullable=False)
    num_urls_procesadas = Column(Integer, default=0)
    tiempo_total_segundos = Column(Float, nullable=False)
    registrado_en = Column(DateTime, default=datetime.utcnow)

    busqueda = relationship("Busqueda", back_populates="metricas")
