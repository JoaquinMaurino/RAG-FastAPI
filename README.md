# RAG FastAPI Knowledge Assistant

A production-grade AI Backend platform designed to act as an internal company knowledge assistant. It features a complete Retrieval-Augmented Generation (RAG) pipeline and autonomous LangChain Agents, all served through a high-performance asynchronous REST API.

---

## Overview

**What problem the system solves:**  
Organizations generate vast amounts of documentation (PDFs, reports, manuals) that are difficult to search and synthesize. Traditional keyword search is often inadequate for complex queries. This system solves that by enabling semantic search and conversational AI interactions over private company data without compromising data privacy (embeddings run locally).

**Main Use Cases:**  
- Intelligent document search and retrieval.
- Automated question answering based exclusively on uploaded knowledge bases.
- Autonomous agent interactions (e.g., summarizing documents, counting stored records).

**Target Users:**  
- Company employees needing fast access to internal information.
- Developers looking for a reference architecture for production RAG systems.

---

## Architecture

The system is built on a layered architecture (API -> Services -> RAG Engine -> DB) ensuring separation of concerns.

```mermaid
graph TD
    User([User Client])

    subgraph "API Layer (FastAPI)"
        DocsRoute["/documents"]
        SearchRoute["/search"]
        ChatRoute["/chat"]
        AgentRoute["/agent"]
    end

    subgraph "Service Layer"
        DocSvc[Document Service]
        SearchSvc[Search Service]
        LLMSvc[LLM Service]
        AgentSvc[Agent Service]
    end

    subgraph "RAG Engine"
        Extractor[PDF Extractor]
        Chunker[Text Chunker]
        Embedder[Embedding Service]
    end

    subgraph "Data Persistence"
        Postgres[(PostgreSQL + pgvector)]
        FS[Local File System]
    end

    subgraph "External Providers"
        Gemini[Google Gemini API]
    end

    User -->|HTTP POST| DocsRoute
    User -->|HTTP POST| ChatRoute
    User -->|HTTP POST| AgentRoute

    DocsRoute --> DocSvc
    ChatRoute --> LLMSvc
    AgentRoute --> AgentSvc

    DocSvc --> Extractor
    DocSvc --> Chunker
    DocSvc --> Embedder
    DocSvc --> Postgres
    DocSvc --> FS

    LLMSvc --> SearchSvc
    SearchSvc --> Embedder
    SearchSvc --> Postgres
    LLMSvc --> Gemini

    AgentSvc --> Gemini
    AgentSvc -.->|Tools| DocSvc
    AgentSvc -.->|Tools| SearchSvc
```

---

## Features

- **PDF Ingestion**: Fast text extraction using PyMuPDF (`fitz`).
- **Semantic Chunking**: Custom recursive character text splitting preserving context overlap.
- **Local Embeddings**: Zero-cost, high-speed local embedding generation using `sentence-transformers` (`all-MiniLM-L6-v2`).
- **Vector Search**: Cosine similarity search directly within PostgreSQL using the `pgvector` extension.
- **Streaming LLM Responses**: Native SSE (Server-Sent Events) streaming for the standard RAG `/chat` endpoint.
- **Autonomous Agents**: LangChain ReAct Agents capable of routing queries and invoking internal backend tools dynamically.
- **Asynchronous IO**: Built fully on `asyncio` using `asyncpg` and SQLAlchemy async sessions.
- **Automated Testing**: Comprehensive `pytest` suite with `httpx` and database mocking.

---

## Tech Stack

- **Python Version**: 3.12+
- **Backend Framework**: FastAPI
- **Vector Database**: PostgreSQL 16 + `pgvector`
- **ORM**: SQLAlchemy (Async)
- **Embedding Models**: `sentence-transformers` (`all-MiniLM-L6-v2` / 384 dimensions)
- **LLM Provider**: Google Gemini (via `langchain-google-genai`)
- **Orchestration**: LangChain
- **Storage**: Local Disk (File System)
- **Infrastructure**: Docker & Docker Compose
- **Testing**: Pytest, Pytest-Asyncio

---

## Project Structure

```text
app/
├── agents/             # LangChain ReAct agents and tools
├── api/
│   └── routes/         # FastAPI HTTP controllers
├── core/               # App configuration (Pydantic Settings)
├── database/           # SQLAlchemy models and async session makers
├── etl/                # (Future) Ingestion pipelines
├── rag/                # Pure RAG functions: extractor, chunker
├── schemas/            # Pydantic validation schemas
└── services/           # Business logic orchestrators
tests/                  # Pytest suite and conftest.py
docs/                   # Comprehensive technical documentation
```

---

## RAG Workflow

1. **Document Ingestion**: PDF is uploaded to `/documents`. Saved to local disk with a UUID.
2. **Extraction**: `PyMuPDF` reads the PDF and extracts raw text, preserving page markers.
3. **Chunking**: A Recursive Character Splitter divides the text into 1000-character chunks with a 200-character overlap.
4. **Embedding Generation**: The `EmbeddingService` processes chunks in batches through the local `sentence-transformers` model.
5. **Vector Storage**: Document metadata, chunks, and normalized vectors are persisted to Postgres/`pgvector` in a single transaction.
6. **Retrieval**: User queries are embedded, and a cosine distance search (`<->`) retrieves the top $K$ chunks.
7. **LLM Generation**: The chunks are injected into a LangChain `ChatPromptTemplate` and passed to Gemini, which streams the response back to the user.

```mermaid
sequenceDiagram
    actor User
    participant API as FastAPI Router
    participant LLM as LLM Service
    participant Search as Search Service
    participant Embedder as Embedding Service
    participant DB as PostgreSQL (pgvector)
    participant Gemini as Google Gemini API

    User->>API: POST /chat/ {"query": "..."}
    API->>LLM: generate_answer_stream(query)
    
    LLM->>Search: search_chunks(query, limit=5)
    Search->>Embedder: get_embedding(query)
    Embedder-->>Search: Query Vector [0.1, 0.4, ...]
    
    Search->>DB: Cosine Similarity Search (<->)
    DB-->>Search: Top 5 Chunks
    Search-->>LLM: List[Document]
    
    LLM->>LLM: Inject Chunks into PromptTemplate
    
    LLM->>Gemini: astream(prompt)
    loop SSE Stream
        Gemini-->>LLM: chunk token
        LLM-->>API: chunk token
        API-->>User: data: chunk token
    end
```

---

## API Documentation

FastAPI automatically generates interactive OpenAPI documentation. Once the server is running, visit:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

**Key Endpoints:**
- `GET /documents/`: List uploaded documents.
- `POST /documents/`: Upload a new PDF.
- `POST /search/`: Perform raw semantic search.
- `POST /chat/`: Standard RAG chat (Streaming).
- `POST /agent/`: LangChain ReAct Agent chat.

---

## Installation

### Prerequisites
- Python 3.12+
- Docker & Docker Compose (for PostgreSQL)

### Steps

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd rag-fastapi
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start the database:**
   ```bash
   docker-compose up -d postgres
   ```

---

## Environment Variables

Create a `.env` file in the root directory:

| Variable | Description | Example |
|----------|-------------|---------|
| `PROJECT_NAME` | Swagger UI Title | `RAG FastAPI` |
| `DEBUG` | Enable debug logs | `True` |
| `DATABASE_URL` | Asyncpg Postgres connection | `postgresql+asyncpg://postgres:postgres@localhost:5432/rag_db` |
| `UPLOAD_DIR` | Path to store PDFs | `./uploads` |
| `GEMINI_API_KEY` | Google Gemini API Key | `AIzaSy...` |
| `GEMINI_MODEL` | Gemini Model version | `gemini-2.0-flash` |

---

## Running Locally

1. **Start the FastAPI application:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

2. **Run Tests:**
   ```bash
   pytest -v
   ```

---

## Example Requests

**1. Upload a PDF**
```bash
curl -X POST http://127.0.0.1:8000/documents/ \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/your/report.pdf"
```

**2. Chat with RAG (Streaming)**
```bash
curl -N -X POST http://127.0.0.1:8000/chat/ \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"What is the summary of the report?\", \"limit\": 5}"
```

**3. Chat with Agent**
```bash
curl -X POST http://127.0.0.1:8000/agent/ \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"How many documents are stored in the system?\"}"
```

---

## Deployment

The application is containerized. For production deployment, use the provided `docker-compose.yml` to spin up both the FastAPI application and the PostgreSQL/pgvector instance.

```bash
docker-compose up -d --build
```

*Note: In a true production environment, the database should be hosted on a managed service (e.g., AWS RDS, Cloud SQL) rather than a Docker container.*

---

## Monitoring and Logging

- **Logging**: The application uses `loguru` for structured, colorized logging across the API and Service layers.
- **Error Handling**: All major extraction, database, and validation errors are intercepted and translated into human-readable HTTP `422` or `500` responses.
- *(Future)*: OpenTelemetry tracing and Prometheus metrics are planned for Phase 5.

---

## Known Limitations

- **Synchronous Bottlenecks**: PDF text extraction (`PyMuPDF`) and embedding generation (`sentence-transformers`) are CPU-bound operations that currently block the `asyncio` event loop.
- **No Authentication**: Endpoints are completely public. There is no tenant or user isolation.
- **File System Persistence**: PDFs are stored on the local disk inside the container, requiring volume mounts to prevent data loss on container restart.

---

## Roadmap

Upcoming architectural phases (as defined in internal documentation):
- **Phase 3 (Step 15)**: Implement Redis and Background Workers (Celery/RQ) to offload synchronous ingestion tasks.
- **Phase 4 (Step 16)**: Introduce Apache Airflow for automated data ingestion pipelines.
- **Phase 5 (Step 17)**: Add Observability (OpenTelemetry, Prometheus, Grafana).
- **Phase 6 (Step 18)**: Integrate RAGAS/DeepEval for automated answer quality evaluation.

---

## Contributing

Contributions are welcome! Please ensure that:
1. All new API routes use Pydantic models for validation.
2. New business logic is placed in `app/services/`, not in the routers.
3. Tests are added to the `tests/` directory and pass using `pytest`.
4. You run `pytest -v` before submitting a Pull Request.

---

## License

This project is licensed under the MIT License - see the LICENSE file for details.
