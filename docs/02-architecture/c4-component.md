# Component Architecture (C4 Model)

The Component diagram reveals the internal structure of the FastAPI Application. The architecture strictly follows a separation of concerns pattern, keeping HTTP routing completely isolated from business logic and database interactions.

```mermaid
%%{init: {'theme': 'default'}}%%
{{ include: ../diagrams/c4-component.mermaid }}
```

*(Note: If the include macro does not render, please view the raw Mermaid file in `docs/diagrams/c4-component.mermaid`)*

## Core Components

### 1. API Routers (`app/api/routes/`)
Responsible exclusively for HTTP logic. They accept requests, validate JSON payloads using Pydantic schemas, invoke the necessary service, and return HTTP responses or status codes.

### 2. Services (`app/services/`)
The business logic orchestrators. They do not know about HTTP.
- **Document Service**: Manages the ingestion pipeline (save, extract, chunk, embed, store).
- **Search Service**: Executes `pgvector` cosine similarity queries via SQLAlchemy.
- **LLM Service**: Connects to Gemini using a standard LangChain RAG pipeline with streaming support.
- **Agent Service**: Defines and executes the LangChain ReAct agent, giving the LLM autonomous access to the Search and Document services.

### 3. RAG Engine (`app/rag/`)
Pure transformational functions without side effects.
- **Extractor**: Uses `PyMuPDF` to convert PDFs to strings.
- **Chunker**: Implements a custom recursive character splitting algorithm.

### 4. Embedding Service (`app/services/embedding_service.py`)
Implemented as a Singleton managing the local `sentence-transformers` model (`all-MiniLM-L6-v2`). Keeps the heavy ~90MB model in memory to prevent loading times on every request.
