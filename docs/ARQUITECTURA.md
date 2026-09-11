# Diagrama de Arquitectura de Software — Reputa Monitor


```mermaid
flowchart TB
    U[Usuario<br/>Navegador Web]
    APP[Aplicación Web<br/>FastAPI + Jinja2<br/>Rutas HTML, API REST y Benchmark]

    subgraph MOTOR["Motor de Crawling Concurrente (RF3 / RF4)"]
        direction TB
        MGR[Crawler Manager<br/>arma el pool de N workers configurable]
        COLA[Cola Compartida<br/>queue.Queue - productor/consumidor]
        WORKERS[Workers 1..N<br/>threads corriendo en paralelo]
        LOCK[URL State Manager<br/>Lock - evita procesar la misma URL 2 veces]
        MGR --> COLA --> WORKERS --> LOCK
    end

    subgraph PIPE["Pipeline de Análisis por Documento (RF5 / RF7 / RF8)"]
        direction TB
        P1[1. Descargar y extraer contenido]
        P2[2. Verificar si está relacionado con la persona]
        P3[3. Verificar identidad]
        P4[4. Clasificar el contexto]
        P1 --> P2 --> P3 --> P4
    end

    DB[(PostgreSQL<br/>Persistencia - RF6)]

    U --> APP
    APP -->|inicia búsqueda| MOTOR
    WORKERS -->|cada worker ejecuta| PIPE
    PIPE -->|guarda documento| DB
    LOCK -->|guarda estado de URL| DB
    APP -->|consulta y filtra - RF9| DB
```

**Cómo funciona**: el usuario inicia una búsqueda desde
la web. El *Crawler Manager* arma un pool de N workers (threads) que
comparten una cola de URLs pendientes. Cada worker, antes de procesar
una URL, pasa por el *URL State Manager*, que usa un `Lock` para
garantizar que ninguna URL sea tomada por dos workers a la vez (RF4).
Una vez que un worker "gana" una URL, corre el pipeline de análisis
(descarga → matching → verificación de identidad → clasificación) de
forma totalmente independiente de los demás workers, y al final
persiste el resultado en PostgreSQL.

---

## Vista detallada (referencia, incluye todos los módulos)

```mermaid
flowchart TB
    subgraph Cliente
        U[Usuario - Navegador Web]
    end

    subgraph "Capa de Presentacion (FastAPI + Jinja2)"
        WEB[Rutas Web / HTML<br/>app/main.py + templates/]
        API[API REST JSON<br/>app/api/*]
        BENCH_UI[Benchmark Web<br/>/benchmark - compara 1 vs N workers]
    end

    subgraph "Capa de Administracion de Fuentes (RF2)"
        DETECT[Country Detector<br/>app/crawler/country_detector.py<br/>lang/og:locale, ccTLD institucional, lexico]
    end

    subgraph "Capa de Orquestacion de Concurrencia (RF3/RF4)"
        MGR2[Crawler Manager<br/>app/crawler/crawler_manager.py]
        SM[URL State Manager<br/>Lock sobre estados - RF4]
        Q["Cola Compartida (queue.Queue)<br/>reserva atomica de cupo - RF3"]
        METR[Acumulador de Tiempos<br/>app/crawler/metrics_accumulator.py<br/>Lock por etapa]
        W1[Worker Thread 1]
        W2[Worker Thread 2]
        WN[Worker Thread N]
    end

    subgraph "Capa de Procesamiento por Documento"
        FETCH[Fetcher<br/>descarga HTTP + parseo HTML + metadatos]
        URLUTIL[URL Normalizer<br/>app/crawler/url_utils.py]
        MATCH[Matcher<br/>RF5 contenido relacionado]
        NOMVAR[Generador de Variantes de Nombre<br/>app/crawler/nombre_utils.py]
        IDENT[Identity Verifier<br/>RF7 verificacion identidad]
        CLASS[Classifier<br/>RF8 clasificacion contextual por ventana]
    end

    subgraph "Capa de Analisis de Concurrencia"
        BENCHAN[Benchmark Analysis<br/>app/crawler/benchmark_analysis.py<br/>genera analisis automatico speedup/meseta]
    end

    subgraph "Capa de Persistencia"
        DB2[(PostgreSQL<br/>Pool de conexiones)]
    end

    U -->|HTTP| WEB
    U -->|HTTP/JSON| API
    U -->|HTTP| BENCH_UI
    WEB --> MGR2
    API --> MGR2
    BENCH_UI -->|N corridas secuenciales| MGR2
    BENCH_UI --> BENCHAN

    WEB --> DETECT
    API --> DETECT
    DETECT --> DB2

    MGR2 --> SM
    MGR2 --> Q
    MGR2 --> METR
    Q --> W1 & W2 & WN
    W1 & W2 & WN --> SM
    W1 & W2 & WN --> FETCH
    FETCH --> URLUTIL
    FETCH --> MATCH
    NOMVAR --> MATCH
    NOMVAR --> IDENT
    MATCH --> IDENT
    IDENT --> CLASS
    W1 & W2 & WN -.mide tiempo por etapa.-> METR
    CLASS -->|Documento clasificado| DB2
    SM -->|estados de URL| DB2
    METR -->|metricas por etapa| DB2
    WEB --> DB2
    API --> DB2
```

## Patrón de concurrencia usado

- **Productor-consumidor** con `queue.Queue` (thread-safe nativamente).
- **Terminación dinámica** vía `queue.join()` + sentinelas, porque el
  número total de URLs a procesar no se conoce de antemano (los propios
  workers descubren nuevas URLs).
- **Sección crítica mínima**: el `Lock` del `URLStateManager` solo
  protege la transición de estado (una operación de BD muy corta); la
  descarga HTTP (lo lento) ocurre siempre fuera del lock.
- **Reserva atómica de cupo**: antes de registrar una URL descubierta,
  se reserva su lugar en el límite de exploración con un `Lock`
  dedicado (`ColaURLsCompartida.intentar_reservar_slot`), evitando que
  se creen registros que nunca serán procesados.
- **Acumulación thread-safe de métricas**: cada worker reporta el
  tiempo de sus sub-etapas (descarga, matching, verificación,
  clasificación) a un acumulador protegido por `Lock`, sin serializar
  el trabajo real.
