"""
Router principal de la API.

Acá se ensamblan todos los routers de la aplicación.
Cuando main.py necesita registrar rutas, importa este
único api_router en vez de cada router individualmente.

Para agregar un nuevo recurso:
    from app.api.routes.chat import router as chat_router
    api_router.include_router(chat_router, prefix="/chat")
"""

from fastapi import APIRouter

from app.api.routes.documents import router as documents_router
from app.api.routes.search import router as search_router
from app.api.routes.chat import router as chat_router

api_router = APIRouter()

api_router.include_router(documents_router, prefix="/documents")
api_router.include_router(search_router, prefix="/search")
api_router.include_router(chat_router, prefix="/chat")
