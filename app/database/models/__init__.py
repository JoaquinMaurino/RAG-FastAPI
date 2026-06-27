"""
Módulo de modelos de base de datos.
Exportamos todos los modelos acá para que:
1. Sean fáciles de importar en otros archivos.
2. SQLAlchemy pueda descubrirlos fácilmente cuando llame a Base.metadata.create_all()
"""

from app.database.models.base import Base
from app.database.models.document import Document
from app.database.models.chunk import Chunk

from app.database.models.conversation import Conversation
from app.database.models.message import Message
from app.database.models.conversation_summary import ConversationSummary

__all__ = ["Base", "Document", "Chunk", "Conversation", "Message", "ConversationSummary"]
