"""
Rutas HTTP para el recurso Documentos.

Esta capa es delgada (thin controller):
- Recibe el request HTTP
- Valida los datos de entrada
- Delega la lógica al service correspondiente
- Convierte el resultado en una respuesta HTTP

NO hace queries a la base de datos directamente.
NO contiene lógica de negocio.
"""

from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.services import document_service
from app.schemas.document import DocumentResponse

router = APIRouter(tags=["Documents"])


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    # UploadFile es el tipo de FastAPI para archivos subidos.
    # File(...) indica que es obligatorio.
    # FastAPI automáticamente maneja multipart/form-data.
    session: AsyncSession = Depends(get_session),
):
    """
    Sube un documento (PDF u otro archivo) al servidor.
    Guarda el archivo en disco y registra sus metadatos en la base de datos.
    """
    try:
        return await document_service.create(session, file)
    except RuntimeError as e:
        # Atrapamos el error limpio que lanzamos desde el service
        # y se lo devolvemos al usuario (o Swagger UI) como un HTTP 500
        # sin ensuciar la consola con un traceback gigante.
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[DocumentResponse])
async def get_documents(
    session: AsyncSession = Depends(get_session),
):
    """Lista todos los documentos."""
    return await document_service.get_all(session)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Devuelve un documento específico por su ID."""
    doc = await document_service.get_by_id(session, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Elimina un documento por su ID."""
    deleted = await document_service.delete(session, document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return None
