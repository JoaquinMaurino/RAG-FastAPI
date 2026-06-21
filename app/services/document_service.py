"""
Servicio de Documentos.

Contiene toda la lógica de negocio relacionada a documentos.
Esta capa conoce SQLAlchemy y el sistema de archivos, pero NO conoce
nada de HTTP (no importa FastAPI, no maneja status codes, etc).

Puede ser invocado desde:
- api/routes/documents.py  (requests HTTP)
- agents/                  (Step 13: agentes de IA)
- workers/                 (Step 15: procesamiento en background)
- etl/                     (Step 16: pipelines de Airflow)
"""

import uuid
from pathlib import Path
from loguru import logger

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.database.models.document import Document
from app.database.models.chunk import Chunk
from app.rag.extractor import extract_text_from_pdf, ExtractionError
from app.rag.chunker import chunk_text
from app.services.embedding_service import get_embeddings_batch

async def save_upload(file: UploadFile) -> str:
    """
    Guarda el archivo en disco y devuelve la ruta donde quedó guardado.

    ¿Por qué generamos un nombre único con UUID?
    Si dos usuarios suben un archivo llamado "informe.pdf", sin UUID
    uno sobreescribiría al otro. El UUID garantiza que cada archivo
    tenga un nombre único en disco, mientras que 'filename' en la DB
    conserva el nombre original que el usuario conoce.
    """
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    # parents=True  → crea subdirectorios intermedios si hacen falta
    # exist_ok=True → no lanza error si la carpeta ya existe

    # Preservamos la extensión original (.pdf, .txt, etc.)
    suffix = Path(file.filename).suffix
    unique_filename = f"{uuid.uuid4()}{suffix}"
    file_path = upload_dir / unique_filename

    # Leemos el contenido del archivo subido y lo escribimos en disco
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    return str(file_path)


async def _save_chunks(
    session: AsyncSession,
    document_id: uuid.UUID,
    texts: list[str],
    embeddings: list[list[float]] | None = None,
) -> int:
    """
    Persiste todos los chunks de un documento en la base de datos.

    Args:
        session:     Sesión async de SQLAlchemy.
        document_id: UUID del documento al que pertenecen los chunks.
        texts:       Lista de strings, uno por chunk.
        embeddings:  Lista de vectores (uno por chunk, mismo orden que texts).
                     None si la generación de embeddings falló o no corresponde.

    Returns:
        Cantidad de chunks guardados.
    """
    chunk_objects = [
        Chunk(
            document_id=document_id,
            content=text,
            chunk_index=index,
            char_count=len(text),
            # Si tenemos embeddings los asignamos; si no, queda None (nullable).
            # zip_longest no es necesario: generamos exactamente len(texts) embeddings.
            embedding=embeddings[index] if embeddings else None,
        )
        for index, text in enumerate(texts)
    ]

    session.add_all(chunk_objects)
    return len(chunk_objects)


async def create(
    session: AsyncSession,
    file: UploadFile,
) -> Document:
    """
    Orquesta la creación de un documento:
    1. Guarda el archivo en disco
    2. Extrae el texto del PDF 
    3. Divide el texto en chunks
    4. Persiste documento + chunks en PostgreSQL

    ¿Por qué guardamos el documento ANTES de los chunks?
    Porque los chunks tienen una foreign key (document_id) que referencia
    al documento. Si intentáramos insertar chunks antes de que el documento
    exista en la DB, PostgreSQL rechazaría la inserción con un error de FK.

    El flujo es:
        INSERT INTO documents ... → obtener el ID generado
        INSERT INTO chunks (document_id=<ese ID>) ...
    """
    # --- Paso 1: Guardar archivo en disco ---
    file_path = await save_upload(file)
    logger.info(f"File saved to disk: {file_path}")

    # --- Paso 2: Extraer texto del PDF ---
    raw_text: str | None = None
    try:
        raw_text = extract_text_from_pdf(file_path)
        char_count = len(raw_text)
        logger.info(f"Text extracted successfully: {char_count} characters")
    except ExtractionError as e:
        logger.warning(f"Text extraction failed for '{file.filename}': {e}")

    # --- Paso 3: Dividir en chunks ---
    chunk_texts: list[str] = []
    if raw_text:
        chunk_texts = chunk_text(raw_text)
        logger.info(f"Text split into {len(chunk_texts)} chunks")

    # --- Paso 4: Generar embeddings ---
    # Procesamos TODOS los chunks en una sola llamada al modelo.
    # get_embeddings_batch() es ~10x más rápido que N llamadas individuales.
    embeddings: list[list[float]] | None = None
    if chunk_texts:
        try:
            embeddings = get_embeddings_batch(chunk_texts)
            logger.info(f"Generated {len(embeddings)} embeddings")
        except Exception as e:
            # Si el modelo falla (ej: memoria insuficiente), no bloqueamos el flujo.
            # Los chunks se guardarán con embedding=None y podrán reintentarse
            # en un worker asincrónico (Step 15).
            logger.warning(f"Embedding generation failed: {e}")

    # --- Paso 5: Persistir documento en PostgreSQL ---
    new_doc = Document(
        filename=file.filename,
        file_path=file_path,
        raw_text=raw_text,
    )
    session.add(new_doc)
    
    try:
        # flush() envía el INSERT a PostgreSQL sin hacer commit.
        # Nos devuelve el ID generado (UUID) que necesitamos para los chunks.
        await session.flush()
        logger.info(f"Document flushed with ID: {new_doc.id}")

        # --- Paso 6: Persistir chunks con sus embeddings ---
        if chunk_texts:
            chunk_count = await _save_chunks(session, new_doc.id, chunk_texts, embeddings)
            logger.info(f"Saved {chunk_count} chunks for document {new_doc.id}")

        # commit() hace permanentes todos los cambios de esta transacción.
        await session.commit()
        await session.refresh(new_doc)
        return new_doc
        
    except Exception as e:
        # Si cualquier operación de DB falla (ej. caracter inválido, desconexión),
        # revertimos TODOS los cambios para no dejar datos a la mitad.
        await session.rollback()
        
        # Logueamos un mensaje descriptivo en vez del stacktrace inmenso
        error_msg = str(e).split('\n')[0] # Tomamos solo la primera línea del error
        logger.error(f"Fallo al guardar en base de datos. Rollback ejecutado. Error: {error_msg}")
        
        # Levantamos un error genérico limpio para que la capa superior lo maneje
        raise RuntimeError(f"Error de base de datos al guardar '{file.filename}': {error_msg}")


async def get_all(session: AsyncSession) -> list[Document]:
    """
    Devuelve todos los documentos ordenados de más nuevo a más viejo.
    """
    stmt = select(Document).order_by(Document.created_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_by_id(session: AsyncSession, document_id: uuid.UUID) -> Document | None:
    """
    Busca un documento por su UUID.
    Devuelve None si no existe (la route decide qué error HTTP lanzar).
    """
    return await session.get(Document, document_id)


async def delete(session: AsyncSession, document_id: uuid.UUID) -> bool:
    """
    Elimina un documento de la base de datos.
    Nota: no elimina el archivo en disco (lo haremos en un step posterior).
    Devuelve True si se eliminó, False si no existía.
    """
    doc = await session.get(Document, document_id)
    if not doc:
        return False
    await session.delete(doc)
    await session.commit()
    return True
