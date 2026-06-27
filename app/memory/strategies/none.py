"""
Estrategia nula de memoria (NoMemory).
"""

from uuid import UUID
from langchain_core.messages import BaseMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.interface import MemoryStrategy


class NoMemory(MemoryStrategy):
    """
    Estrategia "kill switch" o base.
    Siempre devuelve una lista vacía, lo que significa que el LLM
    verá el prompt exactamente igual que si no existiera la memoria.
    """
    
    async def build_context(
        self,
        session: AsyncSession,
        conversation_id: UUID,
        current_question: str,
        max_tokens: int,
    ) -> list[BaseMessage]:
        return []
