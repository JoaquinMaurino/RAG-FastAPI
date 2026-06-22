# RAG FastAPI Documentation

Welcome to the internal engineering documentation for the RAG FastAPI system.

## Project Purpose
This project is a production-style AI Backend application designed to act as an internal company knowledge assistant. It allows users to upload PDF documents, processes them using a Retrieval-Augmented Generation (RAG) pipeline, and provides conversational interfaces (both standard RAG and Agent-based) to interact with the stored knowledge.

## Quick Links
- **[Architecture](system-architecture.md)**
- **[RAG Implementation](../03-rag/ingestion-pipeline.md)**
- **[API Reference](../04-api/endpoints.md)**
- **[Deployment](../05-deployment/docker-setup.md)**

## Tech Stack Overview
- **Backend Framework**: FastAPI
- **Database**: PostgreSQL with `pgvector`
- **ORM**: SQLAlchemy Async
- **Embeddings**: Local `sentence-transformers` (`all-MiniLM-L6-v2`)
- **LLM Provider**: Google Gemini (via `langchain-google-genai`)
- **Orchestration**: LangChain (LCEL and ReAct Agents)
- **Testing**: Pytest & httpx (Async testing with DB mocking)
