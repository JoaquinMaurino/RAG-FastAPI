"""
Ruta HTTP para el endpoint del Agente LangChain.

El agente sigue el mismo ciclo de memoria que /chat:
    prepare_turn → run_agent → save_assistant_response → post_turn_tasks

La diferencia con /chat es que aquí no hay RAG explícito en la ruta:
el agente decide autónomamente cuándo y cómo llamar a search_documents.
"""

import uuid
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session
from app.schemas.query import QueryRequest, QueryResponse
from app.agents.agent_service import run_agent, AgentProviderError, AgentTimeoutError
from app.memory.conversation_manager import ConversationManager

router = APIRouter(tags=["Agent"])

# Instanciamos el manager a nivel router (thread-safe, sin estado mutable por request).
# Reutiliza la misma instancia para todos los requests — igual que en /chat.
memory_manager = ConversationManager()


@router.post("/", response_model=QueryResponse)
async def chat_with_agent(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """
    **Endpoint de Chat con el Agente**

    Envía una pregunta al Agente de LangChain. El agente decidirá qué
    herramientas usar (buscar documentos, contar documentos, etc.) basado
    en la intención de la pregunta.

    Si se envía un `conversation_id`, el agente retoma el hilo de esa
    conversación. Si no se envía, se crea una conversación nueva.
    El `conversation_id` se devuelve siempre en la respuesta para que
    el cliente pueda usarlo en el siguiente turno.
    """
    # --- Paso 1: Memoria — Preparar el turno ---
    # Resuelve/crea la conversación, construye el historial con la estrategia
    # activa, y persiste el mensaje del usuario.
    conv_id, chat_history = await memory_manager.prepare_turn(
        session=session,
        conversation_id=request.conversation_id,
        question=request.query,
    )

    # --- Paso 2: Ejecución del Agente ---
    try:
        answer = await run_agent(request.query, chat_history)
    except AgentProviderError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except AgentTimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(e),
        )
    except Exception:
        # Traceback ya logueado en run_agent. Nunca exponemos detalles al cliente.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocurrió un error inesperado al procesar el request.",
        )

    # --- Paso 3: Persistir la respuesta del agente ---
    await memory_manager.save_assistant_response(
        session=session,
        conversation_id=conv_id,
        response=answer,
    )

    # --- Paso 4: Tareas de post-turno en background ---
    # Corre después de devolver la respuesta HTTP (ej. actualizar resúmenes en SummaryMemory).
    background_tasks.add_task(memory_manager.post_turn_tasks, conv_id)

    return QueryResponse(
        query=request.query,
        conversation_id=conv_id,
        answer=answer,
        results=[],
    )
