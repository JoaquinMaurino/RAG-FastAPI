"""
Modelo SQLAlchemy para el Resumen de la Conversación.
Representa la tabla 'conversation_summaries' en PostgreSQL.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database.models.base import Base

if TYPE_CHECKING:
    from app.database.models.conversation import Conversation


class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    
    summarized_through_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="summary"
    )
