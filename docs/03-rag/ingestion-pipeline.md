# Document Ingestion Pipeline

The document ingestion pipeline is responsible for taking a raw PDF file, extracting its text, breaking it into semantic chunks, and persisting it to the database. 

## Flow Overview

1. **File Save**: The uploaded file is given a unique UUID to prevent naming collisions and saved to the local file system.
2. **Extraction (`app/rag/extractor.py`)**: The PDF is parsed using `PyMuPDF` (`fitz`). PyMuPDF was chosen over PyPDF2 due to its C-based engine, which offers superior speed and better handling of multi-column layouts. The extractor injects a "--- Page N ---" marker to preserve pagination semantics.
3. **Chunking (`app/rag/chunker.py`)**: The raw text is passed to a custom Recursive Character Text Splitter.
4. **Embedding Generation**: The chunks are embedded in batches.
5. **Persistence**: The parent Document is inserted into PostgreSQL to generate its UUID. The chunks, along with their high-dimensional vector representations, are then inserted with foreign keys linking back to the parent Document.

## The Recursive Character Chunker

To ensure context is not lost mid-sentence, the chunker uses a recursive fallback strategy:

1. Attempt to split by `\n\n` (Paragraphs).
2. If a paragraph is larger than the `chunk_size` limit (default 1000 chars), fall back to `\n` (Lines).
3. If still too large, fall back to `. ` (Sentences).
4. If still too large, fall back to ` ` (Words).
5. If still too large, fall back to empty string `""` (Characters).

**Overlap Strategy**: To prevent semantic context from being severed at the boundary of two chunks, the chunker enforces a `chunk_overlap` (default 200 chars). The end of Chunk N is duplicated at the start of Chunk N+1.

## Diagram

See the [Document Ingestion Diagram](../diagrams/document-ingestion.mermaid) for a visual representation.
