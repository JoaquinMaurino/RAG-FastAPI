# System Context (C4 Model)

The System Context diagram provides a high-level view of how the Knowledge Assistant interacts with its users and external dependencies.

```mermaid
%%{init: {'theme': 'default'}}%%
{{ include: ../diagrams/c4-context.mermaid }}
```

*(Note: If the include macro does not render, please view the raw Mermaid file in `docs/diagrams/c4-context.mermaid`)*

## Actors and Systems

1. **Company Employee (User)**: The primary actor interacting with the system. They send queries and upload documents. Currently, this interaction is done via API clients (like `curl` or Postman).
2. **Knowledge Assistant System**: The RAG FastAPI application being documented. It serves as the bridge between the user's files and the intelligent query interface.
3. **Google Gemini API**: The external Large Language Model provider used for natural language understanding and generation.
