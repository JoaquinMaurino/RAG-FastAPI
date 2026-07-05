# AI Backend Engineer Study & Implementation Roadmap

## Objective

Build a production-style AI Backend application that covers the majority of technologies and concepts commonly requested for AI Backend Engineer positions.

The project will simulate an internal company knowledge assistant where users can upload documents, process them, generate embeddings, store them in a vector database, and interact with them through a conversational AI interface.

The goal is not only to learn the technologies individually, but to understand how they work together in a complete system.

---

# Final Architecture

```text
User
 │
 ▼
FastAPI
 │
 ├── Document Upload
 ├── Chat API
 └── Streaming API
 │
 ▼
Services Layer
 │
 ├── Document Processing
 ├── Embedding Generation
 ├── Retrieval
 ├── RAG
 └── Agents
 │
 ▼
PostgreSQL + pgvector
 │
 ▼
Gemini / OpenAI
```

---

# Technologies and Their Purpose

## Python

Main language used for the entire application.

Used for:

* FastAPI
* LangChain
* LlamaIndex
* Pandas
* Pytest
* Airflow
* AI integrations

---

## FastAPI

Backend framework.

Responsible for exposing:

```text
POST /documents
GET /documents
POST /chat
POST /chat/stream
```

Equivalent to Express.js in the Node ecosystem.

---

## PostgreSQL

Main database.

Stores:

* Documents
* Chunks
* Chats
* Users
* Metadata

---

## pgvector

Extension for PostgreSQL.

Allows semantic similarity search.

Stores document embeddings and enables vector search.

---

## Embeddings

Numerical representations of text.

Used to measure semantic similarity between texts.

Foundation of every RAG system.

---

## RAG (Retrieval Augmented Generation)

Technique that allows an LLM to answer questions using company documents.

Flow:

```text
Question
 ↓
Embedding
 ↓
Similarity Search
 ↓
Relevant Chunks
 ↓
LLM
 ↓
Answer
```

---

## LangChain

Orchestration framework for AI applications.

Used for:

* Chains
* Retrievers
* Agents
* Prompt Templates
* Tool Calling

---

## LlamaIndex

Framework specialized in document indexing and retrieval.

Can be integrated with LangChain.

---

## Gemini / OpenAI

Language models used to generate answers.

Initially use Gemini API because it offers a free tier and simpler onboarding.

---

## SSE (Server Sent Events)

Streaming mechanism.

Used to send generated tokens progressively to the frontend.

Typical use case:

```text
ChatGPT typing effect
```

---

## WebSockets

Bidirectional communication.

Useful for real-time applications.

Not required initially.

---

## Agents

LLMs capable of using tools.

Example:

```text
User:
How many documents are stored?

Agent:
Calls count_documents()
```

---

## Pandas

Data processing library.

Used during ETL and preprocessing.

---

## NumPy

Numerical computing library.

Provides vector operations and mathematical utilities.

---

## Scikit-Learn

Traditional Machine Learning library.

Used for:

* Classification
* Clustering
* Regression

Useful to understand AI beyond LLMs.

---

## Pytest

Testing framework.

Used for:

* Unit Tests
* Integration Tests
* End-to-End Tests

---

## Airflow

Workflow orchestration platform.

Used to automate:

```text
PDF Processing
Chunking
Embedding Generation
Data Pipelines
```

---

## Docker

Containerization platform.

Allows running the entire system locally with a reproducible environment.

---

# Project Structure

Arquitectura por capas. Cada capa tiene una responsabilidad única.

```text
app/

├── api/
│   ├── __init__.py          ← Ensambla todos los routers (api_router central)
│   └── routes/              ← Capa HTTP: solo recibe requests y delega
│       ├── documents.py
│       └── chat.py
│
├── services/                ← Lógica de negocio. Agnósticos a HTTP.
│   ├── document_service.py  ← Reutilizable por routes, agents y workers
│   ├── embedding_service.py
│   ├── rag_service.py
│   └── chat_service.py
│
├── database/
│   ├── models/              ← Equivalente a Entities en TypeORM
│   │   └── document.py
│   └── session.py           ← Engine, SessionFactory y get_session()
│
├── rag/
│   ├── chunker.py
│   ├── retriever.py
│   └── vector_store.py
│
├── agents/
│   └── assistant_agent.py
│
├── etl/
│   └── ingestion_pipeline.py
│
├── schemas/                 ← Equivalente a DTOs en NestJS (Pydantic)
│   └── document.py
│
├── tests/
│
└── main.py                  ← Entry point. Registra api_router.
```

## Flujo de una request

```text
HTTP Request
    ↓
api/routes/*.py        → Recibe, valida (Pydantic), delega
    ↓
services/*_service.py  → Lógica de negocio, queries a PostgreSQL
    ↓
database/models/*.py   → Modelo SQLAlchemy (mapea la tabla)
    ↓
PostgreSQL
```

---

# Required Local Tools

## Mandatory

### Python 3.12+

Application runtime.

### Docker

Runs infrastructure.

### PostgreSQL + pgvector

Main database and vector database.

### Gemini API Key

Primary LLM provider.

---

## Recommended Later

### Redis

For queues, caching and background jobs.

### Airflow

For ETL orchestration.

### Ollama

For local LLM experimentation.

Not required initially.

---

# Docker Services Evolution

## Phase 1

```text
api
postgres
```

---

## Phase 2

```text
api
postgres
redis
worker
```

---

## Phase 3

```text
api
postgres
redis
worker
airflow
```

---

# Implementation Roadmap

## Step 1

Create project skeleton.

Setup:

* FastAPI
* PostgreSQL
* Docker

Create a simple health endpoint.

---

## Step 2

Implement document CRUD.

Endpoints:

```text
POST /documents
GET /documents
GET /documents/{id}
DELETE /documents/{id}
```

Store metadata in PostgreSQL.

---

## Step 3

Implement PDF upload.

Store uploaded files locally.

---

## Step 4

Extract text from PDFs.

Output:

```text
PDF
 ↓
Raw Text
```

---

## Step 5

Implement chunking.

Output:

```text
Raw Text
 ↓
Chunks
```

Store chunks in database.

---

## Step 6

Generate embeddings.

Output:

```text
Chunk
 ↓
Embedding
```

Use Gemini or OpenAI embedding models.

---

## Step 7

Install pgvector.

Store embeddings inside PostgreSQL.

---

## Step 8

Implement semantic search.

Flow:

```text
Question
 ↓
Embedding
 ↓
Similarity Search
 ↓
Top K Chunks
```

---

## Step 9

Integrate Gemini.

Create a chat endpoint.

```text
POST /chat
```

---

## Step 10

Implement RAG.

Flow:

```text
Question
 ↓
Retriever
 ↓
Context
 ↓
Gemini
 ↓
Answer
```

At this stage the project already demonstrates the core AI backend concepts.

---

## Step 11

Introduce LangChain.

Replace manual orchestration with:

* Retrievers
* Prompt Templates
* Chains

---

## Step 12

Implement SSE streaming.

Endpoint:

```text
POST /chat/stream
```

Return tokens progressively.

---

## Step 13

Implement agents.

Add tools:

```text
search_documents()
count_documents()
get_document()
```

Create a simple assistant agent.

---

## Step 14

Add automated testing.

Cover:

* APIs
* Services
* RAG
* Agents

Using Pytest.

---

## Step 15

Introduce Redis.

Move heavy processing into background workers.

---

## Step 16

Introduce Airflow.

Create ingestion DAGs:

```text
Upload
 ↓
Extract
 ↓
Chunk
 ↓
Embed
 ↓
Store
```

---

## Step 17

Add observability.

Track:

* Request duration
* Embedding latency
* LLM latency
* Token usage

---

## Step 18

Add evaluation framework.

Experiment with:

* RAGAS
* DeepEval

Measure:

* Answer quality
* Retrieval quality
* Hallucinations

---

# End Goal

By completing this roadmap, the project will demonstrate practical experience with:

* FastAPI
* PostgreSQL
* pgvector
* Docker
* LangChain
* RAG
* Embeddings
* Gemini/OpenAI
* Agents
* SSE
* Redis
* Airflow
* Pytest
* ETL Pipelines
* AI Backend Architecture

The final result should resemble a real-world AI platform rather than a tutorial project.
