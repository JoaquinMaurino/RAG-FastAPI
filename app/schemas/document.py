"""
Esquemas Pydantic para la entidad Document.
Usados para validar los request (lo que entra) y
formatear los responses (lo que sale de la API).
"""

from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime


class DocumentResponse(BaseModel):
    """
    Schema usado para devolver la información de un documento al cliente.
    Ocultamos detalles internos y aseguramos un formato consistente.
    """
    id: UUID
    filename: str
    file_path: str | None
    # --- Step 4: incluimos el texto extraído en la respuesta ---
    # Permite verificar desde el cliente (o desde /docs) que la
    # extracción funcionó. En fases futuras podríamos omitirlo del
    # response por cuestiones de tamaño y dejarlo solo en endpoints
    # específicos (ej: GET /documents/{id}/text).
    raw_text: str | None
    created_at: datetime

    # Esta configuración le indica a Pydantic que está leyendo los datos
    # desde un objeto de SQLAlchemy (que usa atributos ej: doc.filename)
    # y no desde un diccionario (ej: doc['filename']).
    model_config = ConfigDict(from_attributes=True)
