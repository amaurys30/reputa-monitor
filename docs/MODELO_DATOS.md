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


  equivalentes.
- Los borrados están configurados en **cascada** a nivel de ORM
  (`cascade="all, delete-orphan"`): eliminar una `Persona` elimina
  también sus búsquedas, URLs, documentos y métricas asociadas.
