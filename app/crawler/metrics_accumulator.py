"""
Acumulador de tiempos por etapa, thread-safe.

La nota de la rúbrica pide registrar tiempos de ejecución para RF3, RF4,
RF5, RF7 y RF8 -- no solo un tiempo total del pipeline. Cada worker
(hilo) llama a `registrar()` después de ejecutar cada sub-etapa
(descarga, control de estado, matching, verificación, clasificación).
Como varios hilos escriben al mismo tiempo, el acumulado está protegido
por un Lock -- es, en sí mismo, otro ejemplo pequeño de recurso
compartido protegido (además del URLStateManager de RF4).
"""
import threading


class AcumuladorTiempos:
    def __init__(self):
        self._lock = threading.Lock()
        self._totales: dict[str, dict[str, float]] = {}

    def registrar(self, etapa: str, segundos: float):
        with self._lock:
            entrada = self._totales.setdefault(etapa, {"tiempo_total": 0.0, "cuenta": 0})
            entrada["tiempo_total"] += segundos
            entrada["cuenta"] += 1

    def snapshot(self) -> dict[str, dict[str, float]]:
        with self._lock:
            return {k: dict(v) for k, v in self._totales.items()}
