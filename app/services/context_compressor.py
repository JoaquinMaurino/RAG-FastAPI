"""
Context Compression.

Extrae solo las oraciones/párrafos relevantes de cada chunk recuperado
usando un LLM rápido (temperature=0.0) antes de enviarlo al prompt final.
Esto reduce drásticamente los tokens de contexto y minimiza alucinaciones causadas
por información irrelevante que "viaja" junto con la relevante en el mismo chunk.
"""

from loguru import logger
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.services.llm_factory import get_llm

# Usamos un prompt simple y directo.
COMPRESSION_PROMPT = PromptTemplate.from_template(
    """You are an expert at extracting relevant information from text.
Given the following user query and a document, extract only the sentences or paragraphs 
that are strictly relevant to answering the query. If the document contains no relevant 
information, return exactly: "NO_RELEVANT_INFO".

Query: {query}

Document:
{context}

Relevant extracted information:"""
)

async def compress_documents(query: str, docs: list[Document]) -> list[Document]:
    """
    Comprime una lista de documentos reteniendo solo la información útil para la query.
    """
    if not docs:
        return []

    try:
        # Obtenemos el LLM (idealmente uno barato y rápido para esta tarea interna)
        llm = get_llm(temperature=0.0)
        
        # Armamos la cadena LCEL
        chain = COMPRESSION_PROMPT | llm | StrOutputParser()
        
        compressed_docs = []
        
        # Iteramos y comprimimos cada documento. 
        # (Podría hacerse en paralelo con asyncio.gather o chain.abatch, 
        # pero empezamos iterando para evitar rate limits si hay muchos docs).
        for doc in docs:
            logger.debug(f"Compressing document: {doc.metadata.get('chunk_id')}")
            
            result = await chain.ainvoke({
                "query": query,
                "context": doc.page_content
            })
            
            result = result.strip()
            
            # Si el modelo determinó que no hay info útil, lo descartamos
            if result == "NO_RELEVANT_INFO":
                continue
                
            # Clonamos el documento original pero con el contenido comprimido
            # y mantenemos los metadatos intactos para trazabilidad (fuentes, scores).
            compressed_doc = Document(
                page_content=result,
                metadata={**doc.metadata, "compressed": True}
            )
            compressed_docs.append(compressed_doc)
            
        return compressed_docs
        
    except Exception as e:
        # Graceful degradation: si la compresión falla, devolvemos los originales
        logger.error(f"Context compression failed: {e}. Returning original documents.")
        return docs
