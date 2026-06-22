# System Architecture Overview

This document provides a high-level overview of the RAG FastAPI platform.

## Core Architectural Layers

The application is structured in isolated layers following a Domain-Driven Design (DDD) inspired pattern:

1. **API Layer (`app/api/`)**: Handles HTTP requests, payload validation using Pydantic, and delegates work to the services layer. Contains the FastAPI routers.
2. **Services Layer (`app/services/`)**: Contains the core business logic (e.g., `document_service`, `embedding_service`, `llm_service`, `agent_service`). This layer orchestrates the retrieval pipeline and database transactions but is decoupled from HTTP concerns.
3. **RAG Tools Layer (`app/rag/`)**: Pure text transformation functions. Includes the PDF `extractor`, the recursive `chunker`, and `retriever` logic. Does not have side effects.
4. **Data Access Layer (`app/database/`)**: Manages the PostgreSQL connection using SQLAlchemy Async and `pgvector`. Contains entity models.
5. **Agent Layer (`app/agents/`)**: LangChain-powered ReAct agents with function-calling capabilities via `@tool`.

## Data Flow Highlights

- **Uploads**: PDF files are persisted to local storage (`/uploads`). Text is extracted using `PyMuPDF`, recursively chunked, embedded using a local `all-MiniLM-L6-v2` model, and stored in PostgreSQL (`pgvector`).
- **Retrieval**: User queries are embedded using the same local model. A cosine similarity search retrieves the top $K$ semantic chunks.
- **Generation**: The retrieved chunks are injected into a prompt template. A generation request is sent to the LLM (Google Gemini). The response is streamed back to the client using Server-Sent Events (SSE) or managed through a LangChain ReAct agent.

## Diagram Reference

See the [System Architecture Diagram](../diagrams/system-architecture.mermaid) for a visual representation.
