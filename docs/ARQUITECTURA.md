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
