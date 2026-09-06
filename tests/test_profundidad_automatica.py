"""
La profundidad de exploración no es un parámetro que el usuario deba
configurar (no lo exige ningún RF), pero debe escalar sola cuando se
pide un límite de URLs alto -- si no, con solo 2 saltos de enlaces
muchos sitios se agotan mucho antes de llegar a límites como 1000.
"""
from app.crawler.crawler_manager import calcular_profundidad_automatica


def test_limite_pequeno_usa_profundidad_base():
    assert calcular_profundidad_automatica(60) == 2
    assert calcular_profundidad_automatica(100) == 2


def test_limite_mediano_aumenta_profundidad():
    assert calcular_profundidad_automatica(300) == 3


def test_limite_alto_aumenta_mas():
    assert calcular_profundidad_automatica(700) == 4


def test_limite_muy_alto_como_1000():
    assert calcular_profundidad_automatica(1000) == 5


def test_sin_limite_usa_profundidad_alta():
    assert calcular_profundidad_automatica(None) == 5


def test_profundidad_es_monotona_no_decreciente():
    """A mayor límite pedido, la profundidad nunca debería bajar."""
    limites = [50, 100, 300, 500, 700, 1000, 5000]
    profundidades = [calcular_profundidad_automatica(l) for l in limites]
    assert profundidades == sorted(profundidades)
