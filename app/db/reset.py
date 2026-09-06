"""
Utilidad para vaciar todas las tablas y empezar con datos limpios sin
tener que recrear el contenedor de Postgres ni perder el esquema.

Uso:
    docker compose exec api python -m app.db.reset

Pide confirmación antes de borrar, para evitar un "oops" accidental.
"""
from sqlalchemy import text

from app.db.database import SessionLocal, engine

TABLAS_EN_ORDEN = [
    "documentos", "urls", "metricas_ejecucion", "busquedas", "fuentes", "personas",
]


def main():
    respuesta = input(
        "Esto BORRARÁ todos los datos (personas, fuentes, búsquedas, documentos). "
        "¿Continuar? [s/N]: "
    ).strip().lower()
    if respuesta != "s":
        print("Cancelado. No se borró nada.")
        return

    db = SessionLocal()
    try:
        tablas = ", ".join(TABLAS_EN_ORDEN)
        db.execute(text(f"TRUNCATE TABLE {tablas} RESTART IDENTITY CASCADE"))
        db.commit()
        print(f"Listo. Tablas vaciadas: {tablas}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
