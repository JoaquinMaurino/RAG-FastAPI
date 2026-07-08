"""
Re-ranking con Cross-Encoder.

El re-ranking toma una lista inicial de candidatos (por ejemplo, del hybrid search)
y usa un modelo Cross-Encoder para darles un puntaje más preciso. 

A diferencia de los Bi-Encoders (usados en embedding_service), los Cross-Encoders
procesan la query y el documento a la vez, capturando mejor las interacciones entre
palabras, pero son más lentos, por lo que solo se aplican a los top-N documentos.
"""

from loguru import logger
from sentence_transformers import CrossEncoder
from langchain_core.documents import Document

from app.core.config import settings

_reranker: CrossEncoder | None = None


def _get_reranker() -> CrossEncoder:
    """Lazy loading del modelo de cross-encoder (Singleton)."""
    global _reranker
    if _reranker is None:
        logger.info(f"Loading re-ranking model '{settings.reranking_model}'...")
        # Default device inference. sentence_transformers usará GPU si existe o CPU.
        _reranker = CrossEncoder(settings.reranking_model)
        logger.info("Re-ranking model loaded successfully.")
    return _reranker


def rerank_documents(query: str, docs: list[Document], top_n: int = 5) -> list[Document]:
    """
    Toma los documentos recuperados y los re-ordena usando el Cross-Encoder.

    Args:
        query: La consulta original o reescrita.
        docs: Lista de candidatos (recuperados por vector/bm25).
        top_n: Cantidad final de documentos a retornar.

    Returns:
        Lista de documentos re-ordenados, limitados a top_n, con el score original 
        y el nuevo 'rerank_score' en metadata.
    """
    if not docs:
        return []

    try:
        model = _get_reranker()

        # Preparamos los pares (query, documento)
        pairs = [[query, doc.page_content] for doc in docs]

        # Calculamos los scores (devuelve un listado de floats)
        scores = model.predict(pairs)

        # Asignamos el score a la metadata de cada documento para trazabilidad
        for doc, score in zip(docs, scores):
            doc.metadata["rerank_score"] = float(score)

        # Ordenamos descendente por el nuevo score
        docs_sorted = sorted(docs, key=lambda d: d.metadata["rerank_score"], reverse=True)

        return docs_sorted[:top_n]
    except Exception as e:
        # Graceful degradation: si el reranker falla, devolvemos
        # los docs originales sin re-ordenar (limitados a top_n).
        logger.error(f"Re-ranking failed: {e}. Returning original documents.")
        return docs[:top_n]
