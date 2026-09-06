"""
DEMO PARA SUSTENTACIÓN — Condición de carrera: sin sincronización vs. con Lock.

Este script NO usa la base de datos ni la red: aísla el problema de
concurrencia en su forma más pura (un contador/estado compartido en
memoria) para poder EXPLICARLO y DEMOSTRARLO en 30 segundos frente al
profesor, sin ruido de HTTP ni SQL de por medio.

Ejecutar:
    python -m app.crawler.demo_race_condition

Qué hace:
  1. Simula 30 "workers" (threads) que compiten por tomar las MISMAS
     10 urls de una lista de PENDIENTES.
  2. Corre primero la versión INSEGURA (check-then-act sin Lock, con un
     `time.sleep` artificial para agrandar la ventana de la condición de
     carrera y que el problema sea observable de forma consistente).
  3. Corre la versión SEGURA (con `threading.Lock`, igual a como está
     implementado realmente en app/crawler/state_manager.py).
  4. Compara cuántas urls terminaron siendo tomadas por MÁS de un
     worker en cada caso.
"""
import random
import threading
import time

N_WORKERS = 30
N_URLS = 10


def version_insegura():
    """Check-then-act SIN lock -> reproduce la condición de carrera."""
    estados = {i: "PENDIENTE" for i in range(N_URLS)}
    tomadas_por = {i: [] for i in range(N_URLS)}

    def worker(worker_id):
        url_id = random.randint(0, N_URLS - 1)
        if estados[url_id] == "PENDIENTE":          # <-- "check"
            time.sleep(0.001)                        # ventana de carrera
            estados[url_id] = "EN_PROCESAMIENTO"      # <-- "act"
            tomadas_por[url_id].append(worker_id)

    hilos = [threading.Thread(target=worker, args=(i,)) for i in range(N_WORKERS)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    duplicadas = {u: w for u, w in tomadas_por.items() if len(w) > 1}
    return duplicadas


def version_segura():
    """Check-then-act CON lock -> sección crítica atómica."""
    estados = {i: "PENDIENTE" for i in range(N_URLS)}
    tomadas_por = {i: [] for i in range(N_URLS)}
    lock = threading.Lock()

    def worker(worker_id):
        url_id = random.randint(0, N_URLS - 1)
        with lock:                                    # <-- check + act atómico
            if estados[url_id] == "PENDIENTE":
                time.sleep(0.001)
                estados[url_id] = "EN_PROCESAMIENTO"
                tomadas_por[url_id].append(worker_id)

    hilos = [threading.Thread(target=worker, args=(i,)) for i in range(N_WORKERS)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    duplicadas = {u: w for u, w in tomadas_por.items() if len(w) > 1}
    return duplicadas


def main():
    print(f"Simulando {N_WORKERS} workers compitiendo por {N_URLS} URLs...\n")

    print("=== 1) SIN Lock (check-then-act inseguro) ===")
    dup_inseguro = version_insegura()
    if dup_inseguro:
        print(f"FALLA DETECTADA: {len(dup_inseguro)} URL(s) fueron tomadas por más de un worker:")
        for url_id, workers in dup_inseguro.items():
            print(f"   URL#{url_id} tomada por workers: {workers}")
    else:
        print("(no se manifestó esta vez — la condición de carrera es no determinista; "
              "reintenta el script si hace falta para verla)")

    print("\n=== 2) CON Lock (sección crítica atómica, como en state_manager.py) ===")
    dup_seguro = version_segura()
    if dup_seguro:
        print(f"INESPERADO: {len(dup_seguro)} URL(s) duplicadas incluso con Lock (no debería pasar)")
    else:
        print("Ninguna URL fue tomada por más de un worker. El Lock garantiza exclusión mutua.")

    print("\n=== CONCLUSIÓN PARA LA SUSTENTACIÓN ===")
    print("Sin sincronización, el patrón 'check-then-act' sobre un estado compartido")
    print("es intrínsecamente inseguro entre threads: dos pueden pasar el chequeo")
    print("antes de que cualquiera actualice el estado. El Lock convierte el chequeo")
    print("y la actualización en una única operación atómica, eliminando la ventana")
    print("de carrera. Esto es exactamente lo que hace URLStateManager en RF4.")


if __name__ == "__main__":
    main()
