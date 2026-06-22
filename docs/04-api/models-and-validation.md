# Request Models and Validation

FastAPI relies on Pydantic to ensure all incoming payloads are strictly validated before hitting the service layer.

## Schemas (`app/schemas/`)

### `DocumentResponse`
Used to serialize the SQLAlchemy `Document` model into a safe JSON response.
```python
class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    created_at: datetime
```

### `QueryRequest`
Used in `/search`, `/chat`, and `/agent` endpoints.
```python
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, description="La consulta del usuario")
    limit: int = Field(default=5, ge=1, le=20, description="Cantidad máxima de chunks a recuperar")
```
**Validation Rules**:
- `query` must be at least 3 characters.
- `limit` must be between 1 and 20. If not provided, it defaults to 5.

### `ChunkResult`
Represents a piece of text matched during semantic search.
```python
class ChunkResult(BaseModel):
    document_filename: str
    content: str
    similarity_score: float | None = None
```

### `QueryResponse`
Used for structured API responses.
```python
class QueryResponse(BaseModel):
    query: str
    answer: str | None = None
    results: list[ChunkResult]
```

## Global Error Handling

Exceptions raised in the service layer are caught at the router level or by FastAPI exception handlers.
- `ExtractionError` (from PyMuPDF) is caught and transformed into a user-friendly HTTP `422 Unprocessable Entity` to prevent raw stack traces from reaching the client.
- Standard Pydantic validation errors return HTTP `422`.
