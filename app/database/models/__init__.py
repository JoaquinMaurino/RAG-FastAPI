"""
Módulo de modelos de base de datos.
Exportamos todos los modelos acá para que:
1. Sean fáciles de importar en otros archivos.
2. SQLAlchemy pueda descubrirlos fácilmente cuando llame a Base.metadata.create_all()
"""

from app.database.models.base import Base
from app.database.models.document import Document
from app.database.models.chunk import Chunk

__all__ = ["Base", "Document", "Chunk"]
