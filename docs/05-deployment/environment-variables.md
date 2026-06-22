# Environment Variables

Configuration is managed using `pydantic-settings`. The application reads from a `.env` file at the root of the project.

## Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `PROJECT_NAME` | The title displayed in Swagger UI. | `RAG FastAPI` |
| `DEBUG` | Enables debug logging. | `True` |
| `DATABASE_URL` | Asyncpg connection string for PostgreSQL. | `postgresql+asyncpg://postgres:postgres@localhost:5432/rag_db` |
| `UPLOAD_DIR` | Absolute or relative path where raw PDFs are stored. | `./uploads` |
| `GEMINI_API_KEY` | Authentication key for Google Gemini API. | `AIzaSy...` |
| `GEMINI_MODEL` | The specific model string to use for generation. | `gemini-2.0-flash` |

## Pydantic Settings Validation

If any of these variables are missing (especially `DATABASE_URL` or `GEMINI_API_KEY`), Pydantic will throw a `ValidationError` at startup and prevent the application from running. This is a fail-fast mechanism to avoid runtime crashes.
