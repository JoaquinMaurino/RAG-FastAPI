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
from app.memory.conversation_manager import ConversationManager

router = APIRouter(tags=["Chat"])

# Instanciamos el manager a nivel router (es thread-safe y sin estado mutable por request)
memory_manager = ConversationManager()

@router.post("/")
async def chat(
    request: QueryRequest,
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

    # --- Paso 2: Retrieval ---
    docs = await search_chunks(session, request.query, request.limit)

    # --- Paso 3: Generador de Texto Crudo y Guardado de Memoria ---
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
    # Para que el cliente pueda saber qué conversation_id se asignó (si mandó None),
    # podríamos devolverlo en headers. StreamingResponse admite headers custom.
    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={"X-Conversation-Id": str(conv_id)}
    )
