"""
Servicio de LLM (Large Language Model).

Responsabilidad única: recibir una pregunta y fragmentos de contexto,
y devolver una respuesta generada por Gemini.

Patrón utilizado: Stuffing
──────────────────────────
Concatenamos todos los chunks recuperados en un solo bloque de texto
y se lo enviamos al LLM en una única llamada. Es la estrategia más
simple, rápida y barata. Los modelos modernos tienen ventanas de
contexto lo suficientemente grandes para manejar esto sin problemas.
"""

from google import genai
from loguru import logger

from app.core.config import settings


# ── Cliente de Gemini ─────────────────────────────────────────────────────────
# Instanciamos el cliente una sola vez al importar el módulo (Singleton).
# El SDK necesita la API key para autenticarse contra los servidores de Google.
_client = genai.Client(api_key=settings.gemini_api_key)


# ── System Prompt ─────────────────────────────────────────────────────────────
# Esta es la instrucción base que define el COMPORTAMIENTO del asistente.
# Es la pieza más importante para evitar alucinaciones: le decimos
# explícitamente que solo use la información del contexto provisto.
SYSTEM_PROMPT = """Sos un asistente de conocimiento interno de la empresa.
Tu trabajo es responder preguntas EXCLUSIVAMENTE usando el contexto proporcionado.

Reglas estrictas:
1. Solo respondé con información que esté en el contexto.
2. Si la respuesta no está en el contexto, decí: "No encontré información sobre eso en los documentos disponibles."
3. No inventes ni supongas información.
4. Citá las partes relevantes del contexto cuando sea apropiado.
5. Respondé en el mismo idioma en que te preguntan."""


def _build_user_prompt(query: str, contexts: list[str]) -> str:
    """
    Arma el prompt final que recibe el LLM combinando pregunta + contexto.

    Estructura del prompt (Stuffing):
        CONTEXTO:
        [1] texto del chunk 1
        [2] texto del chunk 2
        ...
        PREGUNTA:
        ¿...?

    Los números entre corchetes ayudan al modelo a referenciar
    fuentes específicas en su respuesta.
    """
    context_block = "\n\n".join(
        f"[{i + 1}] {text}" for i, text in enumerate(contexts)
    )

    return f"""CONTEXTO:
{context_block}

PREGUNTA:
{query}"""


async def generate_answer(query: str, contexts: list[str]) -> str:
    """
    Genera una respuesta usando Gemini con la técnica de Stuffing.

    Args:
        query:    La pregunta del usuario.
        contexts: Lista de textos de los chunks recuperados en la búsqueda.

    Returns:
        La respuesta generada por el LLM como string.
    """
    user_prompt = _build_user_prompt(query, contexts)

    logger.info(
        f"Sending prompt to Gemini ({settings.gemini_model}) "
        f"with {len(contexts)} context chunks"
    )

    # generate_content es la llamada principal al LLM.
    # contents: el mensaje del usuario (pregunta + contexto).
    # config: parámetros de generación (system prompt, temperatura, etc.).
    response = _client.models.generate_content(
        model=settings.gemini_model,
        contents=user_prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            # Temperatura baja = respuestas más determinísticas y fieles al contexto.
            # 0.0 sería 100% determinístico pero puede sonar robótico.
            # 0.2 da un buen balance entre fidelidad y naturalidad.
            temperature=0.2,
        ),
    )

    answer = response.text
    logger.info(f"Gemini response received ({len(answer)} chars)")
    return answer
