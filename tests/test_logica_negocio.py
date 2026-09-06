"""RF5, RF7, RF8 - pruebas unitarias de la lógica de negocio pura."""
from dataclasses import dataclass

from app.crawler.matcher import evaluar_contenido_relacionado
from app.crawler.identity import verificar_identidad
from app.crawler.classifier import clasificar_contexto
from app.models.models import EstadoVerificacion, ClasificacionContextual


@dataclass
class PersonaFake:
    nombre_completo: str
    ciudad: str | None = None
    profesion_cargo: str | None = None
    empresa_organizacion: str | None = None
    alias: str | None = None


def test_matching_descarta_contenido_sin_relacion():
    resultado = evaluar_contenido_relacionado(
        texto="El pronóstico del tiempo indica lluvias en la tarde.",
        titulo="Clima de hoy",
        terminos=["Juan Perez", "Sincelejo"],
    )
    assert resultado.relacionado is False
    assert resultado.motivo_descarte


def test_matching_detecta_contenido_relacionado():
    resultado = evaluar_contenido_relacionado(
        texto="Juan Perez fue premiado por su trabajo en Sincelejo.",
        titulo="Reconocimiento",
        terminos=["Juan Perez", "Sincelejo"],
    )
    assert resultado.relacionado is True
    assert "Juan Perez" in resultado.terminos_encontrados


def test_verificacion_identidad_misma_persona():
    persona = PersonaFake(nombre_completo="Juan Perez", ciudad="Sincelejo",
                           empresa_organizacion="Acme Corp")
    resultado = verificar_identidad(
        texto="Juan Perez, gerente de Acme Corp en Sincelejo, fue premiado.",
        titulo="", persona=persona,
    )
    assert resultado.estado == EstadoVerificacion.MISMA_PERSONA


def test_verificacion_identidad_no_determinado_sin_nombre():
    persona = PersonaFake(nombre_completo="Juan Perez", ciudad="Sincelejo")
    resultado = verificar_identidad(
        texto="En Sincelejo se celebró un evento cultural este fin de semana.",
        titulo="", persona=persona,
    )
    assert resultado.estado in (EstadoVerificacion.NO_DETERMINADO,
                                 EstadoVerificacion.POSIBLE_COINCIDENCIA)


def test_clasificacion_negativa():
    resultado = clasificar_contexto(
        texto="Juan Perez fue acusado de fraude en un contrato con el estado.",
        titulo="", nombre_persona="Juan Perez",
    )
    assert resultado.clasificacion == ClasificacionContextual.NEGATIVO


def test_clasificacion_positiva():
    resultado = clasificar_contexto(
        texto="Juan Perez recibió un premio por su aporte a la innovación local.",
        titulo="", nombre_persona="Juan Perez",
    )
    assert resultado.clasificacion == ClasificacionContextual.POSITIVO


def test_clasificacion_neutra_sin_señales():
    resultado = clasificar_contexto(
        texto="Juan Perez asistió a una reunión de trabajo el martes.",
        titulo="", nombre_persona="Juan Perez",
    )
    assert resultado.clasificacion == ClasificacionContextual.NEUTRO
