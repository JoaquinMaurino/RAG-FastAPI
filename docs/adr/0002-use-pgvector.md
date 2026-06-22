# ADR 0002: Use PostgreSQL with pgvector

**Date:** 2026-06-22  
**Status:** Accepted

## Context
A Retrieval-Augmented Generation (RAG) system requires a vector database to perform semantic similarity searches (Cosine Similarity, L2 distance) on text embeddings. 

## Considered Options
* Pinecone (Managed SaaS)
* Milvus / Qdrant (Dedicated Vector DBs)
* PostgreSQL + pgvector extension

## Decision
We chose **PostgreSQL + pgvector**.

## Rationale
1. **Operational Simplicity**: We already need a relational database to store users, document metadata, and chat history. Adding `pgvector` allows us to store vectors in the same database, eliminating the need to deploy and monitor a separate service.
2. **ACID Compliance**: By storing chunks and vectors in the same transaction as the document metadata, we prevent "split-brain" scenarios where a document is deleted from Postgres but its vectors remain orphaned in a separate vector DB.
3. **Cost**: Running `pgvector` locally via Docker is free, avoiding SaaS subscription costs for early-stage development.

## Consequences
- `pgvector` may not scale as efficiently as dedicated vector databases (like Milvus) when dealing with tens of millions of high-dimensional vectors, though this limit is far beyond our current scope.
