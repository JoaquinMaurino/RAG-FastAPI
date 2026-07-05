"""
Servicio de LLM — Refactorizado con LangChain.

Cambios respecto a la versión anterior:
----------------------------------------
ANTES:  google.genai.Client → llamada directa al SDK de Google.
AHORA:  LCEL Chain → PromptTemplate | ChatGoogleGenerativeAI | StrOutputParser

¿Qué ganamos con LCEL?
-----------------------
1. Desacoplamiento: cambiar de Gemini a OpenAI requiere modificar UNA línea.
2. Composición declarativa: el flujo de datos es explícito y legible.
3. Async nativo: ainvoke() es async sin necesidad de wrappers manuales.
4. Extensibilidad: agregar streaming, memoria o callbacks es trivial.

El patron Stuffing se mantiene: concatenamos todos los chunks en un
solo bloque de texto y se lo enviamos al LLM en una única llamada.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from loguru import logger
from typing import AsyncGenerator

from app.services.llm_factory import get_llm


# ── Prompt Template ───────────────────────────────────────────────────────────
_PROMPT_TEMPLATE = """\
Sos un asistente de conocimiento interno de la empresa.
Tu trabajo es responder preguntas EXCLUSIVAMENTE usando el contexto proporcionado.

Reglas estrictas:
1. Solo respondé con información que esté en el contexto.
2. Si la respuesta no está en el contexto, decí: "No encontré información sobre eso en los documentos disponibles."
3. No inventes ni supongas información.
4. Citá las partes relevantes del contexto cuando sea apropiado.
5. Respondé en el mismo idioma en que te preguntan.

CONTEXTO:
{context}"""

_prompt = ChatPromptTemplate.from_messages([
    ("system", _PROMPT_TEMPLATE),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{query}"),
])


# ── ChatModel (construido por la factory centralizada) ─────────────────────────
# Temperatura 0.2: respuestas fieles al contexto pero con suficiente
# naturalidad para sonar como un asistente, no como una máquina de copiar.
_llm = get_llm(temperature=0.2)


# ── LCEL Chain ────────────────────────────────────────────────────────────────
# El operador | conecta componentes: la salida de uno es la entrada del siguiente.
# StrOutputParser extrae el string de texto del objeto AIMessage que devuelve el LLM.
_qa_chain = _prompt | _llm | StrOutputParser()


async def generate_answer(query: str, docs: list[Document], chat_history: list[BaseMessage] | None = None) -> str:
    """
    Genera una respuesta usando la LCEL Chain con Gemini.

    Args:
        query: La pregunta del usuario.
        docs:  Lista de LangChain Documents recuperados por search_chunks.
        chat_history: Lista de mensajes previos.

    Returns:
        La respuesta generada por el LLM como string.
    """
    chat_history = chat_history or []
    
    # Construimos el bloque de contexto desde los Documents.
    # page_content es el texto del chunk — la interfaz estándar de LangChain.
    context_block = "\n\n".join(
        f"[{i + 1}] {doc.page_content}" for i, doc in enumerate(docs)
    )

    logger.info(
        f"Invoking LangChain chain ({settings.gemini_model}) "
        f"with {len(docs)} context chunks and {len(chat_history)} history messages"
    )

    # ainvoke() es el método async de las LCEL Chains.
    # Recibe un dict con las variables del PromptTemplate.
    answer = await _qa_chain.ainvoke({"context": context_block, "chat_history": chat_history, "query": query})

    logger.info(f"Chain response received ({len(answer)} chars)")
    return answer

async def generate_answer_stream(query: str, docs: list[Document], chat_history: list[BaseMessage] | None = None) -> AsyncGenerator[str, None]:
    """
    Genera una respuesta en streaming usando la LCEL Chain con Gemini.

    Args:
        query: La pregunta del usuario.
        docs:  Lista de LangChain Documents recuperados por search_chunks.
        chat_history: Lista de mensajes previos.

    Yields:
        Fragmentos (chunks) de texto generados por el LLM en tiempo real.
    """
    chat_history = chat_history or []
    
    context_block = "\n\n".join(
        f"[{i + 1}] {doc.page_content}" for i, doc in enumerate(docs)
    )

    logger.info(
        f"Starting LangChain stream ({settings.gemini_model}) "
        f"with {len(docs)} context chunks and {len(chat_history)} history messages"
    )

    # astream() devuelve un generador asíncrono que escupe tokens
    # a medida que Gemini los va enviando.
    async for chunk in _qa_chain.astream({"context": context_block, "chat_history": chat_history, "query": query}):
        yield chunk
