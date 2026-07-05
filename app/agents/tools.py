import uuid
from langchain_core.tools import tool
from loguru import logger

from app.core.config import settings
from app.database.session import async_session_factory
from app.services import document_service, search_service
from app.services.query_rewriter import rewrite_query
from app.services.multi_query import multi_query_search

@tool
async def count_documents() -> str:
    """
    Returns the total number of documents currently stored in the system.
    Use this tool whenever the user asks about the total amount or count of uploaded documents/PDFs.
    """
    logger.info("Tool executed: count_documents")
    async with async_session_factory() as session:
        docs = await document_service.get_all(session)
        return f"There are currently {len(docs)} documents stored in the system."


@tool
async def get_document_info(document_id: str) -> str:
    """
    Returns the metadata and details of a specific document given its UUID.
    Use this tool when you have a specific document ID and need to know its filename, path, or raw text.
    """
    logger.info(f"Tool executed: get_document_info (id={document_id})")
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        return "Error: Invalid document_id format. Must be a UUID."
        
    async with async_session_factory() as session:
        doc = await document_service.get_by_id(session, doc_uuid)
        if not doc:
            return f"Error: Document with ID {document_id} not found."
        
        return (
            f"Document Details:\n"
            f"- ID: {doc.id}\n"
            f"- Filename: {doc.filename}\n"
            f"- Created At: {doc.created_at}\n"
            f"- Total Characters: {len(doc.raw_text) if doc.raw_text else 0}"
        )


@tool
async def search_documents(query: str) -> str:
    """
    Performs a semantic search over the content of all uploaded documents.
    Use this tool to find information, answer questions, or retrieve context based on user queries.
    Pass a clear, concise search query in English or Spanish.
    """
    logger.info(f"Tool executed: search_documents (query='{query}')")

    # Rewrite the query for better retrieval quality.
    # No chat_history here — the agent already formulates explicit tool queries,
    # so the rewriter acts as a normalization pass. Falls back to original on failure.
    search_query = await rewrite_query(query, chat_history=None)

    async with async_session_factory() as session:
        # MULTI_QUERY_ENABLED: same switch as /chat for consistency.
        if settings.multi_query_enabled:
            docs = await multi_query_search(session, search_query, limit=5)
        else:
            docs = await search_service.search_chunks(session, search_query, limit=5)

        if not docs:
            return "No relevant information found in the documents."

        context_block = "\n\n".join(
            f"[Source {i + 1}] {doc.page_content}" for i, doc in enumerate(docs)
        )
        return f"Found the following relevant information:\n\n{context_block}"
