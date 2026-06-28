# =============================================================================
# main.py — Punto de entrada del Sistema Conciliación Rimac
# Versión: 4.0 — Arquitectura modular por capas
#
# Este archivo SOLO hace 3 cosas:
#   1. Crea la instancia de FastAPI
#   2. Registra los routers (conciliacion + logs)
#   3. Define el evento de startup (carga DB y Excel)
#
# Toda la lógica de negocio vive en app/services/
# Toda la lógica de datos vive en app/database/
# Todos los endpoints viven en app/routers/
# =============================================================================

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.database.connection import inicializar_db, tomar_snapshot
from app.services.conciliacion_service import cargar_base, estado
from app.routers import conciliacion, logs


# =============================================================================
# LIFESPAN — reemplaza el deprecado @app.on_event("startup")
# Se ejecuta UNA vez al arrancar el servidor.
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "="*50)
    print("  SISTEMA CONCILIACION RIMAC v4.0")
    print("="*50)
    inicializar_db()          # crea tablas SQLite si no existen
    cargar_base()             # carga Excel en RAM
    tomar_snapshot(estado["df"])  # foto del estado inicial del día
    yield
    print("\n Servidor detenido")


# =============================================================================
# APP
# =============================================================================
app = FastAPI(
    title="Sistema Conciliacion Rimac",
    version="4.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="static"), name="static")

# =============================================================================
# ROUTERS
# conciliacion.router -> /api/buscar, /api/guardar, /api/importar, /api/recargar
# logs.router         -> /api/log, /api/log/resumen, /api/log/historial, /api/dashboard
# =============================================================================
app.include_router(conciliacion.router)
app.include_router(logs.router)


@app.get("/", response_class=HTMLResponse)
def index():
    with open("templates/index.html", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
