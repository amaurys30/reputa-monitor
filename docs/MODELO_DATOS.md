# Modelo de Datos — Reputa Monitor

## Diagrama entidad-relación

```mermaid
erDiagram
    PERSONA ||--o{ BUSQUEDA : "es consultada en"
    BUSQUEDA ||--o{ URL_REGISTRO : "descubre"
    BUSQUEDA ||--o{ DOCUMENTO : "produce"
    BUSQUEDA ||--o{ METRICA_EJECUCION : "mide"
    FUENTE ||--o{ URL_REGISTRO : "origina"
    PERSONA ||--o{ DOCUMENTO : "es mencionada en"

    PERSONA {
        int id PK
        string nombre_completo "obligatorio (RF1)"
        string pais "obligatorio (RF1)"
        string ciudad
        string profesion_cargo
        string empresa_organizacion
        string alias
        string palabras_relacionadas
        datetime creado_en
    }

    FUENTE {
        int id PK
        string nombre
        string url_inicial
        string pais "detectado del contenido, no del servidor (RF2)"
        enum tipo "NOTICIAS/RED_SOCIAL/BLOG/DIRECTORIO/OTRO"
        bool activa
        bool pais_detectado_automaticamente
        float confianza_deteccion_pais
        string evidencia_deteccion_pais
    }

    BUSQUEDA {
        int id PK
        int persona_id FK
        string pais
        int max_workers "RF3 - configurable"
        int max_urls "NULL = sin limite"
        int max_profundidad "calculado automaticamente segun max_urls"
        string estado "PENDIENTE/EN_CURSO/FINALIZADA/ERROR"
        string grupo_benchmark "agrupa corridas 1-vs-N workers"
        int conflictos_evitados "evidencia RF4"
        datetime iniciado_en
        datetime finalizado_en
    }

    URL_REGISTRO {
        int id PK
        int busqueda_id FK
        string url
        int fuente_id FK
        enum estado "PENDIENTE/EN_PROCESAMIENTO/PROCESADA/DESCARTADA/ERROR (RF4)"
        int profundidad
        string motivo_descarte "RF5"
        string worker_id "evidencia de concurrencia"
        int intentos
        datetime descubierta_en
        datetime procesada_en
    }

    DOCUMENTO {
        int id PK
        int busqueda_id FK
        int persona_id FK
        int fuente_id FK
        string titulo
        string url "UNIQUE junto con busqueda_id (RF6, evita duplicados)"
        string pais
        datetime fecha_publicacion
        datetime fecha_consulta
        text contenido_texto
        string coincidencias_encontradas "RF5"
        float score_identidad "RF7"
        enum estado_verificacion "MISMA_PERSONA/POSIBLE_COINCIDENCIA/PERSONA_DIFERENTE/NO_DETERMINADO"
        enum clasificacion_contextual "POSITIVO/NEUTRO/NEGATIVO/NO_DETERMINADO (RF8)"
        string justificacion_clasificacion
    }

    METRICA_EJECUCION {
        int id PK
        int busqueda_id FK
        string etapa
        string modo "SECUENCIAL/THREADS/PROCESOS"
        int num_workers
        int num_urls_procesadas
        float tiempo_total_segundos
        datetime registrado_en
    }
```

## Decisiones de diseño relevantes

- **`UrlRegistro.estado`** es el recurso compartido crítico del taller
  (RF4). Su transición está protegida por un `threading.Lock` en
  `app/crawler/state_manager.py`, no solo por la base de datos.
- **`UniqueConstraint(busqueda_id, url)`** en `UrlRegistro` y en
  `Documento` es una segunda barrera (defensa en profundidad) contra
  duplicados, complementaria al lock en memoria — si dos procesos
  distintos (no solo threads) llegaran a coexistir, la BD seguiría
  garantizando unicidad. Las URLs se normalizan antes de compararse
  (`app/crawler/url_utils.py`), para que variaciones superficiales
  (barra final, parámetros de rastreo `utm_*`) no cuenten como
  distintas.
- **`worker_id`** en `UrlRegistro` guarda qué hilo procesó cada URL:
  es la evidencia que se muestra en la sustentación para demostrar que
  el trabajo se distribuyó entre varios workers reales.
- **`MetricaEjecucion`** existe para soportar el ítem de la rúbrica
  "Medición de concurrencia": no solo guarda el tiempo total del
  crawling, sino una fila POR ETAPA (`RF3_descarga_html`,
  `RF4_control_estado_url`, `RF5_matching_contenido`,
  `RF7_verificacion_identidad`, `RF8_clasificacion_contextual`),
  registrada por un acumulador thread-safe
  (`app/crawler/metrics_accumulator.py`).
- **`Fuente.pais_detectado_automaticamente` / `confianza_deteccion_pais`
  / `evidencia_deteccion_pais`**: el país de una fuente se determina
  analizando el CONTENIDO de la URL semilla (idioma del HTML,
  `og:locale`, dominio institucional, léxico) — nunca la ubicación del
  servidor. Ver `app/crawler/country_detector.py`. Si la detección
  automática no logra suficiente confianza, el administrador puede
  corregirlo manualmente, y esa corrección queda registrada aquí.
- **`Busqueda.grupo_benchmark` / `conflictos_evitados`**: soportan la
  funcionalidad de benchmark 1-vs-N-workers integrada a la aplicación
  web (`/benchmark`), que agrupa varias corridas de la misma búsqueda
  con distinto número de workers para compararlas bajo condiciones
  equivalentes.
- Los borrados están configurados en **cascada** a nivel de ORM
  (`cascade="all, delete-orphan"`): eliminar una `Persona` elimina
  también sus búsquedas, URLs, documentos y métricas asociadas.
