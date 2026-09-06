# Reputa Monitor

Taller Práctico #1 — Sistemas Distribuidos — CECAR
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
- [Decisiones técnicas clave](#decisiones-técnicas-clave)

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

### Poblar fuentes de ejemplo (opcional)

```bash
docker compose exec api python -m app.db.seed
```

### ⚠️ Si vienes de una versión anterior del proyecto

Esta versión agrega columnas nuevas a la tabla `fuentes` (para guardar
la evidencia de la detección automática de país). Como el proyecto no
usa migraciones (Alembic), **necesitas recrear el esquema completo**,
no solo vaciar los datos:

```bash
docker compose down -v
docker compose up --build
```

`app.db.reset` (ver más abajo) solo vacía datos, **no** agrega columnas
nuevas a tablas ya existentes — no sirve para este caso.

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
3. **Fuentes** (RF2): agregar/activar fuentes por país (o usar el seed).
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

## Cómo demostrar la concurrencia

Esto es lo que más pesa en la rúbrica (29% entre RF3+RF4+medición), y
lo que hay que mostrar en vivo en la sustentación:

### 1. Logs en vivo mostrando varios workers trabajando en paralelo

Al iniciar una búsqueda con, por ejemplo, 8 workers, los logs del
contenedor (`docker compose logs -f api`) muestran líneas como:

```
[CrawlerWorker-3] Descargando https://sitio.com/noticia-1
[CrawlerWorker-5] Descargando https://sitio.com/noticia-2
[CrawlerWorker-1] Terminó https://sitio.com/pagina-3 en 0.41s
```

Nombres de hilo distintos procesando URLs distintas *al mismo tiempo*
es la evidencia de que el paralelismo es real, no secuencial.

### 2. Prueba de condición de carrera (sin lock vs. con lock)

```bash
docker compose exec api python -m app.crawler.demo_race_condition
```

Este script aísla el problema de sincronización en su forma más pura:
30 threads compitiendo por 10 "URLs" simuladas. Muestra que **sin**
`Lock` varias URLs terminan tomadas por más de un worker (condición de
carrera reproducible), y que **con** `Lock` (igual a como está
implementado en `state_manager.py`) eso nunca ocurre.

### 3. Benchmark 1 vs. N workers (requisito explícito de la rúbrica)

```bash
docker compose exec api python -m app.crawler.benchmark \
    --persona-id 1 --pais Colombia --workers 1 2 4 8 16 --max-urls 60
```

Corre la misma búsqueda con distinto número de workers bajo
condiciones equivalentes, imprime una tabla comparativa y genera
`docs/benchmark_resultados.png` (tiempo vs. workers) para incluir en
el informe.

## Documentación / entregables

- [`docs/MODELO_DATOS.md`](docs/MODELO_DATOS.md) — diagrama entidad-relación (Mermaid)
- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) — diagrama de arquitectura de software (Mermaid)
- [`docs/INFRAESTRUCTURA.md`](docs/INFRAESTRUCTURA.md) — diagrama de infraestructura/despliegue (Mermaid)
- Código fuente — este repositorio

Los diagramas están en Mermaid porque GitHub los renderiza
automáticamente al ver el `.md`; no hace falta abrir ninguna
herramienta externa para revisarlos.

## Decisiones técnicas clave

- **Detección automática del país de una fuente por su contenido, no
  por su servidor (RF2)**: al guardar una fuente, el sistema descarga
  la URL semilla y analiza señales del propio contenido —el atributo
  `lang` del HTML, el meta tag `og:locale`, el dominio de código de
  país (ccTLD) y un análisis léxico de gentilicios/ciudades— para
  determinar el país. **Nunca** se resuelve la IP del servidor ni se
  usa geolocalización/whois (ver `app/crawler/country_detector.py`,
  con un test que documenta explícitamente esta garantía). Si ninguna
  señal es suficientemente confiable, el sistema no adivina: le pide
  al administrador que lo confirme manualmente, igual que se hace con
  `fecha_publicacion` en RF6 ("cuando esté disponible").

- **Threads, no procesos**, para el crawling: la tarea es I/O-bound
  (esperar respuestas HTTP), y en Python el GIL se libera durante I/O,
  por lo que `threading` da paralelismo real ahí sin el overhead de
  `multiprocessing` (serialización entre procesos, mayor consumo de
  memoria).
- **`queue.Queue` + `join()`/`task_done()` + sentinelas** para la cola
  compartida: el número total de URLs no se conoce de antemano (se
  descubren dinámicamente), así que no basta con "esperar a que la
  cola esté vacía" — se usa el contador interno de tareas pendientes de
  `queue.Queue`, el patrón estándar de Python para este problema.
- **Un `Lock` de sección crítica mínima** en `URLStateManager`: solo
  protege la transición de estado (una operación de BD muy corta); la
  descarga HTTP —lo lento— siempre ocurre fuera del lock, para no
  serializar innecesariamente el trabajo pesado.
- **Objetos planos (no ORM) para pasar datos entre threads**
  (`app/crawler/context.py`): las sesiones y objetos de SQLAlchemy no
  son thread-safe, así que los datos de la persona/búsqueda se leen
  una vez y se empaquetan en un `dataclass` inmutable antes de lanzar
  el pool de workers.
- **Verificación de identidad y clasificación basadas en reglas
  explicables**, no en un modelo de caja negra: más fácil de sustentar
  y de justificar ante el profesor por qué un documento terminó en tal
  estado.
