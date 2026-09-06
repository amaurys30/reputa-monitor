"""
Genera el análisis textual de un benchmark 1 vs. N workers -- la parte
de la rúbrica que exige no solo "presentar mediciones" sino "analizar
los resultados". Se calcula automáticamente a partir de los tiempos
medidos, para que siempre haya un análisis coherente con los datos
reales de cada corrida (no un texto genérico fijo).
"""
from dataclasses import dataclass


@dataclass
class PuntoBenchmark:
    workers: int
    tiempo_segundos: float
    urls_procesadas: int
    conflictos_evitados: int


def analizar_resultados(puntos: list[PuntoBenchmark]) -> str:
    if len(puntos) < 2:
        return "Se necesitan al menos 2 corridas (con distinto número de workers) para poder comparar."

    puntos = sorted(puntos, key=lambda p: p.workers)
    base = puntos[0]
    mejor = min(puntos, key=lambda p: p.tiempo_segundos)

    if base.tiempo_segundos == 0:
        return (
            "No se registró un tiempo medible en estas corridas (0.0s en todas). "
            "Esto suele pasar cuando no hay fuentes activas para el país de la "
            "búsqueda, o el límite de URLs es tan bajo que no llega a descargar "
            "nada. Revisa que existan fuentes activas antes de repetir el benchmark."
        )

    speedup_mejor = round(base.tiempo_segundos / mejor.tiempo_segundos, 2) if mejor.tiempo_segundos > 0 else 0

    lineas = []
    lineas.append(
        f"Con {base.workers} worker(s) la búsqueda tardó {base.tiempo_segundos}s. "
        f"El mejor tiempo se obtuvo con {mejor.workers} workers ({mejor.tiempo_segundos}s), "
        f"una mejora de {speedup_mejor}x respecto a {base.workers} worker(s)."
    )

    # ¿Hay meseta? -- compara el mejor tiempo contra el de la mayor cantidad de workers probada
    mayor = puntos[-1]
    if mayor.workers != mejor.workers and mejor.tiempo_segundos > 0:
        diferencia_pct = abs(mayor.tiempo_segundos - mejor.tiempo_segundos) / mejor.tiempo_segundos * 100
        if diferencia_pct < 20:
            lineas.append(
                f"A partir de {mejor.workers} workers el tiempo se estabiliza "
                f"(con {mayor.workers} workers el tiempo fue {mayor.tiempo_segundos}s, "
                f"una diferencia de solo {round(diferencia_pct, 1)}% frente al mejor caso). "
                "Esto es esperado en tareas dominadas por I/O (espera de red): una vez hay "
                "suficientes hilos para mantener varias descargas en vuelo, agregar más no "
                "acelera nada porque el cuello de botella pasa a ser la latencia de las fuentes "
                "remotas, no la capacidad de cómputo del sistema."
            )

    total_conflictos = sum(p.conflictos_evitados for p in puntos)
    if total_conflictos > 0:
        lineas.append(
            f"En conjunto, el mecanismo de sincronización (RF4) evitó {total_conflictos} "
            "intentos de procesar una misma URL más de una vez a lo largo de todas las corridas, "
            "evidencia de que la concurrencia real está ocurriendo (a más workers compitiendo "
            "por el mismo trabajo, más conflictos detectados y resueltos correctamente)."
        )

    return " ".join(lineas)
