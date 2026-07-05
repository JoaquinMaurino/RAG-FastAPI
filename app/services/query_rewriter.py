"""
Servicio de reformulación de queries (Query Rewriting).

Guardrail de degradación elegante:
-----------------------------------
El rewriter es un servicio SECUNDARIO. Si falla (timeout, error de API,
respuesta vacía), el sistema usa la query original y sigue funcionando.
Nunca debe bloquear el flujo principal de RAG — eso sería peor que no tenerlo.

Patrón: la función es pura (no depende de sesión DB), recibe la query
y el historial (que ya tiene el ConversationManager), y devuelve un string.
"""

from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from loguru import logger

from app.services.llm_factory import get_llm


# ── Prompt de reformulación ────────────────────────────────────────────────────
# Prompt minimalista: instrucción clara, un ejemplo implícito en el formato,
# y la instrucción de NO agregar explicaciones — solo devolver la query.
_REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a query rewriting assistant. Your only job is to rewrite the user's "
        "question into a clear, self-contained search query that can be understood "
        "without any prior conversation context.\n\n"
        "Rules:\n"
        "- If the question already is self-contained, return it unchanged.\n"
        "- If the question refers to something from the chat history, incorporate "
        "  that context into the rewritten query.\n"
        "- Return ONLY the rewritten query, no explanations, no preamble.\n"
        "- Keep the same language as the original question.\n"
        "- Be concise: a good search query is 5-20 words."
    ),
    (
        "human",
        "Chat history (last exchanges, for context only):\n{chat_history_text}\n\n"
        "User question to rewrite: {query}"
    ),
])

# Temperatura 0.0: el rewriter debe ser determinístico y factual, no creativo.
_rewrite_chain = _REWRITE_PROMPT | get_llm(temperature=0.0) | StrOutputParser()


def _format_history_for_prompt(chat_history: list[BaseMessage], max_messages: int = 6) -> str:
    """
    Serializa los últimos N mensajes del historial como texto plano para el prompt.

    Solo usamos los más recientes porque el rewriter solo necesita resolver
    referencias inmediatas ("ese", "eso", "el anterior"), no toda la conversación.
    """
    if not chat_history:
        return "(no prior conversation)"

    recent = chat_history[-max_messages:]
    lines = []
    for msg in recent:
        role = "User" if msg.type == "human" else "Assistant"
        lines.append(f"{role}: {msg.content}")
    return "\n".join(lines)


async def rewrite_query(
    query: str,
    chat_history: list[BaseMessage] | None = None,
) -> str:
    """
    Reformula la query del usuario para mejorar la relevancia de la búsqueda.

    Toma la pregunta cruda y el historial conversacional reciente, y produce
    una versión explícita y autocontenida que maximiza la calidad del embedding.

    Si la reformulación falla (excepción, respuesta vacía, o resultado
    idéntico al input), retorna la query original sin modificar.

    Args:
        query:        La pregunta del usuario tal como la escribió.
        chat_history: Historial de mensajes del ConversationManager.

    Returns:
        La query reformulada, o la original si el rewriter falla.
    """
    history = chat_history or []

    # Si no hay historial, la query ya es autocontenida por definición.
    # Nos ahorramos una llamada al LLM.
    if not history:
        logger.debug(f"Query rewriter skipped (no history): '{query}'")
        return query

    history_text = _format_history_for_prompt(history)

    try:
        rewritten = await _rewrite_chain.ainvoke({
            "query": query,
            "chat_history_text": history_text,
        })

        # Sanity checks: si el rewriter devuelve algo vacío o idéntico, no vale la pena.
        rewritten = rewritten.strip()
        if not rewritten or rewritten.lower() == query.lower():
            logger.debug(f"Query rewriter returned no change for: '{query}'")
            return query

        logger.info(
            f"Query rewritten | original='{query}' | rewritten='{rewritten}'"
        )
        return rewritten

    except Exception as e:
        # Guardrail: degradamos elegantemente. El rewriter nunca bloquea el RAG.
        logger.warning(
            f"Query rewriter failed — falling back to original query. "
            f"error={type(e).__name__}: {e}"
        )
        return query
