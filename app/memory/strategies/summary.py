"""
Estrategia de memoria: Resumen Incremental (Summary Memory).

Mantiene un resumen compacto de toda la conversación para conservar
el hilo global sin exceder el presupuesto de tokens. Genera resúmenes
nuevos de forma asíncrona cuando se acumulan N mensajes nuevos.
"""

from uuid import UUID

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.services.llm_factory import get_llm
from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.models.message import Message
from app.database.models.conversation_summary import ConversationSummary
from app.memory.interface import MemoryStrategy
from app.memory.tokens import approx_tokens


# ── Chain de Resumen (LLM) ───────────────────────────────────────────────────
# Temperatura 0.0 para resúmenes: fácticos y consistentes, sin creatividad.
_summary_llm = get_llm(temperature=0.0)

_summary_prompt = PromptTemplate.from_template(
    "Sos un asistente encargado de comprimir el contexto de una conversación.\n"
    "Tu objetivo es fusionar un resumen existente con los mensajes más recientes "
    "para crear un NUEVO resumen actualizado y muy conciso.\n"
    "Ignorá las interacciones irrelevantes (ej. saludos) y mantené los datos duros, "
    "preferencias del usuario, e ideas principales.\n\n"
    "RESUMEN ANTERIOR:\n{previous_summary}\n\n"
    "NUEVOS MENSAJES A INTEGRAR:\n{new_messages}\n\n"
    "NUEVO RESUMEN:"
)

_summary_chain = _summary_prompt | _summary_llm | StrOutputParser()


class SummaryMemory(MemoryStrategy):
    """
    Memoria de resumen incremental.
    """

    def __init__(
        self,
        threshold: int | None = None,
    ):
        self.threshold = threshold if threshold is not None else settings.memory_summary_threshold

    async def build_context(
        self,
        session: AsyncSession,
        conversation_id: UUID,
        current_question: str,
        max_tokens: int,
    ) -> list[BaseMessage]:
        """
        Devuelve el SystemMessage con el resumen actual + los mensajes recientes
        crudos que aún no fueron resumidos.
        """
        try:
            # 1. Recuperar resumen actual
            stmt_sum = select(ConversationSummary).where(ConversationSummary.conversation_id == conversation_id)
            res_sum = await session.execute(stmt_sum)
            summary_obj = res_sum.scalar_one_or_none()

            # 2. Recuperar mensajes desde el último resumido
            stmt_msgs = select(Message).where(Message.conversation_id == conversation_id)
            
            if summary_obj and summary_obj.summarized_through_message_id:
                # Buscamos la fecha del último mensaje resumido para traer los posteriores
                stmt_last_msg = select(Message.created_at).where(Message.id == summary_obj.summarized_through_message_id)
                last_msg_date = await session.scalar(stmt_last_msg)
                
                if last_msg_date:
                    stmt_msgs = stmt_msgs.where(Message.created_at > last_msg_date)
            
            stmt_msgs = stmt_msgs.order_by(Message.created_at.asc())
            unsummarized_msgs = (await session.execute(stmt_msgs)).scalars().all()

            # 3. Construir lista final
            lc_messages: list[BaseMessage] = []
            
            if summary_obj and summary_obj.summary:
                lc_messages.append(SystemMessage(content=f"Resumen de la conversación hasta ahora:\n{summary_obj.summary}"))
                
            for msg in unsummarized_msgs:
                if msg.role == "user":
                    lc_messages.append(HumanMessage(content=msg.content, additional_kwargs={"msg_id": str(msg.id)}))
                elif msg.role == "assistant":
                    lc_messages.append(AIMessage(content=msg.content, additional_kwargs={"msg_id": str(msg.id)}))

            # 4. Trimear por presupuesto si es necesario
            # Regla de oro: el resumen JAMÁS se elimina. Se recortan los mensajes crudos más viejos.
            lc_messages = self._apply_budget_protecting_summary(lc_messages, max_tokens)

            logger.debug(
                f"SummaryMemory: conv={conversation_id}, summary_exists={bool(summary_obj)}, "
                f"unsummarized={len(unsummarized_msgs)}"
            )
            return lc_messages

        except Exception as e:
            logger.error(f"SummaryMemory.build_context failed for conv {conversation_id}: {e}")
            return []

    async def run_background_tasks(self, session: AsyncSession, conversation_id: UUID) -> None:
        """
        Llamado asíncronamente después del request para actualizar el resumen
        si se superó el threshold.
        """
        try:
            # Recuperar resumen actual
            stmt_sum = select(ConversationSummary).where(ConversationSummary.conversation_id == conversation_id)
            summary_obj = (await session.execute(stmt_sum)).scalar_one_or_none()

            # Contar mensajes no resumidos
            stmt_count = select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
            stmt_msgs = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())

            if summary_obj and summary_obj.summarized_through_message_id:
                stmt_last_msg = select(Message.created_at).where(Message.id == summary_obj.summarized_through_message_id)
                last_msg_date = await session.scalar(stmt_last_msg)
                if last_msg_date:
                    stmt_count = stmt_count.where(Message.created_at > last_msg_date)
                    stmt_msgs = stmt_msgs.where(Message.created_at > last_msg_date)

            unsummarized_count = await session.scalar(stmt_count)

            if unsummarized_count < self.threshold:
                return  # Aún no hay suficientes mensajes para justificar un resumen

            # Momento de resumir
            logger.info(f"Threshold reached ({unsummarized_count} >= {self.threshold}) for conv {conversation_id}. Summarizing...")
            
            unsummarized_msgs = (await session.execute(stmt_msgs)).scalars().all()
            if not unsummarized_msgs:
                return

            last_msg_id = unsummarized_msgs[-1].id
            
            # Formatear el texto de los nuevos mensajes para el LLM
            new_msgs_text = "\n".join([f"{m.role}: {m.content}" for m in unsummarized_msgs])
            previous_summary = summary_obj.summary if summary_obj else "No hay resumen anterior. Esta es la primera iteración."

            # Llamada al LLM
            new_summary = await _summary_chain.ainvoke({
                "previous_summary": previous_summary,
                "new_messages": new_msgs_text
            })

            # Guardar el resultado
            if not summary_obj:
                summary_obj = ConversationSummary(conversation_id=conversation_id)
                session.add(summary_obj)
                
            summary_obj.summary = new_summary
            summary_obj.summarized_through_message_id = last_msg_id
            
            await session.commit()
            logger.info(f"Summary successfully updated for conv {conversation_id}.")

        except Exception as e:
            logger.error(f"Background summarization failed for conv {conversation_id}: {e}")
            await session.rollback()

    def _apply_budget_protecting_summary(self, messages: list[BaseMessage], max_tokens: int) -> list[BaseMessage]:
        total = sum(approx_tokens(m.content) for m in messages)
        
        # Si no nos pasamos, no hacemos nada
        if total <= max_tokens:
            return messages
            
        # Si el SystemMessage existe, debe ser el primero.
        has_summary = len(messages) > 0 and isinstance(messages[0], SystemMessage)
        summary_msg = messages.pop(0) if has_summary else None
        
        while messages and total > max_tokens:
            removed = messages.pop(0) # Removemos el mensaje crudo más viejo
            total -= approx_tokens(removed.content)
            
        if summary_msg:
            messages.insert(0, summary_msg)
            
        return messages
