"""
Ruta HTTP para el endpoint de Chat (RAG completo).

Este endpoint ejecuta el flujo completo de RAG:
    Pregunta → Embedding → Búsqueda Semántica → Contexto → LLM → Respuesta

Es una capa delgada que orquesta los servicios existentes:
    - search_service: recupera los chunks relevantes (Retriever)
    - llm_service: genera la respuesta usando Gemini (Generator)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.schemas.query import QueryRequest, QueryResponse
from app.services.search_service import search_chunks
from app.services.llm_service import generate_answer

router = APIRouter(tags=["Chat"])


@router.post("/", response_model=QueryResponse)
async def chat(
    request: QueryRequest,
    session: AsyncSession = Depends(get_session),
):
    """
    **Endpoint de Chat con RAG (Retrieval Augmented Generation)**

    Recibe una pregunta en lenguaje natural y devuelve una respuesta
    generada por Gemini, basada exclusivamente en los documentos
    almacenados en la base de datos.

    Flujo interno:
    1. Busca los chunks más relevantes a la pregunta (Retrieval)
    2. Envía la pregunta + los chunks al LLM (Generation)
    3. Devuelve la respuesta junto con las fuentes utilizadas
    """
    # --- Paso 1: Retrieval ---
    # Reutilizamos search_chunks, la misma función del endpoint /search.
    # Esto es posible porque la lógica vive en services/ y no en routes/.
    results = await search_chunks(session, request.query, request.limit)

    # Extraemos solo el texto de cada chunk para pasarlo como contexto al LLM.
    contexts = [r["content"] for r in results]

    # --- Paso 2: Generation ---
    answer = await generate_answer(request.query, contexts)

    # --- Paso 3: Armar la respuesta ---
    return QueryResponse(
        query=request.query,
        answer=answer,
        results=results,
    )
