import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock

import uuid
from datetime import datetime

# ==============================================================================
# Testing Rutas: /documents
# ==============================================================================

@pytest.mark.asyncio
async def test_get_all_documents(client: AsyncClient):
    """
    Testea el endpoint GET /documents.
    En lugar de dejar que la ruta llame a PostgreSQL (lo cual fallaría porque
    el mock no sabe qué devolver), vamos a "parchear" (patch) la función
    document_service.get_all directamente.
    """
    # 1. Preparamos datos simulados (Mocks)
    doc_id = uuid.uuid4()
    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.filename = "informe.pdf"
    mock_doc.file_path = "/tmp/informe.pdf"
    mock_doc.raw_text = "Texto extraido"
    mock_doc.created_at = datetime.utcnow()
    
    # patch asíncrono para que devuelva nuestra lista
    with patch("app.api.routes.documents.document_service.get_all", return_value=[mock_doc]):
        
        # 2. Ejecutamos la petición HTTP simulada
        response = await client.get("/documents/")
        
        # 3. Verificamos los resultados (Assserts)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == str(doc_id)
        assert data[0]["filename"] == "informe.pdf"

@pytest.mark.asyncio
async def test_get_document_not_found(client: AsyncClient):
    """
    Verifica que al pedir un documento que no existe, retorne 404.
    """
    random_uuid = uuid.uuid4()
    
    # Parcheamos get_by_id para que devuelva None
    with patch("app.api.routes.documents.document_service.get_by_id", return_value=None):
        response = await client.get(f"/documents/{random_uuid}")
        
        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found"
