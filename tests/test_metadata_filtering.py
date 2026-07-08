import uuid
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_search_with_metadata_filter_valid_doc(
    test_client: AsyncClient, test_document_with_chunks, mock_llm_service
):
    """
    Verifica que al buscar con un document_id válido,
    solo se devuelvan chunks de ese documento.
    """
    doc_id = test_document_with_chunks.id

    response = await test_client.post(
        "/api/v1/search/",
        json={"query": "test", "document_id": str(doc_id), "limit": 5},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) > 0
    
    for result in data["results"]:
        assert result["document_id"] == str(doc_id)

@pytest.mark.asyncio
async def test_search_with_metadata_filter_invalid_doc(
    test_client: AsyncClient, test_document_with_chunks, mock_llm_service
):
    """
    Verifica que al buscar con un document_id que no tiene nada que ver,
    se devuelva una lista vacía.
    """
    random_id = str(uuid.uuid4())

    response = await test_client.post(
        "/api/v1/search/",
        json={"query": "test", "document_id": random_id, "limit": 5},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 0

@pytest.mark.asyncio
async def test_search_without_filters(
    test_client: AsyncClient, test_document_with_chunks, mock_llm_service
):
    """
    Verifica que sin filtros, funciona normal.
    """
    response = await test_client.post(
        "/api/v1/search/",
        json={"query": "test", "limit": 5},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) > 0
