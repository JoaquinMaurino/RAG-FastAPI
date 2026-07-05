import asyncio
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import BaseMessage
from langchain.agents import create_tool_calling_agent, AgentExecutor
from loguru import logger

from app.services.llm_factory import get_llm
from app.agents.tools import search_documents, count_documents, get_document_info

# 1. Instantiate the LLM via the shared factory
# Temperature 0.0 is ideal for agents: maximizes determinism in tool-calling decisions,
# reducing hallucinations and ensuring consistent tool selection.
_llm = get_llm(temperature=0.0)

# 2. Define the tools the agent can use
_tools = [
    search_documents,
    count_documents,
    get_document_info,
]

# 3. Create the Agent Prompt
# Agents require a specific prompt structure. They need a system message,
# a placeholder for the conversation history, a placeholder for the user input,
# and a specific placeholder called "agent_scratchpad" where LangChain injects
# the intermediate steps (Tool calls and their outputs).
_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a helpful company internal assistant. You have access to a database of documents. "
        "Use the provided tools to help the user answer their questions. "
        "If the user greets you or asks a general question, answer normally without using tools. "
        "Always use the tools to answer questions about documents."
    ),
    # Historial conversacional inyectado por ConversationManager antes de cada turno.
    # optional=True: cuando MEMORY_STRATEGY=none, el historial es [] y no rompe el prompt.
    MessagesPlaceholder(variable_name="chat_history", optional=True),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# 4. Create the Tool Calling Agent
# This is a specific type of agent optimized for models that natively support function calling (like Gemini).
_agent = create_tool_calling_agent(_llm, _tools, _prompt)

# 5. Create the Agent Executor
# The executor is the runtime that manages the loop: 
# call agent -> agent decides tool -> call tool -> feed result to agent -> repeat
_agent_executor = AgentExecutor(
    agent=_agent,
    tools=_tools,
    verbose=True,  # This will print the agent's thought process to the console
    return_intermediate_steps=False,
    # --- Guardrails ---
    # Prevents infinite tool-calling loops that would burn API quota uncontrollably.
    max_iterations=5,
    # Absolute wall-clock timeout in seconds. Cuts execution cleanly if a tool
    # or LLM call hangs (e.g. network issues, slow DB).
    max_execution_time=30,
    # If the LLM returns a malformed tool call (broken JSON, unknown tool name),
    # the executor retries gracefully instead of raising an unhandled exception.
    handle_parsing_errors=True,
    # When max_iterations is reached, ask the LLM to produce a final answer
    # from whatever context it has accumulated, instead of returning None or erroring.
    early_stopping_method="generate",
)

class AgentProviderError(Exception):
    """El proveedor de LLM rechazó el request (rate limit, credenciales inválidas, etc.)"""

class AgentTimeoutError(Exception):
    """La ejecución del agente superó el tiempo máximo permitido."""


async def run_agent(
    query: str,
    chat_history: list[BaseMessage] | None = None,
) -> str:
    """
    Invokes the agent with the user's query and optional conversation history.

    Args:
        query: La pregunta actual del usuario.
        chat_history: Historial de mensajes construido por ConversationManager.
                      Si es None o vacío, el agente opera sin contexto previo.

    Raises:
        AgentProviderError: Si el LLM devuelve un error de API (rate limit, auth, etc.).
        AgentTimeoutError: Si la ejecución supera max_execution_time.
        Exception: Cualquier otro error inesperado — se loguea y se re-propaga.
    """
    history = chat_history or []
    logger.info(
        f"Invoking AgentExecutor | query='{query}' | history_messages={len(history)}"
    )

    try:
        response = await _agent_executor.ainvoke({
            "input": query,
            "chat_history": history,
        })
        return response["output"]

    except asyncio.TimeoutError as e:
        # El timeout del event loop de Python (distinto del max_execution_time de LangChain,
        # que es manejado internamente por el executor y devuelve un resultado parcial).
        logger.error(f"Agent execution timed out for query: '{query}' | error={type(e).__name__}")
        raise AgentTimeoutError("El agente superó el tiempo máximo de ejecución.") from e

    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)

        # Detectamos errores conocidos del proveedor sin depender de tipos internos de cada SDK.
        # Las excepciones de Gemini/Ollama suelen contener estas palabras en su mensaje.
        provider_keywords = (
            "rate limit", "quota", "unauthorized", "api key", "authentication",
            "permission denied", "resource exhausted", "429", "401", "403",
        )
        is_provider_error = any(kw in error_msg.lower() for kw in provider_keywords)

        if is_provider_error:
            logger.error(
                f"LLM provider error for query: '{query}' | "
                f"error_type={error_type} | detail={error_msg}"
            )
            raise AgentProviderError(
                f"El proveedor de LLM no pudo procesar el request: {error_type}"
            ) from e

        # Error inesperado: logueamos con detalle para debugging pero
        # nunca exponemos el traceback crudo al cliente.
        logger.exception(
            f"Unexpected agent error for query: '{query}' | error_type={error_type}"
        )
        raise
