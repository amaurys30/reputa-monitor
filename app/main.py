import logging

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import Base, engine, get_db
from app.models import models  # noqa: F401 - registra los modelos en Base
from app.models.models import Persona, Fuente, Busqueda, Documento, TipoFuente
from app.api import personas, fuentes, busquedas, documentos

logging.basicConfig(level=logging.INFO,
                     format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Reputa Monitor - Sistemas Distribuidos CECAR")

app.include_router(personas.router)
app.include_router(fuentes.router)
app.include_router(busquedas.router)
app.include_router(documentos.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def crear_tablas():
    Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------
# Interfaz web (server-rendered) para RF1, RF2, RF9 y lanzar búsquedas.
# La lógica de negocio real vive en app/api/*; estas rutas solo arman
# la vista HTML para que el usuario no dependa de curl/Postman.
# ---------------------------------------------------------------------

@app.get("/")
def home(request: Request, q: str = "", estado: str = "", db: Session = Depends(get_db)):
    personas_lista = db.query(Persona).order_by(Persona.id.desc()).all()

    # RF9: permitir localizar una búsqueda específica ya realizada, no
    # solo ver "las últimas 10". Se filtra por nombre de la persona
    # consultada, país, o el propio ID de la búsqueda.
    query_busquedas = db.query(Busqueda).join(Persona)
    if q:
        patron = f"%{q}%"
        filtros_texto = [Persona.nombre_completo.ilike(patron), Busqueda.pais.ilike(patron)]
        if q.isdigit():
            filtros_texto.append(Busqueda.id == int(q))
        from sqlalchemy import or_
        query_busquedas = query_busquedas.filter(or_(*filtros_texto))
    if estado:
        query_busquedas = query_busquedas.filter(Busqueda.estado == estado)

    limite = 50 if (q or estado) else 10
    busquedas_lista = query_busquedas.order_by(Busqueda.id.desc()).limit(limite).all()

    return templates.TemplateResponse("home.html", {
        "request": request, "personas": personas_lista, "busquedas": busquedas_lista,
        "filtro_q": q, "filtro_estado": estado,
    })


@app.get("/personas/nueva")
def form_nueva_persona(request: Request):
    return templates.TemplateResponse("persona_form.html", {"request": request})


@app.post("/personas/nueva")
def crear_persona_form(
    request: Request,
    nombre_completo: str = Form(...), pais: str = Form(...),
    ciudad: str = Form(""), profesion_cargo: str = Form(""),
    empresa_organizacion: str = Form(""), alias: str = Form(""),
    palabras_relacionadas: str = Form(""),
    db: Session = Depends(get_db),
):
    persona = Persona(
        nombre_completo=nombre_completo, pais=pais, ciudad=ciudad or None,
        profesion_cargo=profesion_cargo or None,
        empresa_organizacion=empresa_organizacion or None,
        alias=alias or None, palabras_relacionadas=palabras_relacionadas or None,
    )
    db.add(persona)
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/personas/{persona_id}/eliminar")
def eliminar_persona(persona_id: int, db: Session = Depends(get_db)):
    """
    Elimina una persona y, en cascada, todas sus búsquedas, URLs,
    documentos y métricas asociadas (ver cascade="all, delete-orphan"
    en las relaciones del modelo). Se usa cuando ya no se necesitan los
    datos de prueba de esa persona.
    """
    persona = db.get(Persona, persona_id)
    if persona:
        db.delete(persona)
        db.commit()
    return RedirectResponse("/", status_code=303)


@app.get("/fuentes")
def ver_fuentes(request: Request, db: Session = Depends(get_db), error: str = ""):
    fuentes_lista = db.query(Fuente).order_by(Fuente.id.desc()).all()
    return templates.TemplateResponse("fuentes.html", {
        "request": request, "fuentes": fuentes_lista, "tipos": [t.value for t in TipoFuente],
        "error": error,
    })


@app.post("/fuentes/nueva")
def crear_fuente_form(
    nombre: str = Form(...), url_inicial: str = Form(...),
    tipo: str = Form("OTRO"), pais_manual: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.crawler.fetcher import descargar_pagina
    from app.crawler.country_detector import detectar_pais_desde_contenido

    # RF2: el país se determina a partir del CONTENIDO de la URL semilla
    # (lang del HTML, og:locale, ccTLD, léxico), nunca de la ubicación
    # física del servidor. pais_manual solo se usa como respaldo si la
    # detección automática no logra suficiente confianza.
    pagina = descargar_pagina(url_inicial)
    if not pagina.ok:
        if pais_manual:
            pais, automatico, confianza = pais_manual, False, 0.0
            evidencia = f"No se pudo descargar la URL ({pagina.error}); país asignado manualmente"
        else:
            return RedirectResponse(
                f"/fuentes?error=No se pudo acceder a la URL para detectar el país "
                f"({pagina.error}). Vuelve a intentar e ingresa el país manualmente.",
                status_code=303,
            )
    else:
        resultado = detectar_pais_desde_contenido(
            url_inicial, pagina.titulo, pagina.texto,
            idioma_html=pagina.idioma_html, og_locale=pagina.og_locale,
        )
        if resultado.automatico:
            pais, automatico, confianza, evidencia = (
                resultado.pais, True, resultado.confianza, resultado.evidencia
            )
        elif pais_manual:
            pais, automatico, confianza = pais_manual, False, resultado.confianza
            evidencia = f"Detección automática inconclusa ({resultado.evidencia}); asignado manualmente"
        else:
            return RedirectResponse(
                f"/fuentes?error=No se pudo determinar el país automáticamente "
                f"({resultado.evidencia}). Vuelve a intentar e ingresa el país manualmente.",
                status_code=303,
            )

    fuente = Fuente(nombre=nombre, url_inicial=url_inicial, pais=pais,
                     tipo=TipoFuente(tipo), activa=True,
                     pais_detectado_automaticamente=automatico,
                     confianza_deteccion_pais=confianza,
                     evidencia_deteccion_pais=evidencia)
    db.add(fuente)
    db.commit()
    return RedirectResponse("/fuentes", status_code=303)


@app.post("/fuentes/{fuente_id}/toggle")
def alternar_fuente(fuente_id: int, db: Session = Depends(get_db)):
    fuente = db.get(Fuente, fuente_id)
    if fuente:
        fuente.activa = not fuente.activa
        db.commit()
    return RedirectResponse("/fuentes", status_code=303)


@app.post("/fuentes/{fuente_id}/corregir-pais")
def corregir_pais_fuente(fuente_id: int, pais_correcto: str = Form(...),
                          db: Session = Depends(get_db)):
    """
    Corrección manual del país de una fuente YA registrada, para cuando
    la detección automática se equivocó (ej. un sitio con dominio .co
    pero con idioma/locale mal configurado como "es-ES"). Queda
    registrado como corrección manual, no como detección automática.
    """
    fuente = db.get(Fuente, fuente_id)
    if fuente:
        fuente.pais = pais_correcto.strip()
        fuente.pais_detectado_automaticamente = False
        fuente.evidencia_deteccion_pais = "Corregido manualmente por el administrador"
        db.commit()
    return RedirectResponse("/fuentes", status_code=303)


@app.get("/busquedas/nueva")
def form_nueva_busqueda(request: Request, db: Session = Depends(get_db)):
    personas_lista = db.query(Persona).all()
    return templates.TemplateResponse("busqueda_form.html", {
        "request": request, "personas": personas_lista,
    })


@app.post("/busquedas/nueva")
def crear_busqueda_form(
    persona_id: int = Form(...), pais: str = Form(...),
    max_workers: int = Form(5), max_urls: int = Form(60),
    sin_limite: str | None = Form(None),
):
    import threading
    from app.db.database import SessionLocal
    from app.crawler.crawler_manager import ejecutar_busqueda

    # Si el usuario marcó "sin límite", ignoramos el número del input y
    # pasamos None: ColaURLsCompartida ya soporta max_urls=None como
    # "no hay tope, terminar solo cuando no queden URLs pendientes"
    # (segunda condición de parada de RF3).
    limite_final = None if sin_limite else max_urls

    db = SessionLocal()
    # max_profundidad no es un parámetro que pida ningún RF, así que no
    # se le pregunta al usuario -- se calcula automáticamente según qué
    # tan grande es el límite de URLs pedido (ver crawler_manager.py).
    from app.crawler.crawler_manager import calcular_profundidad_automatica
    profundidad_auto = calcular_profundidad_automatica(limite_final)
    busqueda = Busqueda(persona_id=persona_id, pais=pais, max_workers=max_workers,
                         max_urls=limite_final, max_profundidad=profundidad_auto,
                         estado="PENDIENTE")
    db.add(busqueda)
    db.commit()
    db.refresh(busqueda)
    busqueda_id = busqueda.id
    db.close()

    threading.Thread(target=ejecutar_busqueda, args=(busqueda_id,), daemon=True).start()
    return RedirectResponse(f"/busquedas/{busqueda_id}", status_code=303)


# ---------------------------------------------------------------------
# Benchmark de concurrencia (1 vs. N workers) integrado a la web, para
# poder correrlo y mostrarlo en la sustentación sin salir a la terminal.
# Rúbrica: "Compara 1 vs. múltiples workers bajo condiciones equivalentes,
# registra métricas y analiza los resultados."
# ---------------------------------------------------------------------

def _correr_benchmark_secuencial(busqueda_ids: list[int]):
    """
    Corre cada búsqueda del grupo UNA DESPUÉS DE OTRA (nunca en paralelo
    entre sí) en un único hilo de fondo. Esto es intencional: si dos
    corridas del benchmark se ejecutaran al mismo tiempo, competirían
    por la misma red/CPU y dejarían de ser "condiciones equivalentes"
    -- justo lo que exige este ítem de la rúbrica.
    """
    from app.db.database import SessionLocal
    from app.crawler.crawler_manager import ejecutar_busqueda
    for bid in busqueda_ids:
        try:
            ejecutar_busqueda(bid)
        except Exception:
            logging.exception("Fallo la corrida de benchmark busqueda_id=%s", bid)
            db = SessionLocal()
            try:
                b = db.get(Busqueda, bid)
                if b:
                    b.estado = "ERROR"
                    db.commit()
            finally:
                db.close()


@app.get("/benchmark")
def form_benchmark(request: Request, db: Session = Depends(get_db)):
    personas_lista = db.query(Persona).all()
    return templates.TemplateResponse("benchmark_form.html", {
        "request": request, "personas": personas_lista,
    })


@app.post("/benchmark/nuevo")
def crear_benchmark(
    persona_id: int = Form(...), pais: str = Form(...),
    lista_workers: str = Form("1,2,4,8"), max_urls: int = Form(60),
):
    import threading
    import uuid
    from app.db.database import SessionLocal
    from app.crawler.crawler_manager import calcular_profundidad_automatica

    # Parseo defensivo: acepta "1,2,4,8" o "1, 2, 4, 8", ignora vacíos,
    # quita duplicados, y siempre queda ordenado de menor a mayor para
    # que la comparación se lea de forma natural.
    valores = sorted({
        int(v.strip()) for v in lista_workers.split(",")
        if v.strip().isdigit() and int(v.strip()) > 0
    })
    if not valores:
        valores = [1, 2, 4, 8]

    grupo = uuid.uuid4().hex[:10]
    profundidad = calcular_profundidad_automatica(max_urls)

    db = SessionLocal()
    ids_en_orden = []
    for n_workers in valores:
        b = Busqueda(persona_id=persona_id, pais=pais, max_workers=n_workers,
                      max_urls=max_urls, max_profundidad=profundidad,
                      grupo_benchmark=grupo, estado="PENDIENTE")
        db.add(b)
        db.commit()
        db.refresh(b)
        ids_en_orden.append(b.id)
    db.close()

    threading.Thread(target=_correr_benchmark_secuencial, args=(ids_en_orden,),
                      daemon=True).start()
    return RedirectResponse(f"/benchmark/{grupo}", status_code=303)


@app.get("/benchmark/{grupo}")
def ver_benchmark(request: Request, grupo: str, db: Session = Depends(get_db)):
    from app.models.models import MetricaEjecucion
    from app.crawler.benchmark_analysis import PuntoBenchmark, analizar_resultados

    busquedas_grupo = (
        db.query(Busqueda)
        .filter(Busqueda.grupo_benchmark == grupo)
        .order_by(Busqueda.max_workers)
        .all()
    )

    filas = []
    puntos_para_analisis = []
    for b in busquedas_grupo:
        metrica_total = (
            db.query(MetricaEjecucion)
            .filter_by(busqueda_id=b.id, etapa="CRAWLING_COMPLETO")
            .first()
        )
        tiempo = metrica_total.tiempo_total_segundos if metrica_total else None
        urls_procesadas = metrica_total.num_urls_procesadas if metrica_total else None
        filas.append({
            "workers": b.max_workers, "estado": b.estado,
            "tiempo": tiempo, "urls_procesadas": urls_procesadas,
            "conflictos": b.conflictos_evitados,
        })
        if b.estado == "FINALIZADA" and tiempo is not None:
            puntos_para_analisis.append(PuntoBenchmark(
                workers=b.max_workers, tiempo_segundos=tiempo,
                urls_procesadas=urls_procesadas or 0,
                conflictos_evitados=b.conflictos_evitados or 0,
            ))

    todas_finalizadas = bool(busquedas_grupo) and all(
        b.estado in ("FINALIZADA", "ERROR") for b in busquedas_grupo
    )
    analisis = analizar_resultados(puntos_para_analisis) if len(puntos_para_analisis) >= 2 else None

    tiempo_max = max((f["tiempo"] for f in filas if f["tiempo"]), default=1)

    persona_nombre = busquedas_grupo[0].persona.nombre_completo if busquedas_grupo else None

    return templates.TemplateResponse("benchmark_resultados.html", {
        "request": request, "grupo": grupo, "filas": filas,
        "todas_finalizadas": todas_finalizadas, "analisis": analisis,
        "tiempo_max": tiempo_max, "persona_nombre": persona_nombre,
    })


@app.get("/busquedas/{busqueda_id}")
def ver_busqueda(
    request: Request, busqueda_id: int,
    clasificacion_contextual: str = "", estado_verificacion: str = "",
    fuente_id: str = "", fecha_desde: str = "", fecha_hasta: str = "",
    db: Session = Depends(get_db),
):
    """RF9: filtros por clasificación, fuente, fecha y estado de verificación."""
    busqueda = db.get(Busqueda, busqueda_id)
    q = db.query(Documento).filter(Documento.busqueda_id == busqueda_id)
    if clasificacion_contextual:
        q = q.filter(Documento.clasificacion_contextual == clasificacion_contextual)
    if estado_verificacion:
        q = q.filter(Documento.estado_verificacion == estado_verificacion)
    if fuente_id:
        q = q.filter(Documento.fuente_id == int(fuente_id))
    if fecha_desde:
        q = q.filter(Documento.fecha_consulta >= fecha_desde)
    if fecha_hasta:
        q = q.filter(Documento.fecha_consulta <= fecha_hasta)
    documentos = q.order_by(Documento.fecha_consulta.desc()).all()

    from app.models.models import UrlRegistro, EstadoURL, MetricaEjecucion
    descartados = db.query(UrlRegistro).filter(
        UrlRegistro.busqueda_id == busqueda_id,
        UrlRegistro.estado.in_([EstadoURL.DESCARTADA, EstadoURL.ERROR]),
    ).all()
    metricas = db.query(MetricaEjecucion).filter_by(busqueda_id=busqueda_id).all()
    fuentes_pais = (
        db.query(Fuente)
        .filter(func.lower(func.trim(Fuente.pais)) == busqueda.pais.strip().lower())
        .all()
        if busqueda else []
    )

    # RF4: conteo de URLs por estado -- evidencia visible de que los 5
    # estados (PENDIENTE, EN_PROCESAMIENTO, PROCESADA, DESCARTADA, ERROR)
    # se controlan de verdad, no solo "existen" en el modelo de datos.
    conteos_query = (
        db.query(UrlRegistro.estado, func.count(UrlRegistro.id))
        .filter(UrlRegistro.busqueda_id == busqueda_id)
        .group_by(UrlRegistro.estado)
        .all()
    )
    conteos_por_estado = {estado.value: 0 for estado in EstadoURL}
    for estado, cantidad in conteos_query:
        conteos_por_estado[estado.value] = cantidad

    return templates.TemplateResponse("resultados.html", {
        "request": request, "busqueda": busqueda, "documentos": documentos,
        "descartados": descartados, "metricas": metricas, "fuentes_pais": fuentes_pais,
        "conteos_por_estado": conteos_por_estado,
        "filtro_clasificacion": clasificacion_contextual,
        "filtro_verificacion": estado_verificacion,
        "filtro_fuente_id": fuente_id,
        "filtro_fecha_desde": fecha_desde,
        "filtro_fecha_hasta": fecha_hasta,
    })
