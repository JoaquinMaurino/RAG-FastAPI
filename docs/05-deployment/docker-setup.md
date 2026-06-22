# Docker Setup

The application is containerized using Docker to ensure environment reproducibility across development and production.

## Architecture

Currently, the Docker configuration defines the following services in `docker-compose.yml`:
1. **api**: The FastAPI application running via Uvicorn.
2. **postgres**: A `pgvector/pgvector:pg16` image that provides PostgreSQL 16 pre-compiled with the vector extension.

*(Note: Redis and Airflow are planned for Phase 3 but are not yet implemented in the Compose file).*

## Local Development

To start the system locally:

```bash
docker-compose up --build
```

This command will:
- Pull the `pgvector` image and initialize the database.
- Build the Python image, install dependencies from `requirements.txt`.
- Start Uvicorn on port 8000 with hot-reload enabled.

Data persistence for the database is managed via Docker volumes (`postgres_data`). Uploaded files are mounted to local disk.
