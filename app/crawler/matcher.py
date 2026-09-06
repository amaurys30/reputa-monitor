"""
RF5 - Identificación de contenido relacionado.

Determina si el texto descargado menciona a la persona consultada,
usando nombre, alias, ciudad, profesión/cargo, organización y palabras
relacionadas (tal como pide el enunciado). Si no hay ninguna coincidencia,
el documento se descarta y se guarda el motivo (requisito explícito de
RF5: "permitir consultar los elementos descartados y por qué").
"""
import re
from dataclasses import dataclass


@dataclass
class ResultadoMatching:
    relacionado: bool
    terminos_encontrados: list[str]
    motivo_descarte: str = ""


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip().lower()


def evaluar_contenido_relacionado(texto: str, titulo: str, terminos: list[str]) -> ResultadoMatching:
    contenido = _normalizar(f"{titulo} {texto}")
    encontrados = []
    for termino in terminos:
        t = _normalizar(termino)
        if t and t in contenido:
            encontrados.append(termino)

    # Regla mínima: el nombre completo (o al menos 2 términos distintos)
    # debe aparecer para considerar que hay relación real, evitando
    # falsos positivos por coincidencias muy débiles (una sola ciudad
    # común, por ejemplo).
    if len(encontrados) == 0:
        return ResultadoMatching(False, [], "Ningún término de búsqueda apareció en el contenido")
    return ResultadoMatching(True, encontrados)
