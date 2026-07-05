"""
Factory centralizada para la construcción del LLM.

¿Por qué una factory?
---------------------
Antes de este módulo, el proyecto tenía DOS instanciaciones independientes
de ChatGoogleGenerativeAI: una en llm_service.py (/chat) y otra en
agent_service.py (/agent). Si mañana quisieras usar Ollama para testear
localmente sin gastar cuota de Gemini, tendrías que cambiar dos archivos.

Esta factory centraliza la construcción en un solo lugar. Todos los módulos
que necesiten un LLM llaman a get_llm(), y la variable de entorno
LLM_PROVIDER decide qué proveedor se usa.

Patrón: Composition over Inheritance (via factory function).
No hay clases abstractas ni herencia — solo una función que devuelve la
interfaz BaseChatModel de LangChain, que todos los proveedores implementan.
"""

from langchain_core.language_models.chat_models import BaseChatModel
from loguru import logger

from app.core.config import settings


def get_llm(temperature: float = 0.2) -> BaseChatModel:
    """
    Construye y devuelve una instancia del LLM configurado.

    El proveedor se selecciona con la variable de entorno LLM_PROVIDER.
    La temperatura se parametriza porque distintos casos de uso la necesitan
    distinta:
      - /chat usa 0.2 (un poco de creatividad para respuestas naturales)
      - /agent usa 0.0 (determinismo máximo para tool-calling correcto)

    Args:
        temperature: Temperatura del modelo. 0.0 = determinístico, 1.0 = creativo.

    Returns:
        Una instancia de BaseChatModel lista para usar con LangChain.
    """
    provider = settings.llm_provider

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        logger.info(f"Building LLM: provider=gemini, model={settings.gemini_model}, temp={temperature}")
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=temperature,
        )

    elif provider == "ollama":
        from langchain_ollama import ChatOllama

        logger.info(
            f"Building LLM: provider=ollama, model={settings.ollama_model}, "
            f"base_url={settings.ollama_base_url}, temp={temperature}"
        )
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=temperature,
        )

    # Pydantic ya valida con Literal, pero por seguridad defensiva:
    raise ValueError(f"LLM provider '{provider}' no soportado. Valores válidos: gemini, ollama")
