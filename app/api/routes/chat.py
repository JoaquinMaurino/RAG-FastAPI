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
    generada por Gemini vía LangChain, basada exclusivamente en los
    documentos almacenados en la base de datos.

    Flujo interno:
    1. Busca los chunks más relevantes a la pregunta (Retrieval)
    2. Pasa los Documents a la LCEL Chain para generar la respuesta (Generation)
    3. Devuelve la respuesta junto con las fuentes utilizadas
    """
    # --- Paso 1: Retrieval (DB injection separada de la chain) ---
    # search_chunks devuelve List[LangChain Document] con page_content y metadata.
    docs = await search_chunks(session, request.query, request.limit)

    # --- Paso 2: Generation (LCEL Chain) ---
    answer = await generate_answer(request.query, docs)

    # --- Paso 3: Armar la respuesta ---
    # Convertimos los Documents de vuelta a dicts para el schema Pydantic.
    results = [
        {
            "chunk_id": doc.metadata["chunk_id"],
            "document_id": doc.metadata["document_id"],
            "content": doc.page_content,
            "distance": doc.metadata["distance"],
        }
        for doc in docs
    ]

    return QueryResponse(
        query=request.query,
        answer=answer,
        results=results,
    )
