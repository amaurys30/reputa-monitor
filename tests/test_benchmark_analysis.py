from app.crawler.benchmark_analysis import PuntoBenchmark, analizar_resultados


def test_detecta_speedup_y_meseta():
    puntos = [
        PuntoBenchmark(workers=1, tiempo_segundos=27.2, urls_procesadas=60, conflictos_evitados=0),
        PuntoBenchmark(workers=4, tiempo_segundos=7.0, urls_procesadas=60, conflictos_evitados=5),
        PuntoBenchmark(workers=8, tiempo_segundos=7.7, urls_procesadas=60, conflictos_evitados=11),
    ]
    texto = analizar_resultados(puntos)
    assert "27.2" in texto
    assert "7.0" in texto
    assert "mejora" in texto.lower()
    assert "meseta" in texto.lower() or "estabiliza" in texto.lower()


def test_menciona_conflictos_evitados_si_hay():
    puntos = [
        PuntoBenchmark(workers=1, tiempo_segundos=10.0, urls_procesadas=20, conflictos_evitados=0),
        PuntoBenchmark(workers=8, tiempo_segundos=3.0, urls_procesadas=20, conflictos_evitados=15),
    ]
    texto = analizar_resultados(puntos)
    assert "15" in texto


def test_mensaje_claro_cuando_no_hay_tiempo_medible():
    """Si no hubo fuentes activas, todos los tiempos pueden dar 0.0 --
    el mensaje debe explicar la causa probable, no decir 'mejora de 0x'."""
    puntos = [
        PuntoBenchmark(workers=1, tiempo_segundos=0.0, urls_procesadas=0, conflictos_evitados=0),
        PuntoBenchmark(workers=2, tiempo_segundos=0.0, urls_procesadas=0, conflictos_evitados=0),
    ]
    texto = analizar_resultados(puntos)
    assert "0x" not in texto
    assert "fuentes activas" in texto


def test_requiere_al_menos_dos_puntos():
    texto = analizar_resultados([
        PuntoBenchmark(workers=1, tiempo_segundos=10.0, urls_procesadas=20, conflictos_evitados=0),
    ])
    assert "al menos 2" in texto
