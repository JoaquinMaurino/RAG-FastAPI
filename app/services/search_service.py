"""
Servicio de Búsqueda — Fase 2.2: Hybrid Search (Semantic + Lexical BM25).

Modos disponibles (SEARCH_MODE):
---------------------------------
  hybrid:        Semántico + Léxico fusionados con Reciprocal Rank Fusion (RRF).
                 Default recomendado para producción.
  semantic_only: Solo búsqueda vectorial (comportamiento pre-2.2).
                 Útil para A/B testing o si el corpus es puramente conceptual.
  lexical_only:  Solo full-text search (PostgreSQL tsvector/tsquery).
                 Útil para debug, queries con términos exactos, o testing.

¿Qué es Reciprocal Rank Fusion (RRF)?
--------------------------------------
En vez de intentar normalizar y combinar los scores directamente (difícil porque
los scores de cosine distance y ts_rank tienen escalas muy distintas), RRF solo
usa la *posición* (rank) de cada resultado en su lista:

    score_RRF(doc) = Σ  1 / (k + rank_i)

donde k=60 es una constante que amortigua el peso de las primeras posiciones.
Esto es robusto porque no asume nada sobre las distribuciones de scores de cada
sistema — solo combina "quién apareció más arriba en cada lista".

Trigger en PostgreSQL:
-----------------------
La columna content_tsv se actualiza automáticamente via trigger en cada INSERT/UPDATE.
Ver docs/migrations/add_tsvector_hybrid_search.sql para la migración completa.
"""

import asyncio

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.documents import Document

from app.core.config import settings
from app.database.models.chunk import Chunk
from app.services.embedding_service import get_embedding


async def _semantic_search(
    session: AsyncSession,
    query: str,
    limit: int,
) -> list[Document]:
    """Búsqueda por similitud coseno sobre pgvector."""
    query_vector = get_embedding(query)
    distance_col = Chunk.embedding.cosine_distance(query_vector).label("distance")

    stmt = (
        select(Chunk, distance_col)
        .where(Chunk.embedding.is_not(None))
        .order_by(distance_col.asc())
        .limit(limit)
    )

    result = await session.execute(stmt)
    return [
        Document(
            page_content=row.Chunk.content,
            metadata={
                "chunk_id": str(row.Chunk.id),
                "document_id": str(row.Chunk.document_id),
                "distance": round(float(row.distance), 4),
            },
        )
        for row in result.all()
    ]


async def _lexical_search(
    session: AsyncSession,
    query: str,
    limit: int,
) -> list[Document]:
    """
    Búsqueda léxica con tsvector/tsquery de PostgreSQL (equivalente a BM25).
    
    Usa ts_rank para ordenar por relevancia léxica. Si content_tsv está vacío
    (chunks previos a la migración), devuelve lista vacía — graceful degradation.
    """
    # Convertimos la query a tsquery: cada palabra se busca como término léxico.
    # plainto_tsquery convierte texto libre en tsquery sin necesidad de sintaxis especial.
    stmt = (
        select(
            Chunk,
            func.ts_rank(Chunk.content_tsv, func.plainto_tsquery("simple", query)).label("rank"),
        )
        .where(
            Chunk.content_tsv.is_not(None),
            Chunk.content_tsv.op("@@")(func.plainto_tsquery("simple", query)),
        )
        .order_by(text("rank DESC"))
        .limit(limit)
    )

    result = await session.execute(stmt)
    return [
        Document(
            page_content=row.Chunk.content,
            metadata={
                "chunk_id": str(row.Chunk.id),
                "document_id": str(row.Chunk.document_id),
                "ts_rank": round(float(row.rank), 4),
            },
        )
        for row in result.all()
    ]


def _reciprocal_rank_fusion(
    semantic_docs: list[Document],
    lexical_docs: list[Document],
    k: int,
    limit: int,
) -> list[Document]:
    """
    Combina dos listas de documentos rankeados usando Reciprocal Rank Fusion.

    score_RRF(doc) = Σ  1 / (k + rank)
    (rank es 1-indexed, el primer resultado de cada lista tiene rank=1)

    Preserva el documento con sus metadatos originales y agrega el rrf_score
    resultante para auditoría/debugging.
    """
    # Mapa chunk_id → Document (primera aparición, para no perder metadatos)
    docs_by_id: dict[str, Document] = {}
    rrf_scores: dict[str, float] = {}

    def accumulate(docs: list[Document]) -> None:
        for rank, doc in enumerate(docs, start=1):
            chunk_id = doc.metadata.get("chunk_id", "")
            if chunk_id not in docs_by_id:
                docs_by_id[chunk_id] = doc
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (k + rank)

    accumulate(semantic_docs)
    accumulate(lexical_docs)

    # Ordenamos por score RRF descendente y devolvemos el top-limit
    sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)
    result = []
    for chunk_id in sorted_ids[:limit]:
        doc = docs_by_id[chunk_id]
        doc.metadata["rrf_score"] = round(rrf_scores[chunk_id], 6)
        result.append(doc)

    return result


async def search_chunks(
    session: AsyncSession,
    query: str,
    limit: int = 5,
) -> list[Document]:
    """
    Punto de entrada principal de búsqueda. El modo se controla via SEARCH_MODE.

    Args:
        session: Sesión de SQLAlchemy.
        query:   La query normalizada (ya procesada por rewrite_query si aplica).
        limit:   Cantidad de chunks a devolver.

    Returns:
        Lista de LangChain Documents listos para el LLM.
    """
    mode = settings.search_mode

    if mode == "semantic_only":
        return await _semantic_search(session, query, limit)

    if mode == "lexical_only":
        return await _lexical_search(session, query, limit)

    # hybrid: ejecutamos ambas en paralelo y fusionamos con RRF.
    # Pedimos más candidatos a cada sistema (×2) para que la fusión tenga
    # material suficiente y el top-limit final sea de alta calidad.
    candidate_limit = limit * 2
    semantic_docs, lexical_docs = await asyncio.gather(
        _semantic_search(session, query, candidate_limit),
        _lexical_search(session, query, candidate_limit),
    )

    return _reciprocal_rank_fusion(
        semantic_docs,
        lexical_docs,
        k=settings.hybrid_rrf_k,
        limit=limit,
    )
