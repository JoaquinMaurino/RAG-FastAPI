"""
Modelo SQLAlchemy para los Documentos.
Representa la tabla 'documents' en PostgreSQL.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    # Import condicional para evitar imports circulares.
    # Chunk importa Document (FK), Document importa Chunk (relationship).
    # TYPE_CHECKING es False en runtime, True solo cuando mypy/pyright analiza el código.
    from app.database.models.chunk import Chunk
from sqlalchemy.dialects.postgresql import UUID

from app.database.models.base import Base


class Document(Base):
    # Nombre exacto de la tabla en PostgreSQL
    __tablename__ = "documents"

    # UUID como clave primaria. Es mejor que los IDs autoincrementales
    # enteros para sistemas distribuidos o APIs expuestas.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Nombre del archivo original que el usuario subió.
    # Guardamos el nombre original para mostrarlo al usuario,
    # aunque el archivo en disco use un nombre único (UUID).
    filename: Mapped[str] = mapped_column(String, nullable=False)

    # Ruta en disco donde está guardado el archivo.
    # Nullable porque en el futuro podría haber documentos sin archivo físico.
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Step 4: Texto extraído del PDF ---
    # Usamos Text (no String) porque Text no tiene límite de longitud
    # en PostgreSQL (equivale al tipo TEXT de SQL).
    # String en SQLAlchemy equivale a VARCHAR, que tiene un máximo configurable.
    # Un PDF de 100 páginas puede tener fácilmente 500.000+ caracteres.
    #
    # Es nullable porque:
    #   - El archivo podría ser un PDF escaneado (sin texto seleccionable)
    #   - La extracción podría fallar y queremos registrar el documento igual
    #   - En el futuro soportaremos otros formatos que tienen su propio extractor
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Fecha de creación. Se autogenera usando UTC para evitar
    # problemas de zona horaria.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relación ORM hacia los chunks de este documento.
    # cascade="all, delete-orphan": cuando borramos un Document desde Python
    # (session.delete(doc)), SQLAlchemy borra automáticamente todos sus Chunks.
    # Trabaja junto al ondelete="CASCADE" de la FK en chunk.py (que aplica
    # cuando PostgreSQL hace el DELETE directamente, sin pasar por el ORM).
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

