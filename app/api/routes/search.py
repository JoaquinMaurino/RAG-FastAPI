from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.schemas.query import QueryRequest, QueryResponse
from app.services.search_service import search_chunks

router = APIRouter(tags=["Search"])

@router.post("/", response_model=QueryResponse, response_model_exclude_none=True)
async def perform_search(
    request: QueryRequest,
    session: AsyncSession = Depends(get_session)
):

    """
    **Endpoint de Búsqueda Semántica (Retriever)**

    Recibe una pregunta en lenguaje natural y busca en la base de datos de PostgreSQL
    los fragmentos de documentos (chunks) que sean semánticamente más similares.
    
    Este endpoint representa la fase "Retrieve" del patrón RAG.
    La respuesta de este endpoint (los textos de los chunks) es lo que en el futuro
    se le inyectará al LLM para que pueda responder la pregunta.
    """
    docs = await search_chunks(session, request.query, request.limit)

    # Convertimos los Documents al formato dict que espera QueryResponse.
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
        results=results,
    )
