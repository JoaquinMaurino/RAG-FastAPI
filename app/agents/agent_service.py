from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor
from loguru import logger

from app.core.config import settings
from app.agents.tools import search_documents, count_documents, get_document_info

# 1. Instantiate the LLM
_llm = ChatGoogleGenerativeAI(
    model=settings.gemini_model,
    google_api_key=settings.gemini_api_key,
    temperature=0.0,  # Temperature 0 is ideal for agents to reduce hallucinations when calling tools
)

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
)

async def run_agent(query: str) -> str:
    """
    Invokes the agent with the user's query.
    """
    logger.info(f"Invoking AgentExecutor for query: {query}")
    
    # We pass the query as the 'input' variable defined in the ChatPromptTemplate
    response = await _agent_executor.ainvoke({"input": query})
    
    return response["output"]
