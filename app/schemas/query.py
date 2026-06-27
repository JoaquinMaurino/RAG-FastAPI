"""
Schemas (DTOs) compartidos para los endpoints de búsqueda y chat.

Ambos endpoints comparten la misma estructura:
- Reciben una pregunta (query) con un límite de resultados
- Devuelven chunks relevantes con su distancia
- Chat adicionalmente incluye la respuesta del LLM (answer)
"""

import uuid

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Payload de entrada para búsqueda semántica y chat."""

    query: str = Field(
        ...,
        description="La pregunta o texto a buscar en la base de datos.",
        examples=["¿Cuáles son los requisitos para sacar un préstamo?"],
    )
    conversation_id: uuid.UUID | None = Field(
        default=None,
        description="ID de la conversación para mantener el contexto. Si no se envía, se creará una nueva.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Cantidad máxima de chunks a recuperar.",
    )


class ChunkResult(BaseModel):
    """Fragmento de documento encontrado por la búsqueda semántica."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    distance: float = Field(
        description="Distancia coseno. Más cerca a 0.0 = mayor similitud."
    )


class QueryResponse(BaseModel):
    """
    Respuesta unificada para búsqueda y chat.

    En /search: answer es None y se excluye del JSON de respuesta.
    En /chat:   answer contiene la respuesta generada por el LLM.
    """

    query: str
    conversation_id: uuid.UUID | None = None
    answer: str | None = None
    results: list[ChunkResult]
