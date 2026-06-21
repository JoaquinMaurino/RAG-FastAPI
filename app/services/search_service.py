from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chunk import Chunk
from app.services.embedding_service import get_embedding

async def search_chunks(session: AsyncSession, query: str, limit: int = 5) -> list[dict]:
    """
    Realiza una búsqueda semántica en la tabla de chunks.

    Flujo:
    1. Convierte el texto 'query' a un vector usando el mismo modelo que se 
       usó para la ingesta.
    2. Usa el operador de pgvector (cosine_distance) para calcular qué tan 
       lejos está el vector de la pregunta de cada vector en la DB.
    3. Ordena los resultados de menor a mayor distancia (los más cercanos primero).

    Args:
        session: Sesión de SQLAlchemy.
        query: La pregunta del usuario.
        limit: Cantidad de resultados a traer.
        
    Returns:
        Lista de diccionarios con el contenido del chunk y la métrica de distancia.
    """
    # 1. Generar el vector para la pregunta del usuario.
    # Usamos la versión singular porque es un solo texto.
    query_vector = get_embedding(query)
    
    # 2. pgvector agrega métodos a las columnas de tipo Vector.
    # cosine_distance() calcula matemáticamente la similitud. 
    # El resultado va de 0.0 (idénticos) a 2.0 (totalmente opuestos).
    distance_col = Chunk.embedding.cosine_distance(query_vector).label("distance")
    
    # 3. Armamos la query SQLAlchemy.
    # Pedimos devolver el objeto Chunk completo Y el cálculo de la distancia,
    # ordenado por esa misma distancia ascendente.
    stmt = (
        select(Chunk, distance_col)
        .order_by(distance_col.asc())
        .limit(limit)
    )
    
    result = await session.execute(stmt)
    # result.all() devuelve una lista de tuplas (Chunk_obj, distance_float)
    rows = result.all()
    
    # 4. Formatear la salida
    # Convertimos los objetos SQLAlchemy en diccionarios para que FastAPI 
    # los pueda parsear automáticamente con los modelos Pydantic.
    return [
        {
            "chunk_id": row.Chunk.id,
            "document_id": row.Chunk.document_id,
            "content": row.Chunk.content,
            "distance": row.distance
        }
        for row in rows
    ]
