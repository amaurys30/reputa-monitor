"""
Genera variantes plausibles de cómo alguien es mencionado en un texto,
a partir de su nombre completo registrado (RF1).

Problema real detectado en pruebas: exigir que el nombre completo de 4
palabras (nombre + segundo nombre + apellido + segundo apellido, muy
común en nombres colombianos) aparezca LITERALMENTE en un artículo es
demasiado estricto. En la práctica, casi nadie es mencionado por su
nombre legal completo en una noticia -- se le nombra por "nombre +
primer apellido" ("James Rodríguez"), a veces "nombre + segundo
apellido", o el nombre completo solo la primera vez que aparece.

Este módulo genera esas variantes (de más a menos específica) para que
tanto el matching (RF5) como la verificación de identidad (RF7) puedan
reconocer menciones realistas, no solo la forma legal completa.
"""


def generar_variantes_nombre(nombre_completo: str) -> list[tuple[str, float]]:
    """
    Devuelve [(variante, peso)], ordenado de más a menos específico.
    `peso` en [0, 1] indica qué tan "completa" es esa forma del nombre
    (1.0 = nombre completo tal cual; menor para formas parciales).
    """
    tokens = [t for t in nombre_completo.split() if t]
    n = len(tokens)

    if n <= 1:
        return [(nombre_completo, 1.0)] if nombre_completo else []
    if n == 2:
        return [(nombre_completo, 1.0)]  # "Nombre Apellido" ya es la forma mínima razonable

    variantes: dict[str, float] = {}

    # Formas contiguas: nombre completo, luego recortando por los extremos
    # ("James David Rodríguez Rubio" -> "James David Rodríguez", "David
    # Rodríguez Rubio", -> "James David", "David Rodríguez", etc.)
    for tam in range(n, 1, -1):
        peso = tam / n
        for i in range(0, n - tam + 1):
            variante = " ".join(tokens[i:i + tam])
            variantes[variante] = max(variantes.get(variante, 0), peso)

    # Formas ancladas al primer nombre + cada apellido individual, que es
    # como realmente se suele nombrar a alguien en español ("James
    # Rodríguez" o "James Rubio", saltándose el segundo nombre):
    for i in range(1, n):
        variante = f"{tokens[0]} {tokens[i]}"
        peso = 0.55  # razonable: nombre + un apellido identifica bastante bien
        variantes[variante] = max(variantes.get(variante, 0), peso)

    # De más específico (más largo/mayor peso) a menos específico, para
    # que el llamador pueda quedarse con la PRIMERA coincidencia hallada.
    return sorted(variantes.items(), key=lambda par: (-par[1], -len(par[0])))
