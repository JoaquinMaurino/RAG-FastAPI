# Known Limitations & Technical Debt

This document outlines the current limitations of the RAG FastAPI platform. Addressing these is critical before declaring the system production-ready for a large user base.

## 1. Synchronous Bottlenecks
- **Embedding Generation**: The `sentence-transformers` `.encode()` method is CPU-bound. Calling it directly inside the `document_service.py` blocks the FastAPI asynchronous event loop. If 10 users upload PDFs simultaneously, the API will become unresponsive until the math operations finish.
- **Extraction**: `fitz` (PyMuPDF) text extraction is also a blocking operation.

## 2. Missing Authentication & Authorization
- There is currently no `OAuth2` or JWT authentication. All endpoints are public.
- There is no Tenant or User isolation. Every user can search and chat with every document uploaded to the system.

## 3. Reliability of Long-running Tasks
- If a user uploads a 500-page PDF, the HTTP request might timeout before extraction and embedding finish.
- There is no retry mechanism if the database connection drops mid-ingestion.

## 4. Basic Chunking
- The recursive character chunker relies purely on punctuation. It does not understand tables, markdown structure, or document layout (headers vs. body).

## 5. Security Concerns
- PDFs are saved to local disk. There is no malware scanning mechanism implemented on upload.
- `Path` traversal mitigations rely on UUID generation, but explicit input sanitization on filenames is limited.
