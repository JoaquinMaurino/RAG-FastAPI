# Future Improvements

Based on the architectural roadmap and known limitations, the following evolutions are planned for the system.

## Phase 3: Background Workers (Step 15)
To solve the synchronous bottlenecks during PDF ingestion, we will introduce **Redis** and **Celery** (or RQ/ARQ).
- The `POST /documents` endpoint will save the file to disk and immediately return a `202 Accepted` with a `task_id`.
- A background worker process will pick up the task, run extraction, chunking, and embedding generation without blocking the main API.

## Phase 4: Data Pipelines (Step 16)
Introduction of **Apache Airflow** for orchestrating complex ingestion DAGs (Directed Acyclic Graphs). This allows us to schedule nightly syncs from external sources (e.g., SharePoint, Confluence) rather than relying solely on manual file uploads.

## Phase 5: Observability (Step 17)
Currently, `loguru` handles basic logging. We need telemetry:
- **Tracing**: OpenTelemetry or LangSmith to trace the execution path of LangChain Agents and measure LLM latency/token usage.
- **Metrics**: Prometheus + Grafana to monitor API request rates, database pool usage, and error rates.

## Phase 6: Evaluation Framework (Step 18)
Implementing tools like **RAGAS** or **DeepEval** to programmatically measure:
- Answer quality and relevance.
- Retrieval precision and recall.
- Hallucination rates.
