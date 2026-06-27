"""
Interfaz base para todas las estrategias de memoria.
"""

from abc import ABC, abstractmethod
from uuid import UUID
from langchain_core.messages import BaseMessage
from sqlalchemy.ext.asyncio import AsyncSession


class MemoryStrategy(ABC):
    """
    Define el contrato para cualquier estrategia de memoria conversacional.
    Todas las implementaciones (SlidingWindow, Vector, Summary, Hybrid) 
    deben heredar de esta clase.
    """

    @abstractmethod
    async def build_context(
        self,
        session: AsyncSession,
        conversation_id: UUID,
        current_question: str,
        max_tokens: int,
    ) -> list[BaseMessage]:
        """
        Devuelve los mensajes de turnos anteriores para adjuntar al prompt, 
        empezando por el más antiguo.

        Reglas:
        - NO debe incluir `current_question` (el caller lo agrega luego).
        - DEBE respetar `max_tokens`. Si se excede, debe truncar, no lanzar excepción.
        - NO debe fallar estrepitosamente en caso de errores transitorios de DB/LLM.
          Debe atrapar el error, loguearlo y devolver el mejor contexto parcial o [].
        """
        pass
