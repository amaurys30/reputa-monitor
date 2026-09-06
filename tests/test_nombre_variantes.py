"""
Prueba de regresión: el problema real reportado fue que un nombre de 4
palabras (nombre + segundo nombre + apellido + segundo apellido) casi
nunca aparece así, literalmente, en un artículo real -- la gente se
refiere a alguien por "nombre + un apellido". Este módulo verifica que
ahora sí se reconocen esas formas parciales realistas.
"""
from dataclasses import dataclass

from app.crawler.nombre_utils import generar_variantes_nombre
from app.crawler.identity import verificar_identidad
from app.models.models import EstadoVerificacion


@dataclass
class PersonaFake:
    nombre_completo: str
    ciudad: str | None = None
    profesion_cargo: str | None = None
    empresa_organizacion: str | None = None
    alias: str | None = None


def test_variantes_incluyen_nombre_completo_como_mas_especifica():
    variantes = generar_variantes_nombre("James David Rodríguez Rubio")
    assert variantes[0][0] == "James David Rodríguez Rubio"
    assert variantes[0][1] == 1.0


def test_variantes_incluyen_nombre_mas_un_apellido():
    variantes_texto = [v for v, _p in generar_variantes_nombre("James David Rodríguez Rubio")]
    assert "James Rodríguez" in variantes_texto
    assert "James Rubio" in variantes_texto


def test_nombre_de_dos_palabras_no_genera_variantes_de_una_palabra():
    variantes = generar_variantes_nombre("Gustavo Petro")
    assert variantes == [("Gustavo Petro", 1.0)]
    # nunca debe proponer "Gustavo" solo o "Petro" solo -- demasiado
    # ambiguo (cualquier "Gustavo" del mundo calzaría).


def test_deteccion_ahora_reconoce_nombre_parcial_realista():
    """
    Este es el caso exacto reportado: con el nombre completo (4
    palabras) el sistema NO detectaba a la persona, pero sí cuando se
    usaba una forma más corta y reconocible. Ahora ambas deben
    funcionar sin que el usuario tenga que cambiar los datos de RF1.
    """
    persona = PersonaFake(nombre_completo="James David Rodríguez Rubio")
    texto = "James Rodríguez fue destacado por su labor en la comunidad."

    resultado = verificar_identidad(texto, titulo="", persona=persona)
    assert resultado.variante_nombre_hallada == "James Rodríguez"
    assert resultado.score > 0


def test_nombre_completo_exacto_sigue_dando_el_score_maximo():
    """El caso ya soportado (nombre completo literal) no debe empeorar."""
    persona = PersonaFake(nombre_completo="Gustavo Petro", ciudad="Bogotá",
                           empresa_organizacion="Gobierno de Colombia")
    texto = "Gustavo Petro, desde Bogotá, lideró una reunión del Gobierno de Colombia."
    resultado = verificar_identidad(texto, titulo="", persona=persona)
    assert resultado.estado == EstadoVerificacion.MISMA_PERSONA
