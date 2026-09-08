# Diagrama de Infraestructura — Reputa Monitor

```mermaid
flowchart LR
    subgraph Host["Máquina host (Docker Engine)"]
        subgraph net["Red Docker: reputa-monitor_default"]
            subgraph api_container["Contenedor: reputa_api"]
                UV[Uvicorn + FastAPI<br/>Puerto interno 8000]
                THREADS["Pool de N threads<br/>(configurable por búsqueda)"]
                UV --- THREADS
            end

            subgraph db_container["Contenedor: reputa_db"]
                PG[(PostgreSQL 16<br/>Puerto interno 5432)]
                VOL[(Volumen: reputa_pgdata)]
                PG --- VOL
            end

            api_container -->|SQL vía pool de conexiones| db_container
        end
    end

    NAV[Navegador del usuario] -->|http://localhost:8000| api_container
    api_container -->|HTTP saliente concurrente| INTERNET((Internet<br/>Fuentes publicas: RF2))
```

## Componentes desplegados

| Contenedor | Imagen base | Rol | Puertos expuestos |
|---|---|---|---|
| `reputa_api` | `python:3.12-slim` | API + UI web + orquestador del crawler concurrente | `8000:8000` |
| `reputa_db` | `postgres:16-alpine` | Persistencia relacional | `5432:5432` |


  perder resultados entre sesiones de pruebas/sustentación.
- Ambos contenedores se comunican por la **red interna de Docker
  Compose** (`reputa-monitor_default`), resuelta por nombre de servicio
  (`db`), no por IP fija.
