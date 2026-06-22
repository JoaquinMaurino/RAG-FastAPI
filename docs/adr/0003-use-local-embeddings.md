# ADR 0003: Use Local Embedding Models

**Date:** 2026-06-22  
**Status:** Accepted

## Context
Text must be converted into numerical vectors (embeddings) during the RAG ingestion and retrieval phases.

## Considered Options
* OpenAI Embeddings API (`text-embedding-ada-002`)
* Google Gemini Embeddings API
* Local models via `sentence-transformers`

## Decision
We chose to host a local model (`all-MiniLM-L6-v2`) via `sentence-transformers`.

## Rationale
1. **Cost Efficiency**: Generating embeddings for large PDF documents over an API can become expensive quickly. Running a lightweight model locally incurs zero variable costs.
2. **Latency**: API calls introduce network latency. A local model loaded into memory (Singleton pattern) computes vectors in milliseconds.
3. **Data Privacy**: Sensitive internal company documents are not transmitted to third-party providers just to be indexed. Only the final generation prompt goes to the LLM.

## Consequences
- The application requires more RAM to hold the model in memory (~90 MB).
- Encoding is a CPU-bound operation that currently blocks the asynchronous event loop during ingestion. This must be addressed in Phase 3 by introducing background workers.
