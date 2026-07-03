"""
Estrategia de memoria: Búsqueda Vectorial (Vector Memory).

Utiliza pgvector para encontrar turnos anteriores de la misma conversación
que sean semánticamente similares a la pregunta actual.
"""

import asyncio
from uuid import UUID

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.models.message import Message
from app.memory.interface import MemoryStrategy
from app.memory.tokens import approx_tokens
from app.services.embedding_service import get_embedding


class VectorMemory(MemoryStrategy):
    """
    Estrategia de memoria basada en similitud semántica.

    Busca los top_k mensajes del usuario más parecidos a la pregunta actual,
    y recupera sus respectivas respuestas del asistente.
    
    Limitación conocida:
    La búsqueda por similitud pura no tiene noción de recencia. Un mensaje muy antiguo
    pero textualmente similar superará a un mensaje de hace 5 minutos que sea
    ligeramente menos similar.
    """

    def __init__(self, top_k: int | None = None):
        self.top_k = top_k if top_k is not None else settings.memory_vector_top_k

    async def build_context(
        self,
        session: AsyncSession,
        conversation_id: UUID,
        current_question: str,
        max_tokens: int,
    ) -> list[BaseMessage]:
        try:
            # 1. Embeber la pregunta actual (en thread separado por ser CPU bound)
            question_embedding = await asyncio.to_thread(get_embedding, current_question)

            # 2. Buscar los top_k mensajes del usuario más similares en esta conversación
            # Usamos vector_cosine_ops (<=>) provisto por pgvector
            stmt_user_msgs = (
                select(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.role == "user",
                    Message.embedding.is_not(None)
                )
                .order_by(Message.embedding.cosine_distance(question_embedding))
                .limit(self.top_k)
            )
            
            result_user = await session.execute(stmt_user_msgs)
            similar_user_msgs = result_user.scalars().all()

            if not similar_user_msgs:
                return []

            # 3. Para cada mensaje del usuario, buscar la respuesta del asistente
            # que ocurrió inmediatamente después.
            # Ordenamos los pares cronológicamente para que LangChain reciba el
            # contexto en un orden temporal lógico, aunque hayan sido recuperados por semántica.
            similar_user_msgs = sorted(similar_user_msgs, key=lambda m: m.created_at)
            
            lc_messages: list[BaseMessage] = []
            
            for user_msg in similar_user_msgs:
                # Buscamos el primer mensaje del asistente posterior a este mensaje del usuario
                stmt_assistant = (
                    select(Message)
                    .where(
                        Message.conversation_id == conversation_id,
                        Message.role == "assistant",
                        Message.created_at > user_msg.created_at
                    )
                    .order_by(Message.created_at.asc())
                    .limit(1)
                )
                res_ast = await session.execute(stmt_assistant)
                ast_msg = res_ast.scalar_one_or_none()

                lc_messages.append(HumanMessage(content=user_msg.content, additional_kwargs={"msg_id": str(user_msg.id)}))
                if ast_msg:
                    lc_messages.append(AIMessage(content=ast_msg.content, additional_kwargs={"msg_id": str(ast_msg.id)}))

            # 4. Aplicar presupuesto de tokens
            lc_messages = _apply_token_budget(lc_messages, max_tokens)

            logger.debug(
                f"VectorMemory: conv={conversation_id}, top_k={self.top_k}, "
                f"returned={len(lc_messages)} msgs"
            )
            return lc_messages

        except Exception as e:
            logger.error(
                f"VectorMemory.build_context failed for conv {conversation_id}: {e}"
            )
            return []


def _apply_token_budget(
    messages: list[BaseMessage],
    max_tokens: int,
) -> list[BaseMessage]:
    """
    Recorta la lista descartando los pares más antiguos si se excede el presupuesto.
    """
    total = sum(approx_tokens(m.content) for m in messages)

    while messages and total > max_tokens:
        removed = messages.pop(0)
        total -= approx_tokens(removed.content)

    return messages
