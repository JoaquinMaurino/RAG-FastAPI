"""
Orquestador principal de la memoria conversacional.
"""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from langchain_core.messages import BaseMessage
from loguru import logger

from app.core.config import settings
from app.database.models.conversation import Conversation
from app.database.models.message import Message
from app.memory.interface import MemoryStrategy
from app.memory.strategies.none import NoMemory


class ConversationManager:
    """
    Gestiona el ciclo de vida de las conversaciones y delega
    la construcción del contexto a la estrategia activa.
    Es el ÚNICO componente que conoce la estrategia concreta configurada.
    """

    def __init__(self):
        # Resolvemos la estrategia a utilizar en base a la configuración.
        # Por ahora solo tenemos 'none'. En futuras fases agregaremos las demás.
        self.strategy: MemoryStrategy
        if settings.memory_strategy == "none":
            self.strategy = NoMemory()
        else:
            # Fallback seguro por ahora, aunque Pydantic ya validó el string.
            logger.warning(f"Strategy '{settings.memory_strategy}' not yet fully implemented. Falling back to NoMemory.")
            self.strategy = NoMemory()

    async def prepare_turn(
        self,
        session: AsyncSession,
        conversation_id: UUID | None,
        question: str,
    ) -> tuple[UUID, list[BaseMessage]]:
        """
        Prepara el contexto para un nuevo turno de chat.
        
        1. Resuelve la conversación (la crea si no existe).
        2. Obtiene el contexto de memoria usando la estrategia activa.
        3. Persiste el mensaje del usuario en la base de datos (sin commit, se hace luego).
        
        Returns:
            Una tupla con (conversation_id_definitivo, contexto_del_llm)
        """
        # 1. Crear o recuperar conversación
        if not conversation_id:
            conv = Conversation()
            session.add(conv)
            await session.flush()  # Flush para obtener el ID sin commitear aún
            conversation_id = conv.id
            logger.info(f"Created new conversation: {conversation_id}")
        else:
            # Validamos que exista
            stmt = select(Conversation).where(Conversation.id == conversation_id)
            result = await session.execute(stmt)
            if not result.scalar_one_or_none():
                # Si nos pasan un ID fantasma, creamos uno nuevo transparente
                conv = Conversation(id=conversation_id)
                session.add(conv)
                await session.flush()
                logger.info(f"Created missing conversation with provided ID: {conversation_id}")

        # 2. Construir contexto con la estrategia (con manejo de fallos gracefully)
        try:
            context = await self.strategy.build_context(
                session=session,
                conversation_id=conversation_id,
                current_question=question,
                max_tokens=settings.memory_max_context_tokens,
            )
        except Exception as e:
            logger.error(f"Memory strategy '{settings.memory_strategy}' failed for conv {conversation_id}: {e}")
            context = []  # Fallback gracefully a "sin memoria"

        # 3. Guardar el mensaje del usuario
        # Ojo: en la Fase 2 aquí inyectaremos el cálculo del vector (embedding).
        user_msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=question,
        )
        session.add(user_msg)
        await session.flush()

        return conversation_id, context

    async def save_assistant_response(
        self,
        session: AsyncSession,
        conversation_id: UUID,
        response: str,
    ) -> None:
        """
        Guarda la respuesta final del asistente.
        """
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=response,
        )
        session.add(assistant_msg)
        # Commit para persistir el turno entero (conv + user_msg + assistant_msg)
        await session.commit()
