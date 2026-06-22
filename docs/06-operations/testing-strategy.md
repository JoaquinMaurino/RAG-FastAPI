# Testing Strategy

Testing an asynchronous FastAPI application that heavily relies on database connections and third-party LLM APIs requires a robust isolation strategy. The chosen framework is `pytest` with `pytest-asyncio`.

## Core Principles

1. **Isolation from External Costs**: Tests must NEVER call the actual Google Gemini API. This prevents monetary costs during CI/CD runs and avoids flaky tests caused by LLM latency or unpredictable text generation.
2. **Database Mocking for Unit Tests**: Setting up an isolated PostgreSQL database is required for integration testing. However, for unit testing API routers, we use `unittest.mock.AsyncMock` to bypass the database entirely.

## Pytest Configuration

- `pytest.ini` is configured with `asyncio_mode = auto` to automatically handle `async def test_*` functions.
- `tests/conftest.py` sets up the global fixtures.

## Key Fixtures

### `override_get_session`
We use FastAPI's `app.dependency_overrides` to swap the real database connection generator (`get_session`) with a mock generator. 

### `client`
An `httpx.AsyncClient` bound to the ASGI app (`ASGITransport(app=app)`). This allows us to make HTTP requests against the FastAPI routers without actually starting a network server via Uvicorn.

## Examples of Mocking
In `tests/api/test_chat_agent.py`, we patch the LangChain agent execution:
```python
with patch("app.api.routes.agent.run_agent", return_value="There are 3 documents."):
    response = await client.post("/agent/", json=query_payload)
```
This forces the agent service to immediately return the hardcoded string, allowing us to test the router's JSON serialization and status codes in isolation.
