"""
Servicio de Búsqueda Semántica (Retrieval).

Responsabilidad: ejecutar la búsqueda por similitud coseno contra pgvector
y devolver los resultados como objetos LangChain Document.

¿Por qué LangChain Document y no un dict?
------------------------------------------
LangChain define Document como la unidad estándar de información recuperada:
    - page_content: el texto del chunk
    - metadata:     cualquier dato extra (id, document_id, score, etc.)

Al devolver Document objects desde acá, el llm_service puede consumir
los resultados directamente usando la interfaz estándar de LangChain,
sin necesidad de saber cómo está estructurada nuestra base de datos.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.documents import Document

from app.database.models.chunk import Chunk
from app.services.embedding_service import get_embedding


async def search_chunks(
    session: AsyncSession,
    query: str,
    limit: int = 5,
) -> list[Document]:
    """
    Realiza una búsqueda semántica en la tabla de chunks.

    Flujo:
    1. Convierte el texto 'query' a un vector usando el mismo modelo de ingesta.
    2. Calcula la distancia coseno contra todos los chunks en la DB.
    3. Ordena por distancia ascendente (más cercanos = más relevantes).
    4. Envuelve cada resultado en un LangChain Document.

    Args:
        session: Sesión de SQLAlchemy.
        query:   La pregunta del usuario.
        limit:   Cantidad de chunks a recuperar.

    Returns:
        Lista de LangChain Documents con el texto en page_content
        y los metadatos (ids, score) en metadata.
    """
    query_vector = get_embedding(query)

    distance_col = Chunk.embedding.cosine_distance(query_vector).label("distance")

    stmt = (
        select(Chunk, distance_col)
        .order_by(distance_col.asc())
        .limit(limit)
    )

    result = await session.execute(stmt)
    rows = result.all()

    # Convertimos cada fila en un LangChain Document.
    # page_content es el texto del chunk — lo que el LLM va a leer.
    # metadata guarda los datos de trazabilidad (para las "fuentes" en la respuesta).
    return [
        Document(
            page_content=row.Chunk.content,
            metadata={
                "chunk_id": str(row.Chunk.id),
                "document_id": str(row.Chunk.document_id),
                "distance": round(float(row.distance), 4),
            },
        )
        for row in rows
    ]
