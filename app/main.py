"""
Entry point de la aplicación FastAPI.

=====================================================================
¿QUÉ ES FASTAPI?
=====================================================================

FastAPI es un framework web para Python que:
1. Es ASYNC por defecto (puede manejar miles de requests simultáneos)
2. Genera documentación automática (Swagger UI en /docs)
3. Valida datos automáticamente con Pydantic
4. Tiene dependency injection integrado

Comparación con otros frameworks:
- Flask    → Síncrono, más simple, menos features
- Django   → Síncrono (async parcial), batteries-included, más pesado
- FastAPI  → Async nativo, moderno, validación automática ← Nuestro choice

=====================================================================
¿QUÉ ES UN LIFESPAN?
=====================================================================

El "lifespan" es código que se ejecuta:
- Al ARRANCAR la app (antes de recibir requests) → startup
- Al APAGAR la app (después del último request) → shutdown

Lo usamos para:
- Startup:  verificar que PostgreSQL está vivo
- Shutdown: cerrar las conexiones limpiamente

Sin esto, si PostgreSQL está caído, la app arrancaría "bien" pero
cada request fallaría. Mejor fallar rápido al inicio.
=====================================================================
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.logger import setup_logging
from app.database.session import engine
from app.database.models.base import Base
from app.api import api_router

# =====================================================================
# 1. CONFIGURACIÓN DEL LOGGER
# =====================================================================
# Interceptamos logs de uvicorn y ponemos el formato visual de loguru
setup_logging()

# =====================================================================
# 2. INICIALIZACIÓN DE LA APP
# =====================================================================

# =====================================================================
# LIFESPAN: Startup y Shutdown
# =====================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Maneja el ciclo de vida de la aplicación.
    
    Todo ANTES del yield → se ejecuta al ARRANCAR
    Todo DESPUÉS del yield → se ejecuta al APAGAR
    """
    # --- STARTUP ---
    print(f"Starting {settings.app_name}...")
    
    # Verificar conexión a PostgreSQL y crear tablas
    try:
        async with engine.begin() as conn:
            # Primero verificamos la conexión
            await conn.execute(text("SELECT 1"))
            print("Database connection successful")

            # Activamos la extensión pgvector ANTES de crear las tablas.
            # La tabla 'chunks' tiene una columna de tipo VECTOR(384).
            # Sin esta extensión, PostgreSQL no conoce ese tipo y create_all() falla.
            # IF NOT EXISTS: idempotente, no lanza error si ya estaba activa.
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            print("pgvector extension enabled")

            # Luego creamos las tablas si no existen
            await conn.run_sync(Base.metadata.create_all)
            print("Database tables verified/created successfully")

    except Exception as e:
        print(f"Database initialization failed: {e}")
        # No hacemos raise acá para que la app arranque igual.
        # El health endpoint mostrará el error.
        # En producción podrías hacer raise para que no arranque.
    
    yield  # ← La app está corriendo y recibiendo requests
    
    # --- SHUTDOWN ---
    print("Shutting down...")
    await engine.dispose()  # Cierra todas las conexiones del pool
    print("Database connections closed")


# =====================================================================
# CREAR LA APP
# =====================================================================
app = FastAPI(
    title=settings.app_name,
    # ↑ Aparece en la documentación automática (/docs)

    description="ChatBOT assistant powered by RAG",

    version="1.0.0",

    lifespan=lifespan,
    # ↑ Conecta nuestro ciclo de vida definido arriba
)

# =====================================================================
# ROUTERS
# =====================================================================
# Registramos el router central. Todos los subrouters
# (documents, chat, etc.) ya están ensamblados dentro de api_router.
app.include_router(api_router)


# =====================================================================
# HEALTH ENDPOINT
# =====================================================================
@app.get("/health")
async def health_check():
    """
    Endpoint de health check.
    
    Verifica que:
    1. La API está corriendo
    2. PostgreSQL está accesible
    
    Devuelve el estado de cada componente.
    
    ¿Para qué sirve un health check?
    - Docker lo usa para saber si el contenedor está sano
    - Load balancers lo usan para saber a dónde mandar tráfico
    - Monitoreo lo usa para alertar si algo se cayó
    """
    # Intentar conectar a la base de datos
    db_status = "connected"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            # ↑ La query más simple posible. Si funciona, PostgreSQL está vivo.
            #   text() le dice a SQLAlchemy "esto es SQL crudo, no lo parsees".
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "database": db_status,
        "app_name": settings.app_name,
    }
