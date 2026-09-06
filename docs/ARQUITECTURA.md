# Diagrama de Arquitectura de Software — Reputa Monitor

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
        MGR[Crawler Manager<br/>app/crawler/crawler_manager.py]
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
        DB[(PostgreSQL<br/>Pool de conexiones)]
    end

    U -->|HTTP| WEB
    U -->|HTTP/JSON| API
    U -->|HTTP| BENCH_UI
    WEB --> MGR
    API --> MGR
    BENCH_UI -->|N corridas secuenciales| MGR
    BENCH_UI --> BENCHAN

    WEB --> DETECT
    API --> DETECT
    DETECT --> DB

    MGR --> SM
    MGR --> Q
    MGR --> METR
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
    CLASS -->|Documento clasificado| DB
    SM -->|estados de URL| DB
    METR -->|metricas por etapa| DB
    WEB --> DB
    API --> DB
```

## Justificación de capas

1. **Presentación**: FastAPI expone vistas HTML (para uso humano y para
   la sustentación, incluyendo el benchmark visual en `/benchmark`),
   una API JSON (para pruebas automatizadas o integración), y comparten
   toda la lógica de negocio subyacente.
2. **Administración de fuentes (RF2)**: el país de una fuente se
   determina automáticamente analizando el contenido de su URL semilla
   (nunca la ubicación del servidor). El detector prioriza dominios
   institucionales (`.edu.co`, `.gov.co`) sobre el idioma declarado,
   porque este último suele ser un valor por defecto de plantilla poco
   confiable.
3. **Orquestación de concurrencia**: es el corazón del taller. El
   `Crawler Manager` arma el pool de N workers configurables (RF3),
   les entrega una cola compartida thread-safe con reserva atómica de
   cupo (evita URLs huérfanas más allá del límite de exploración), un
   gestor de estados con sincronización explícita (RF4), y un
   acumulador de tiempos por etapa para la medición de concurrencia.
4. **Procesamiento por documento**: pipeline puro (sin estado
   compartido) que cada worker ejecuta de forma aislada. Incluye
   normalización de URLs (evita duplicados por variaciones
   superficiales) y generación de variantes de nombre (reconoce
   menciones realistas como "Nombre Apellido", no solo el nombre legal
   completo).
5. **Análisis de concurrencia**: a partir de las métricas persistidas,
   genera automáticamente el análisis textual (speedup, detección de
   meseta) que exige la rúbrica, mostrado en vivo en `/benchmark`.
6. **Persistencia**: PostgreSQL con un pool de conexiones
   (`pool_size=20`) para soportar escrituras concurrentes desde
   múltiples workers sin agotar conexiones.

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
