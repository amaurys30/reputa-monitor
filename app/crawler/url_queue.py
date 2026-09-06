"""
RF3 - Cola compartida de procesamiento.

queue.Queue de la librería estándar ya es thread-safe internamente (usa
un Lock + Condition variables por debajo); es la estructura estándar de
Python para el patrón productor-consumidor y por eso la usamos como la
cola compartida entre todos los workers del pool.

Problema de diseño a resolver (terminación dinámica): el número total
de URLs a procesar NO se conoce de antemano, porque cada worker puede
descubrir e insertar nuevas URLs mientras el crawling está en curso.
Por lo tanto NO podemos simplemente "esperar hasta que la cola esté
vacía" con un timeout. Solución estándar: usamos el contador interno de
tareas no terminadas de queue.Queue (`task_done()` / `join()`):
  - Cada `put()` incrementa un contador de "tareas pendientes".
  - Cada `task_done()` lo decrementa.
  - `join()` bloquea al hilo principal hasta que el contador llegue a 0,
    sin importar cuántas veces se hayan insertado ítems nuevos mientras
    tanto.
Cuando `join()` retorna, se garantiza que TODA URL descubierta ya fue
procesada. Solo entonces se envían N sentinelas (None) para que cada
worker termine su ciclo de vida.

BUG CORREGIDO -- "cupo" del límite de exploración:
Antes, un worker primero CREABA el registro de una URL nueva en la BD
(estado PENDIENTE) y solo DESPUÉS intentaba encolarla; si el límite de
exploración ya se había alcanzado, `put()` simplemente rechazaba el
ítem -- pero el registro en la BD ya existía y, al no estar en la cola,
ningún worker lo tomaría jamás. Resultado observado: cientos de URLs
"PENDIENTE" para siempre incluso con la búsqueda ya FINALIZADA.

La corrección invierte el orden: primero se debe "reservar un cupo"
atómicamente con `intentar_reservar_slot()`; solo si se obtiene el
cupo se procede a registrar la URL en la BD y encolarla. Así nunca se
crea un registro que no vaya a ser procesado.

También se corrige una segunda condición de carrera: el contador
`_urls_encoladas` se incrementaba SIN lock, así que bajo alta
concurrencia el "check-then-act" (¿hay cupo? -> incrementar) podía
dejar pasar más URLs de las permitidas por `max_urls`. Ahora esa
verificación + incremento es una única operación atómica, protegida
por un `Lock` (el mismo patrón que `URLStateManager` usa para RF4).
"""
import threading
import queue

# Valor centinela: al recibirlo, un worker sabe que debe terminar.
SENTINEL = None


class ColaURLsCompartida:
    def __init__(self, max_urls: int | None = None):
        self._queue: queue.Queue = queue.Queue()
        self.max_urls = max_urls
        self._urls_encoladas = 0
        self._lock_contador = threading.Lock()

    def intentar_reservar_slot(self) -> bool:
        """
        Verifica si aún hay cupo dentro del límite de exploración (RF3)
        y, si lo hay, lo reserva atómicamente incrementando el contador.
        Debe llamarse ANTES de registrar la URL en la base de datos --
        nunca después -- para no dejar registros huérfanos que jamás
        serán procesados.
        """
        with self._lock_contador:  # check + act atómico, evita URLs de más
            if self.max_urls is not None and self._urls_encoladas >= self.max_urls:
                return False
            self._urls_encoladas += 1
            return True

    def put(self, url_id):
        """
        Encola un ítem ya registrado en la BD. El control del límite de
        exploración NO ocurre aquí -- debe haberse reservado el cupo
        antes con `intentar_reservar_slot()`.
        """
        self._queue.put(url_id)

    def get(self):
        """Bloquea hasta que haya un ítem (o un sentinel de apagado)."""
        return self._queue.get()

    def task_done(self):
        self._queue.task_done()

    def join(self):
        """Bloquea hasta que todas las URLs puestas hayan sido procesadas."""
        self._queue.join()

    def enviar_sentinelas(self, n: int):
        for _ in range(n):
            self._queue.put(SENTINEL)

    def qsize(self) -> int:
        return self._queue.qsize()

    @property
    def total_encoladas(self) -> int:
        with self._lock_contador:
            return self._urls_encoladas
