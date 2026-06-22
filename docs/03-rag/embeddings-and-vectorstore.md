# Embeddings and Vector Store

## Embedding Strategy

The system uses local models rather than paying for API-based embedding providers (like OpenAI or Gemini Embeddings). This decision drastically reduces operating costs and latency.

### The Model: `all-MiniLM-L6-v2`
Implemented in `app/services/embedding_service.py` using `sentence-transformers`.
- **Dimensions**: 384
- **Memory Footprint**: ~90 MB in RAM.
- **Performance**: Capable of generating batch embeddings in milliseconds on a standard CPU.

### Singleton Pattern
Loading a 90MB PyTorch model from disk takes 1-2 seconds. If done per-request, performance would be unacceptable. The `embedding_service` uses a Singleton pattern: the model is lazily loaded into memory on the first request and kept alive in RAM for the lifetime of the FastAPI worker.

*Note: Generating embeddings is a CPU-bound operation. Currently, this runs synchronously, which temporarily blocks the FastAPI async event loop. Moving this to a Redis worker (Celery/RQ) is a known future improvement.*

## Vector Database (`pgvector`)

Instead of adopting a dedicated vector database (like Pinecone, Milvus, or Qdrant), this project uses **PostgreSQL with the `pgvector` extension**. 

### Advantages
1. **ACID Compliance**: Document metadata and vectors are stored in the same transaction. We don't have to worry about the vector store becoming out-of-sync with the relational database.
2. **Simplicity**: No extra infrastructure to deploy.

### Configuration
- We normalize vectors (`normalize_embeddings=True`) before inserting. This maps vectors onto a unit sphere.
- Because vectors are normalized, we can use the inner product / cosine distance operator (`<->` in pgvector) which is highly optimized.
- The `Chunk` model defines the embedding column as `mapped_column(Vector(384))`.
