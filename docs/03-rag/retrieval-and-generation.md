# Retrieval and Generation

The ultimate goal of the RAG system is to answer user queries using the ingested knowledge.

## Query Processing Flow

1. The user sends a query string to the API.
2. The `search_service` passes the query string to the `embedding_service` to generate a 384-dimensional query vector.
3. An SQLAlchemy query is executed against PostgreSQL:
   ```python
   stmt = select(Chunk).order_by(Chunk.embedding.cosine_distance(query_vector)).limit(limit)
   ```
4. The top $K$ semantic matches are returned.

## Generation (LLM Invocation)

The LLM logic is managed by LangChain in `app/services/llm_service.py`.

### LangChain LCEL (LangChain Expression Language)
The generation pipeline is defined as a chain:
```python
_qa_chain = _prompt_template | _llm | StrOutputParser()
```

- **Prompt Construction**: The retrieved chunks are formatted into a single context string. The system prompt instructs the LLM: *"Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know."*
- **Streaming Execution**: Instead of waiting for the full response to be generated (which can take several seconds), the chain is invoked using `.astream()`. 
- **FastAPI SSE**: The API route (`/chat/`) wraps the async generator in FastAPI's `StreamingResponse(media_type="text/plain")`, piping tokens directly to the user's terminal or frontend as they are produced by Google Gemini.

## Diagram

See the [Query Processing Diagram](../diagrams/query-processing.mermaid) for a visual representation.
