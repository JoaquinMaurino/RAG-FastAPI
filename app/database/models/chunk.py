"""
Modelo SQLAlchemy para los Chunks.
Representa la tabla 'chunks' en PostgreSQL.

¿Por qué una tabla separada y no una columna JSONB en 'documents'?
------------------------------------------------------------------
Opción A — JSONB en documents: almacenar todos los chunks como un array JSON.
    Contra: no podemos hacer queries eficientes por chunk individual.
    Contra: no podemos agregar una columna VECTOR por chunk (Step 7).
    Contra: no podemos indexar vectores individualmente.

Opción B — tabla chunks (la que usamos): cada chunk es una fila.
    Pro: cada fila puede tener su propia columna VECTOR(768) (Step 7).
    Pro: pgvector indexa y busca a nivel de fila → búsqueda semántica eficiente.
    Pro: podemos filtrar chunks por documento, por fecha, por longitud, etc.
    Pro: es el modelo estándar en todos los sistemas RAG de producción.

Relación:
    Document (1) ──────────────── (N) Chunk
    Un documento tiene muchos chunks.
    Cada chunk pertenece a exactamente un documento.
"""

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database.models.base import Base
from app.services.embedding_service import EMBEDDING_DIMENSIONS


class Chunk(Base):
    __tablename__ = "chunks"

    # Clave primaria UUID (misma decisión que en Document)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Foreign key hacia la tabla documents.
    # ondelete="CASCADE": si se elimina el documento padre,
    # PostgreSQL elimina automáticamente todos sus chunks.
    # Sin esto, borrar un Document dejaría chunks "huérfanos" en la DB.
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        # index=True: crea un índice en esta columna.
        # Lo necesitamos porque frecuentemente vamos a filtrar
        # chunks por document_id (ej: "traé todos los chunks del doc X").
        # Sin índice, esa query escanea TODA la tabla.
    )

    # El texto del chunk en sí.
    # Text = sin límite de longitud en PostgreSQL.
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Posición del chunk dentro del documento (0-indexed).
    # Útil para:
    #   - Ordenar los chunks al reconstruir el contexto para el LLM
    #   - Debug: saber de qué parte del documento viene un chunk
    #   - En el futuro: implementar "ventana deslizante" de contexto
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Longitud en caracteres del chunk.
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- Step 6 & 7: Vector de embeddings ---
    # Tipo Vector(N) es provisto por la librería pgvector para SQLAlchemy.
    # N debe coincidir con EMBEDDING_DIMENSIONS del modelo elegido (384 para MiniLM).
    #
    # nullable=True porque:
    #   - En el flujo actual generamos el embedding antes de insertar, pero
    #   - En el Step 15 (workers) el embedding se generará de forma asincrónica
    #     DESPUÉS de que el chunk ya está guardado en la DB.
    #   - Un PDF escaneado tendrá raw_text=None y por ende nunca tendrá embedding.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )

    # Timestamp de creación
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relación ORM hacia el documento padre.
    # Nos permite hacer: chunk.document → acceder al objeto Document completo.
    # lazy="selectin": cuando cargamos chunks, SQLAlchemy también carga
    # el documento automáticamente con una query separada (más eficiente
    # que JOIN para relaciones 1:1 o N:1).
    document: Mapped["Document"] = relationship(  # type: ignore[name-defined]
        "Document", back_populates="chunks"
    )
