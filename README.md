# Reputa Monitor

Taller Práctico #1 — Sistemas Distribuidos — CECAR
Amaurys Castro De Arco - Daniel Jiménez Salcedo - Sofia Suancha Contreras
Programación Concurrente (Threading), Crawling, Indexación y Procesamiento de Información.

Plataforma que localiza contenido público en Internet relacionado con
una persona, usando un **crawler concurrente basado en threads**,
verifica si el contenido corresponde a esa persona y clasifica su
contexto como POSITIVO/NEUTRO/NEGATIVO/NO DETERMINADO.

## Índice

- [Cómo levantar el proyecto](#cómo-levantar-el-proyecto)
- [Cómo usarlo](#cómo-usarlo)
- [Dónde está cada requisito funcional](#dónde-está-cada-requisito-funcional)
- [Cómo demostrar la concurrencia (para la sustentación)](#cómo-demostrar-la-concurrencia)
- [Documentación / entregables](#documentación--entregables)

## Cómo levantar el proyecto

Requiere Docker y Docker Compose.

```bash
git clone <url-del-repo>
cd reputa-monitor
docker compose up --build
```

Esto levanta:
- `reputa_api` → FastAPI en `http://localhost:8000`
- `reputa_db` → PostgreSQL en el puerto `5432`

Las tablas se crean automáticamente al iniciar (evento `startup` de FastAPI).

### Limpiar todos los datos (empezar de cero, sin cambios de esquema)

```bash
docker compose exec api python -m app.db.reset
```

Pide confirmación antes de borrar. Alternativa más agresiva (recrea todo el volumen de Postgres):

```bash
docker compose down -v
docker compose up --build
```

## Cómo usarlo

1. Abrir `http://localhost:8000`
2. **Registrar persona** (RF1): nombre completo y país son obligatorios.
3. **Fuentes** (RF2): agregar/activar fuentes por país.
4. **Nueva búsqueda**: elegir persona, país, **número de workers** y
   límite de URLs, e iniciar el crawling.
5. La búsqueda corre en segundo plano; refrescar la página de
   resultados para ver el avance, los documentos encontrados, los
   descartados (con motivo) y las métricas de tiempo.

También existe una API JSON equivalente en `/api/personas`,
`/api/fuentes`, `/api/busquedas`, `/api/documentos` (ver
`http://localhost:8000/docs` para la documentación interactiva
autogenerada por FastAPI).

## Dónde está cada requisito funcional

| RF | Descripción | Ubicación en el código |
|---|---|---|
| RF1 | Registro de persona | `app/models/models.py::Persona`, `app/api/personas.py`, `templates/persona_form.html` |
| RF2 | Fuentes por país | `app/models/models.py::Fuente`, `app/api/fuentes.py`, `templates/fuentes.html` |
| RF3 | Crawler concurrente | `app/crawler/crawler_manager.py`, `app/crawler/worker.py`, `app/crawler/url_queue.py` |
| RF4 | Control concurrente de URLs | `app/crawler/state_manager.py` (Lock + máquina de estados) |
| RF5 | Contenido relacionado | `app/crawler/matcher.py`, descartados consultables en `/busquedas/{id}` |
| RF6 | Extracción y persistencia | `app/crawler/fetcher.py`, `app/crawler/worker.py`, `UniqueConstraint` en `Documento` |
| RF7 | Verificación de identidad | `app/crawler/identity.py` |
| RF8 | Clasificación contextual | `app/crawler/classifier.py` |
| RF9 | Consulta y filtrado | `app/main.py::ver_busqueda`, `templates/resultados.html` |
| Medición de concurrencia | Comparar 1 vs. N workers | `app/crawler/benchmark.py`, tabla `MetricaEjecucion` |

## Cómo demostramos la concurrencia

###  Benchmark 1 vs. N workers (requisito explícito de la rúbrica)

```bash
docker compose exec api python -m app.crawler.benchmark \
    --persona-id 1 --pais Colombia --workers 1 2 4 8 16 --max-urls 60
```

Corre la misma búsqueda con distinto número de workers bajo
condiciones equivalentes, imprime una tabla comparativa y genera
`docs/benchmark_resultados.png` (tiempo vs. workers) en la web la podemos hacer igualmente configurando los parametros de prueba.

## Documentación / entregables

- [`docs/MODELO_DATOS.md`](docs/MODELO_DATOS.md) — diagrama entidad-relación (Mermaid)
- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) — diagrama de arquitectura de software (Mermaid)
- [`docs/INFRAESTRUCTURA.md`](docs/INFRAESTRUCTURA.md) — diagrama de infraestructura/despliegue (Mermaid)
- Código fuente — este repositorio

