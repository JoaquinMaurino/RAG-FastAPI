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

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from loguru import logger

from app.core.config import settings


# ── Prompt Template ───────────────────────────────────────────────────────────
# PromptTemplate reemplaza el f-string manual de la versión anterior.
# Las variables entre llaves ({context}, {query}) se inyectan en ainvoke().
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
{context}

PREGUNTA:
{query}"""

_prompt = PromptTemplate.from_template(_PROMPT_TEMPLATE)


# ── ChatModel (LangChain wrapper de Gemini) ───────────────────────────────────
# ChatGoogleGenerativeAI implementa la interfaz estándar BaseChatModel de LangChain.
# Temperatura baja = respuestas más determinísticas y fieles al contexto.
_llm = ChatGoogleGenerativeAI(
    model=settings.gemini_model,
    google_api_key=settings.gemini_api_key,
    temperature=0.2,
)


# ── LCEL Chain ────────────────────────────────────────────────────────────────
# El operador | conecta componentes: la salida de uno es la entrada del siguiente.
# StrOutputParser extrae el string de texto del objeto AIMessage que devuelve el LLM.
_qa_chain = _prompt | _llm | StrOutputParser()


async def generate_answer(query: str, docs: list[Document]) -> str:
    """
    Genera una respuesta usando la LCEL Chain con Gemini.

    Args:
        query: La pregunta del usuario.
        docs:  Lista de LangChain Documents recuperados por search_chunks.

    Returns:
        La respuesta generada por el LLM como string.
    """
    # Construimos el bloque de contexto desde los Documents.
    # page_content es el texto del chunk — la interfaz estándar de LangChain.
    context_block = "\n\n".join(
        f"[{i + 1}] {doc.page_content}" for i, doc in enumerate(docs)
    )

    logger.info(
        f"Invoking LangChain chain ({settings.gemini_model}) "
        f"with {len(docs)} context chunks"
    )

    # ainvoke() es el método async de las LCEL Chains.
    # Recibe un dict con las variables del PromptTemplate.
    answer = await _qa_chain.ainvoke({"context": context_block, "query": query})

    logger.info(f"Chain response received ({len(answer)} chars)")
    return answer
