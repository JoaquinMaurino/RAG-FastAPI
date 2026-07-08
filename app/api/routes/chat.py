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
from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.schemas.query import QueryRequest, SearchFilters
from app.services.search_service import search_chunks
from app.services.llm_service import generate_answer_stream
from app.services.query_rewriter import rewrite_query
from app.services.multi_query import multi_query_search
from app.memory.conversation_manager import ConversationManager
from app.core.config import settings

router = APIRouter(tags=["Chat"])

# Instanciamos el manager a nivel router (es thread-safe y sin estado mutable por request)
memory_manager = ConversationManager()

@router.post("/")
async def chat(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    **Endpoint de Chat con RAG y Memoria (Streaming)**
    """
    # --- Paso 1: Memoria - Preparar el turno ---
    conv_id, chat_history = await memory_manager.prepare_turn(
        session=session,
        conversation_id=request.conversation_id,
        question=request.query,
    )

    # --- Paso 2: Query Rewriting ---
    # Reformulamos la query antes del retrieval para mejorar la calidad del embedding.
    # Si el rewriter falla internamente, rewrite_query devuelve la query original.
    search_query = await rewrite_query(request.query, chat_history)

    # --- Paso 3: Retrieval ---
    filters = SearchFilters(document_id=request.document_id) if request.document_id else None

    # MULTI_QUERY_ENABLED=true: genera N variantes y busca en paralelo (mayor recall).
    # MULTI_QUERY_ENABLED=false: búsqueda simple con la query reescrita (Fase 2.1).
    if settings.multi_query_enabled:
        docs = await multi_query_search(session, search_query, limit=request.limit, chat_history=None, filters=filters)
    else:
        docs = await search_chunks(session, search_query, limit=request.limit, filters=filters)

    # --- Paso 4: Generador de Texto Crudo y Guardado de Memoria ---
    async def event_generator():
        full_response = []
        # Iteramos sobre el generador asíncrono de LangChain pasándole el history
        async for chunk in generate_answer_stream(request.query, docs, chat_history):
            full_response.append(chunk)
            # Enviamos el texto puro
            yield chunk
            
        # Una vez que termina el stream, guardamos la respuesta del asistente en memoria.
        # Al estar dentro del generador, la sesión de DB sigue abierta.
        await memory_manager.save_assistant_response(
            session=session,
            conversation_id=conv_id,
            response="".join(full_response),
        )

    # --- Paso 4: Respuesta ---
    # Registramos las tareas de post-procesamiento (ej. actualizar el resumen)
    # Estas correrán DESPUÉS de que se cierre el stream HTTP.
    background_tasks.add_task(memory_manager.post_turn_tasks, conv_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={"X-Conversation-Id": str(conv_id)},
        background=background_tasks
    )
