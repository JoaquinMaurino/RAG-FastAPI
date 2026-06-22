from fastapi import APIRouter
from app.schemas.query import QueryRequest, QueryResponse
from app.agents.agent_service import run_agent

router = APIRouter(tags=["Agent"])

@router.post("/", response_model=QueryResponse)
async def chat_with_agent(request: QueryRequest):
    """
    **Endpoint de Chat con el Agente**

    Envía una pregunta al Agente de LangChain.
    El Agente decidirá qué herramientas usar (buscar documentos, contar documentos, etc)
    basado en la intención de la pregunta.
    """
    # Llama al agent_executor de LangChain
    answer = await run_agent(request.query)

    # Devolvemos un QueryResponse con results vacío, ya que el agente
    # puede haber usado diferentes tools y no siempre devuelve chunks.
    return QueryResponse(
        query=request.query,
        answer=answer,
        results=[],
    )
