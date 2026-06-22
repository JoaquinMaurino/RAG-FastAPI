# Container Architecture (C4 Model)

The Container diagram zooms into the Knowledge Assistant System boundary to reveal its primary execution units and data stores.

```mermaid
%%{init: {'theme': 'default'}}%%
{{ include: ../diagrams/c4-container.mermaid }}
```

*(Note: If the include macro does not render, please view the raw Mermaid file in `docs/diagrams/c4-container.mermaid`)*

## Containers

1. **FastAPI Application**: The core backend running on Python 3.12+. It is responsible for all business logic, coordination, and exposing the HTTP REST interface.
2. **PostgreSQL Database**: Powered by the `pgvector` extension. It handles the persistence of document metadata, chunk text, and high-dimensional vector embeddings, allowing for efficient semantic search.
3. **File System**: Local storage used to persist the raw `.pdf` files uploaded by users.
