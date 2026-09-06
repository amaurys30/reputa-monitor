"""
Script de "Medición de concurrencia" pedido explícitamente en la
rúbrica: "Compara 1 vs. múltiples workers bajo condiciones equivalentes,
registra métricas y analiza los resultados."

Uso (dentro del contenedor, ver README):
    python -m app.crawler.benchmark --persona-id 1 --pais Colombia \
        --workers 1 2 4 8 16 --max-urls 60

Para que la comparación sea justa ("condiciones equivalentes"), cada
corrida:
  - Usa la MISMA persona y el MISMO conjunto de fuentes/país.
  - Crea una Busqueda NUEVA e independiente por cada valor de `workers`
    (para no reprocesar URLs ya vistas ni reutilizar caché).
  - Limita la exploración al mismo `max_urls` y misma profundidad.

Al final genera:
  - Una tabla de resultados en consola.
  - Un gráfico PNG (docs/benchmark_resultados.png) tiempo vs. workers,
    listo para incluir en el informe/sustentación.
"""
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

from app.db.database import SessionLocal
from app.models.models import Busqueda
from app.crawler.crawler_manager import ejecutar_busqueda


def crear_busqueda(persona_id: int, pais: str, workers: int, max_urls: int) -> int:
    db = SessionLocal()
    try:
        b = Busqueda(persona_id=persona_id, pais=pais, max_workers=workers,
                     max_urls=max_urls, estado="PENDIENTE")
        db.add(b)
        db.commit()
        db.refresh(b)
        return b.id
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Benchmark de concurrencia del crawler")
    parser.add_argument("--persona-id", type=int, required=True)
    parser.add_argument("--pais", type=str, required=True)
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4, 8, 16])
    parser.add_argument("--max-urls", type=int, default=60)
    args = parser.parse_args()

    resultados = []
    for n in args.workers:
        busqueda_id = crear_busqueda(args.persona_id, args.pais, n, args.max_urls)
        print(f"\n=== Ejecutando benchmark con {n} worker(s) (busqueda_id={busqueda_id}) ===")
        resultado = ejecutar_busqueda(busqueda_id)
        resultados.append(resultado)

    print("\n\n===== RESULTADOS COMPARATIVOS =====")
    print(f"{'Workers':>8} | {'URLs procesadas':>16} | {'Tiempo (s)':>10} | {'Conflictos evitados':>20}")
    for r in resultados:
        print(f"{r['workers']:>8} | {r['urls_procesadas']:>16} | "
              f"{r['tiempo_total_segundos']:>10} | {r['conflictos_evitados']:>20}")

    try:
        import matplotlib.pyplot as plt
        workers = [r["workers"] for r in resultados]
        tiempos = [r["tiempo_total_segundos"] for r in resultados]

        fig, ax = plt.subplots(figsize=(7, 5))
        ax.plot(workers, tiempos, marker="o")
        ax.set_xlabel("Número de workers (threads)")
        ax.set_ylabel("Tiempo total de crawling (segundos)")
        ax.set_title("Medición de concurrencia: tiempo vs. número de workers")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig("docs/benchmark_resultados.png", dpi=150)
        print("\nGráfico guardado en docs/benchmark_resultados.png")
    except Exception as e:
        print(f"No se pudo generar el gráfico: {e}")


if __name__ == "__main__":
    main()
