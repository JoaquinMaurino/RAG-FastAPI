import pytest
from httpx import AsyncClient
from unittest.mock import patch

# ==============================================================================
# Testing Rutas: /agent
# ==============================================================================

@pytest.mark.asyncio
async def test_chat_with_agent(client: AsyncClient):
    """
    Verifica que el endpoint /agent/ reciba el request, invoque al Agente
    y estructure el QueryResponse correctamente.
    Mockeamos run_agent para NO pegarle a la API de Gemini (que cuesta plata y tiempo).
    """
    
    query_payload = {
        "query": "How many documents do we have?",
        "limit": 5
    }
    
    # run_agent es una corrutina (async def), así que usamos patch y le decimos
    # que cuando se la llame, devuelva una respuesta instantánea.
    with patch("app.api.routes.agent.run_agent", return_value="There are 3 documents."):
        
        response = await client.post("/agent/", json=query_payload)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["query"] == "How many documents do we have?"
        assert data["answer"] == "There are 3 documents."
        assert data["results"] == [] # El agente devuelve results vacíos por diseño
