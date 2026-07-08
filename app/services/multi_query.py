"""
Servicio de Multi-Query Retrieval.

Pipeline completo:
  query cruda
    → rewrite_query (2.1): resuelve referencias históricas → query normalizada
    → generate_query_variants (2.1b): amplía cobertura semántica → N queries
    → búsquedas en paralelo (asyncio.gather)
    → deduplicación por chunk_id
    → resultado unificado para el LLM

Activación:
  MULTI_QUERY_ENABLED=true  →  activa este módulo
  MULTI_QUERY_ENABLED=false →  comportamiento idéntico a Fase 2.1 (solo rewrite)
"""

import asyncio
import json

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.query import SearchFilters
from app.services.llm_factory import get_llm
from app.services.search_service import search_chunks


# ── Prompt de generación de variantes ────────────────────────────────────────
# Pedimos exactamente N líneas, una por variante, sin numeración ni prefijos.
# El parseo es simple: split por newline + filtro de líneas vacías.
_VARIANTS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a search query diversification assistant. Your job is to generate "
        "alternative formulations of a search query to maximize retrieval recall.\n\n"
        "Rules:\n"
        "- Generate exactly {n} alternative versions of the given query.\n"
        "- Each alternative must express the same information need but with "
        "  different vocabulary, angle, or level of abstraction.\n"
        "- Each alternative must be on its own line, no numbering, no bullets, no extra text.\n"
        "- Keep the same language as the original query.\n"
        "- Each alternative should be a valid standalone search query (5-20 words)."
    ),
    (
        "human",
        "Original query: {query}\n\n"
        "Generate {n} alternative search queries:"
    ),
])

# Temperatura ligeramente elevada para fomentar diversidad léxica entre variantes.
_variants_chain = _VARIANTS_PROMPT | get_llm(temperature=0.4) | StrOutputParser()


async def generate_query_variants(query: str, n: int | None = None) -> list[str]:
    """
    Genera N reformulaciones semánticamente diversas de la query dada.

    Las variantes se generan a partir de la query ya normalizada por rewrite_query,
    no de la query cruda del usuario.

    Args:
        query: La query normalizada (salida de rewrite_query).
        n:     Cantidad de variantes. Por defecto usa settings.multi_query_n.

    Returns:
        Lista de strings con las variantes. Si la generación falla, devuelve
        [query] (la query original como único elemento — degradación elegante).
    """
    n = n or settings.multi_query_n

    try:
        raw = await _variants_chain.ainvoke({"query": query, "n": n})

        variants = [line.strip() for line in raw.strip().splitlines() if line.strip()]

        if not variants:
            logger.warning(f"Variant generator returned empty output for query: '{query}'")
            return [query]

        logger.info(
            f"Generated {len(variants)} query variants for '{query}': {variants}"
        )
        return variants

    except Exception as e:
        logger.warning(
            f"Query variant generation failed — using original query only. "
            f"error={type(e).__name__}: {e}"
        )
        return [query]


async def multi_query_search(
    session: AsyncSession,
    query: str,
    limit: int = 5,
    chat_history: list[BaseMessage] | None = None,
    filters: SearchFilters | None = None,
) -> list[Document]:
    """
    Ejecuta búsquedas en paralelo con N variantes de la query y deduplica resultados.

    Flujo:
    1. Genera N variantes de la query.
    2. Ejecuta search_chunks con cada variante en paralelo (asyncio.gather).
    3. Deduplica por chunk_id — nunca el mismo chunk dos veces al LLM.
    4. Preserva el orden de relevancia (el chunk más cercano de cada variante
       aparece antes que chunks más lejanos).

    Args:
        session:      Sesión de SQLAlchemy para las búsquedas.
        query:        Query normalizada (ya procesada por rewrite_query).
        limit:        Chunks a recuperar por variante. El resultado final puede
                      tener hasta n * limit chunks únicos antes de truncar.
        chat_history: Solo se usa si se quiere pasar al rewriter externamente.
                      Este módulo no reescribe — recibe la query ya normalizada.

    Returns:
        Lista de Documents deduplicados, listos para pasar al LLM.
    """
    n = settings.multi_query_n
    variants = await generate_query_variants(query, n=n)

    # Ejecutamos todas las búsquedas en paralelo.
    # Si una búsqueda falla, la capturamos para no bloquear las demás.
    async def safe_search(q: str) -> list[Document]:
        try:
            return await search_chunks(session, q, limit=limit, filters=filters)
        except Exception as e:
            logger.warning(f"Search failed for variant '{q}': {type(e).__name__}: {e}")
            return []

    results_per_variant: list[list[Document]] = await asyncio.gather(
        *[safe_search(v) for v in variants]
    )

    # Deduplicamos por chunk_id manteniendo el orden de aparición.
    # El primer resultado para cada chunk_id gana (viene de la variante
    # con mejor matching para ese chunk).
    seen_chunk_ids: set[str] = set()
    deduplicated: list[Document] = []

    for docs in results_per_variant:
        for doc in docs:
            chunk_id = doc.metadata.get("chunk_id")
            if chunk_id and chunk_id not in seen_chunk_ids:
                seen_chunk_ids.add(chunk_id)
                deduplicated.append(doc)

    logger.info(
        f"Multi-query retrieval: {len(variants)} variants × {limit} chunks → "
        f"{len(deduplicated)} unique chunks after dedup"
    )
    return deduplicated
