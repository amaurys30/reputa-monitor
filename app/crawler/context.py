"""
Objetos de contexto inmutables y "planos" (no ORM) para pasar entre
threads.

Motivo: las sesiones y objetos de SQLAlchemy NO son thread-safe. Si
pasáramos directamente el objeto ORM `Busqueda` (cargado por la sesión
del hilo principal) a los workers, cada worker podría disparar una
carga perezosa (lazy load) de `busqueda.persona` usando esa MISMA
sesión desde un hilo distinto -> comportamiento indefinido / errores
intermitentes difíciles de reproducir.

Solución: leemos todo lo necesario UNA vez en el hilo principal, antes
de lanzar el pool, y lo empaquetamos en dataclasses simples de solo
lectura. Cada worker abre su propia sesión (ver worker.py) si necesita
tocar la base de datos.
"""
from dataclasses import dataclass

from app.crawler.nombre_utils import generar_variantes_nombre


@dataclass(frozen=True)
class PersonaContexto:
    id: int
    nombre_completo: str
    ciudad: str | None
    profesion_cargo: str | None
    empresa_organizacion: str | None
    alias: str | None
    palabras_relacionadas: str | None

    def palabras_clave(self) -> list[str]:
        # Variantes realistas del nombre (RF5): "James Rodríguez", no solo
        # el nombre legal completo de 4 palabras -- ver nombre_utils.py.
        terminos = [variante for variante, _peso in generar_variantes_nombre(self.nombre_completo)]
        campos = [self.ciudad, self.profesion_cargo, self.empresa_organizacion]
        terminos += [c.strip() for c in campos if c]
        if self.alias:
            terminos += [a.strip() for a in self.alias.split(",") if a.strip()]
        if self.palabras_relacionadas:
            terminos += [p.strip() for p in self.palabras_relacionadas.split(",") if p.strip()]
        return terminos


@dataclass(frozen=True)
class BusquedaContexto:
    id: int
    pais: str
    persona: PersonaContexto


def construir_contexto(busqueda) -> BusquedaContexto:
    """Se llama UNA vez, en el hilo principal, con la sesión del manager."""
    p = busqueda.persona
    persona_ctx = PersonaContexto(
        id=p.id,
        nombre_completo=p.nombre_completo,
        ciudad=p.ciudad,
        profesion_cargo=p.profesion_cargo,
        empresa_organizacion=p.empresa_organizacion,
        alias=p.alias,
        palabras_relacionadas=p.palabras_relacionadas,
    )
    return BusquedaContexto(id=busqueda.id, pais=busqueda.pais, persona=persona_ctx)
