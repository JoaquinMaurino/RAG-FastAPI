"""
Estrategia de memoria: Ventana Deslizante (Sliding Window).

Devuelve los últimos N mensajes de la conversación, respetando
el presupuesto de tokens definido en la sección 6 del plan.

Regla de recorte: si los últimos N mensajes exceden max_tokens,
se eliminan los MÁS ANTIGUOS primero hasta que el contexto entre
en presupuesto, incluso si eso significa devolver menos de N mensajes.
"""

from uuid import UUID

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.models.message import Message
from app.memory.interface import MemoryStrategy
from app.memory.tokens import approx_tokens


class SlidingWindowMemory(MemoryStrategy):
    """
    Estrategia de ventana deslizante.

    Carga los últimos `window_size` mensajes de la conversación y los
    filtra por presupuesto de tokens (max_tokens) descartando los más
    antiguos primero.

    Args:
        window_size: Número máximo de mensajes a recuperar de la DB.
                     Configurado desde settings.memory_sliding_window_size.
    """

    def __init__(self, window_size: int | None = None):
        self.window_size = window_size if window_size is not None else settings.memory_sliding_window_size

    async def build_context(
        self,
        session: AsyncSession,
        conversation_id: UUID,
        current_question: str,
        max_tokens: int,
    ) -> list[BaseMessage]:
        """
        Devuelve hasta `window_size` mensajes anteriores de la conversación,
        ordenados del más antiguo al más reciente, dentro del presupuesto de tokens.

        Nunca incluye `current_question`. El caller lo agrega por separado.
        """
        try:
            # Recuperamos los últimos window_size mensajes de la DB.
            # La subconsulta ordena DESC para tomar los más recientes,
            # luego la consulta externa los invierte a ASC (oldest-first).
            subq = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(self.window_size)
                .subquery()
            )

            stmt = (
                select(Message)
                .select_from(subq)
                .join(Message, Message.id == subq.c.id)
                .order_by(Message.created_at.asc())
            )

            result = await session.execute(stmt)
            messages: list[Message] = list(result.scalars().all())

            if not messages:
                return []

            # Convertimos a LangChain BaseMessage
            lc_messages: list[BaseMessage] = [
                _to_langchain_message(m) for m in messages
            ]

            # Aplicamos el presupuesto de tokens (sección 6 del plan):
            # si el total excede max_tokens, descartamos los más antiguos primero.
            lc_messages = _apply_token_budget(lc_messages, max_tokens)

            logger.debug(
                f"SlidingWindowMemory: conv={conversation_id}, "
                f"window_size={self.window_size}, returned={len(lc_messages)} msgs"
            )
            return lc_messages

        except Exception as e:
            logger.error(
                f"SlidingWindowMemory.build_context failed for conv {conversation_id}: {e}"
            )
            return []


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _to_langchain_message(msg: Message) -> BaseMessage:
    """Convierte un ORM Message en el tipo de mensaje LangChain correcto."""
    if msg.role == "user":
        return HumanMessage(content=msg.content, additional_kwargs={"msg_id": str(msg.id)})
    if msg.role == "assistant":
        return AIMessage(content=msg.content, additional_kwargs={"msg_id": str(msg.id)})
    # role == "system" u otro futuro — devolvemos AIMessage como fallback seguro
    return AIMessage(content=msg.content, additional_kwargs={"msg_id": str(msg.id)})


def _apply_token_budget(
    messages: list[BaseMessage],
    max_tokens: int,
) -> list[BaseMessage]:
    """
    Recorta la lista de mensajes (oldest-first) para que el costo total
    de tokens no supere max_tokens. Elimina desde el principio (los más antiguos).

    Returns:
        La lista recortada, manteniendo el orden oldest-first.
    """
    total = sum(approx_tokens(m.content) for m in messages)

    while messages and total > max_tokens:
        removed = messages.pop(0)  # el más antiguo (índice 0)
        total -= approx_tokens(removed.content)

    return messages
