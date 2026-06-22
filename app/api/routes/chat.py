"""
Ruta HTTP para el endpoint de Chat (RAG completo).

Este endpoint ejecuta el flujo completo de RAG:
    Pregunta → Embedding → Búsqueda Semántica → Contexto → LangChain Chain → Respuesta

Mantiene la separación explícita entre retrieval y generation:
    - search_chunks: recupera Documents desde PostgreSQL (FastAPI DI con AsyncSession)
    - generate_answer: LCEL Chain que procesa los Documents y llama a Gemini

¿Por qué separamos retrieval de la chain?
------------------------------------------
LangChain tiene su propio sistema de Retrievers, pero integrarlo con
la AsyncSession de FastAPI requiere un BaseRetriever custom que mezcla
las responsabilidades. Mantenerlos separados es más limpio y explícito.
"""

import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.schemas.query import QueryRequest
from app.services.search_service import search_chunks
from app.services.llm_service import generate_answer_stream

router = APIRouter(tags=["Chat"])


@router.post("/")
async def chat(
    request: QueryRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    **Endpoint de Chat con RAG (Streaming SSE)**

    Recibe una pregunta en lenguaje natural y devuelve un stream de texto
    (Server-Sent Events) generado por Gemini vía LangChain, basado en los
    documentos almacenados.

    Nota: Al ser un stream, Swagger UI no lo puede visualizar en tiempo real.
    Prueba desde la terminal con:
    curl -N -X POST http://127.0.0.1:8000/chat/ -H "Content-Type: application/json" -d "{\"query\": \"...\"}"
    """
    # --- Paso 1: Retrieval ---
    docs = await search_chunks(session, request.query, request.limit)

    # --- Paso 2: Generador de Texto Crudo ---
    async def event_generator():
        # Iteramos sobre el generador asíncrono de LangChain
        async for chunk in generate_answer_stream(request.query, docs):
            # Enviamos el texto puro sin formato SSE para que curl lo muestre limpio
            yield chunk

    # --- Paso 3: Respuesta ---
    # Devolvemos un stream de texto plano
    return StreamingResponse(event_generator(), media_type="text/plain")
