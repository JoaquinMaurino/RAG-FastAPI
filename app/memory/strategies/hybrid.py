"""
Estrategia de memoria: Híbrida (Hybrid Memory).

Composición de las otras tres estrategias: Summary + Vector + Sliding Window.
Sigue el patrón Composition over Inheritance.
"""

from uuid import UUID

from langchain_core.messages import BaseMessage, SystemMessage
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.memory.interface import MemoryStrategy
from app.memory.strategies.sliding_window import SlidingWindowMemory
from app.memory.strategies.summary import SummaryMemory
from app.memory.strategies.vector import VectorMemory
from app.memory.tokens import approx_tokens


class HybridMemory(MemoryStrategy):
    """
    Estrategia híbrida que compone Summary, Vector y SlidingWindow.

    El contexto generado sigue el siguiente orden:
    [Resumen] -> [Matches Semánticos Deduplicados] -> [Mensajes Recientes]
    """

    def __init__(self):
        # Instanciamos las dependencias una sola vez, delegando sus propias configs
        self.summary = SummaryMemory()
        self.vector = VectorMemory()
        self.sliding = SlidingWindowMemory()

    async def build_context(
        self,
        session: AsyncSession,
        conversation_id: UUID,
        current_question: str,
        max_tokens: int,
    ) -> list[BaseMessage]:
        try:
            # 1. Recuperar los 3 contextos de forma independiente.
            # Les pasamos max_tokens a cada uno temporalmente, nosotros haremos 
            # el trimeo final global.
            summary_context = await self.summary.build_context(session, conversation_id, current_question, max_tokens)
            vector_context = await self.vector.build_context(session, conversation_id, current_question, max_tokens)
            sliding_context = await self.sliding.build_context(session, conversation_id, current_question, max_tokens)

            # 2. Desgranar componentes
            # a) Resumen (el SystemMessage que siempre va primero si existe)
            has_summary = len(summary_context) > 0 and isinstance(summary_context[0], SystemMessage)
            summary_msg = summary_context[0] if has_summary else None
            
            # b) Mensajes recientes crudos (ignoramos el SystemMessage si summary devolvió uno)
            recent_msgs = sliding_context
            
            # c) Matches semánticos
            semantic_msgs = vector_context

            # 3. Deduplicación por msg_id
            # Obtenemos los IDs de los mensajes recientes
            recent_ids = set()
            for m in recent_msgs:
                msg_id = m.additional_kwargs.get("msg_id")
                if msg_id:
                    recent_ids.add(msg_id)

            # Filtramos los semánticos que ya están en los recientes
            dedup_semantic_msgs = []
            for m in semantic_msgs:
                msg_id = m.additional_kwargs.get("msg_id")
                # Si no tiene ID o no está en recientes, lo mantenemos
                if not msg_id or msg_id not in recent_ids:
                     dedup_semantic_msgs.append(m)

            # 4. Aplicar la regla de recorte (Token Budget)
            # Regla de la Sección 6: trim semantic primero, luego recent, NUNCA summary.
            # NUNCA question (pero el caller la agrega después, así que estamos a salvo).
            total_tokens = sum(approx_tokens(m.content) for m in dedup_semantic_msgs + recent_msgs)
            if summary_msg:
                total_tokens += approx_tokens(summary_msg.content)

            # Mientras estemos excedidos, recortamos en orden de prioridad inversa:
            # 1ro: sacamos semánticos (pop(0) saca el match menos relevante si están ordenados, 
            # o el más viejo. En VectorMemory el último agregado es el más cercano, 
            # pero por simplicidad pop(0) saca desde el inicio).
            while total_tokens > max_tokens and dedup_semantic_msgs:
                removed = dedup_semantic_msgs.pop(0)
                total_tokens -= approx_tokens(removed.content)
            
            # 2do: si todavía estamos excedidos, sacamos recientes más antiguos
            while total_tokens > max_tokens and recent_msgs:
                removed = recent_msgs.pop(0)
                total_tokens -= approx_tokens(removed.content)

            # 5. Ensamblar contexto final
            final_context = []
            if summary_msg:
                final_context.append(summary_msg)
            
            final_context.extend(dedup_semantic_msgs)
            final_context.extend(recent_msgs)

            logger.debug(
                f"HybridMemory: conv={conversation_id}, summary={bool(summary_msg)}, "
                f"semantic={len(dedup_semantic_msgs)}, recent={len(recent_msgs)}, "
                f"total_msgs={len(final_context)}"
            )
            return final_context

        except Exception as e:
            logger.error(f"HybridMemory.build_context failed for conv {conversation_id}: {e}")
            return []

    async def run_background_tasks(self, session: AsyncSession, conversation_id: UUID) -> None:
        """
        Delega las tareas de background (actualización de resúmenes)
        a la instancia interna de SummaryMemory.
        """
        await self.summary.run_background_tasks(session, conversation_id)

def semantically_in_recent(msg_id: str, recent_ids: set) -> bool:
    return msg_id in recent_ids
