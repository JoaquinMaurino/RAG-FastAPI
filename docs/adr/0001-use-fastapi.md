# ADR 0001: Use FastAPI for the Backend Framework

**Date:** 2026-06-22  
**Status:** Accepted

## Context
We need a robust, scalable backend framework for the Python ecosystem to handle the API layer. The framework must efficiently handle asynchronous IO bounds, particularly for streaming LLM responses and managing database connection pools.

## Considered Options
* Django
* Flask
* FastAPI

## Decision
We chose **FastAPI**.

## Rationale
1. **Native Async Support**: Essential for SSE (Server-Sent Events) streaming, which we use to pipe tokens from Google Gemini to the client in real-time.
2. **Pydantic Validation**: Automatic payload validation and serialization drastically reduces boilerplate code.
3. **Speed**: Built on Starlette, it is one of the fastest Python frameworks available.
4. **Auto-Documentation**: Built-in Swagger UI simplifies testing during development.

## Consequences
- Requires developers to understand `async`/`await` paradigms in Python.
- SQLAlchemy usage must be adapted to `async_sessionmaker` and `asyncpg`, which is slightly more complex than synchronous ORM usage.
