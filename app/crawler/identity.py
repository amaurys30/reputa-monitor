"""
RF7 - Verificación de identidad.

Enfoque: scoring explicable por campo (no una "caja negra"), fácil de
sustentar. Cada campo de la persona (RF1) que aparece cerca del nombre
en el texto suma peso al score. Con base en el score total se asigna
uno de los 4 estados obligatorios.

Esto es intencionalmente una heurística basada en reglas, documentada y
ajustable — es más defendible en la sustentación que un modelo de caja
negra, y cumple el requisito funcional igualmente.
"""
from dataclasses import dataclass

from app.crawler.matcher import _normalizar
from app.crawler.nombre_utils import generar_variantes_nombre
from app.models.models import EstadoVerificacion

PESOS = {
    "nombre_completo": 0.45,
    "ciudad": 0.15,
    "profesion_cargo": 0.15,
    "empresa_organizacion": 0.15,
    "alias": 0.10,
}

UMBRAL_MISMA_PERSONA = 0.55
UMBRAL_POSIBLE = 0.25


@dataclass
class ResultadoVerificacion:
    score: float
    estado: EstadoVerificacion
    variante_nombre_hallada: str | None = None


def verificar_identidad(texto: str, titulo: str, persona) -> ResultadoVerificacion:
    contenido = _normalizar(f"{titulo} {texto}")
    if not contenido:
        return ResultadoVerificacion(0.0, EstadoVerificacion.NO_DETERMINADO)

    score = 0.0
    variante_hallada = None
    peso_nombre = 0.0
    for variante, peso in generar_variantes_nombre(persona.nombre_completo):
        if _normalizar(variante) in contenido:
            variante_hallada = variante
            peso_nombre = peso
            break  # ya viene ordenado de más a menos específico

    nombre_presente = variante_hallada is not None
    contribucion_nombre = 0.0
    if nombre_presente:
        contribucion_nombre = PESOS["nombre_completo"] * peso_nombre
        score += contribucion_nombre

    if persona.ciudad and _normalizar(persona.ciudad) in contenido:
        score += PESOS["ciudad"]
    if persona.profesion_cargo and _normalizar(persona.profesion_cargo) in contenido:
        score += PESOS["profesion_cargo"]
    if persona.empresa_organizacion and _normalizar(persona.empresa_organizacion) in contenido:
        score += PESOS["empresa_organizacion"]
    if persona.alias:
        for alias in persona.alias.split(","):
            if alias.strip() and _normalizar(alias) in contenido:
                score += PESOS["alias"]
                break

    if not nombre_presente:
        # Hay coincidencia de términos secundarios (ciudad, profesión...)
        # pero no del nombre (en ninguna variante razonable) -> nunca
        # puede ser "MISMA_PERSONA"
        estado = (EstadoVerificacion.POSIBLE_COINCIDENCIA if score > 0
                  else EstadoVerificacion.NO_DETERMINADO)
        return ResultadoVerificacion(round(score, 2), estado, variante_hallada)

    # Señal explícita de "tocayo"/homónimo: el nombre aparece pero el
    # propio texto aclara que se trata de alguien distinto, o ninguno de
    # los datos secundarios registrados coincide pese a tener varios
    # registrados (fuerte indicio de homonimia, no de la misma persona).
    marcadores_homonimo = ["tocayo", "no confundir con", "otro", "distinto a", "diferente a"]
    hay_marcador_textual = any(m in contenido for m in marcadores_homonimo)
    secundarios_registrados = sum(1 for c in [persona.ciudad, persona.profesion_cargo,
                                               persona.empresa_organizacion] if c)

    if hay_marcador_textual and score <= contribucion_nombre:
        return ResultadoVerificacion(round(score, 2), EstadoVerificacion.PERSONA_DIFERENTE,
                                      variante_hallada)

    if secundarios_registrados >= 2 and score <= contribucion_nombre:
        # Nombre coincide pero NINGÚN dato secundario registrado aparece,
        # aun habiendo varios para contrastar -> probable homónimo.
        return ResultadoVerificacion(round(score, 2), EstadoVerificacion.PERSONA_DIFERENTE,
                                      variante_hallada)

    if score >= UMBRAL_MISMA_PERSONA:
        estado = EstadoVerificacion.MISMA_PERSONA
    elif score >= UMBRAL_POSIBLE:
        estado = EstadoVerificacion.POSIBLE_COINCIDENCIA
    else:
        estado = EstadoVerificacion.NO_DETERMINADO

    return ResultadoVerificacion(round(score, 2), estado, variante_hallada)
