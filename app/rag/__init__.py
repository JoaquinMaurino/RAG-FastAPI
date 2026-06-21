# Paquete rag/
# Contiene todo el pipeline de procesamiento de documentos:
#   extractor.py   ← Step 4: PDF → Raw Text       (actual)
#   chunker.py     ← Step 5: Raw Text → Chunks    (próximo)
#   vector_store.py← Step 7: Chunks → pgvector    (futuro)
#   retriever.py   ← Step 8: Query → Top-K Chunks (futuro)
