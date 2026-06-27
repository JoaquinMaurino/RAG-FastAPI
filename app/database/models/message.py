"""
Modelo SQLAlchemy para los Mensajes.
Representa la tabla 'messages' en PostgreSQL.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database.models.base import Base
from app.services.embedding_service import EMBEDDING_DIMENSIONS

if TYPE_CHECKING:
    from app.database.models.conversation import Conversation


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    role: Mapped[str] = mapped_column(String, nullable=False)
    
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Vector column para similitud semántica.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relación a conversation
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )

    __table_args__ = (
        Index("idx_messages_conv_created", "conversation_id", "created_at"),
        Index(
            "idx_messages_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
