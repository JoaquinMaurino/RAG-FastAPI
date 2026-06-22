import pytest
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator
from unittest.mock import AsyncMock

from app.main import app
from app.database.session import get_session

# ==============================================================================
# Fixtures de Base de Datos (Mocks)
# ==============================================================================

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """
    Crea un mock asíncrono que simula ser una AsyncSession de SQLAlchemy.
    Cualquier método que llame FastAPI (ej: session.execute) será interceptado
    por este mock sin tocar la base de datos real.
    """
    return AsyncMock()

@pytest.fixture(autouse=True)
def override_get_session(mock_db_session: AsyncMock) -> None:
    """
    Este fixture se ejecuta automáticamente (autouse=True) antes de cada test.
    Le dice a FastAPI: "Si alguien pide Depends(get_session), entregale
    nuestro mock_db_session en lugar de la conexión real".
    """
    async def _get_mock_session():
        yield mock_db_session

    app.dependency_overrides[get_session] = _get_mock_session
    yield
    # Limpieza después del test
    app.dependency_overrides.clear()

# ==============================================================================
# Fixtures HTTP (Cliente FastAPI)
# ==============================================================================

@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Provee un cliente HTTP asíncrono conectado directamente a nuestra app FastAPI.
    Esto permite simular peticiones HTTP sin necesidad de levantar el puerto 8000
    con uvicorn. El ASGITransport hace puente directo entre httpx y FastAPI.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver"
    ) as ac:
        yield ac
