# ADR 0004: Use LangChain for Agents and Orchestration

**Date:** 2026-06-22  
**Status:** Accepted

## Context
As the system evolves from simple Retrieval-Augmented Generation (RAG) to an autonomous assistant, we need a framework to orchestrate tool-calling and conversational memory.

## Considered Options
* Custom Python implementation.
* LlamaIndex.
* LangChain.

## Decision
We chose **LangChain** (`langchain`, `langchain-core`, `langchain-google-genai`).

## Rationale
1. **Agent Ecosystem**: LangChain provides mature implementations of the ReAct (Reasoning and Acting) paradigm out-of-the-box (`create_tool_calling_agent`, `AgentExecutor`).
2. **LCEL (LangChain Expression Language)**: Simplifies the construction of complex RAG pipelines (Prompt | LLM | Parser) and natively supports streaming (`astream()`).
3. **Standardization**: LangChain is widely adopted in the industry, making the codebase easier for new AI engineers to understand.

## Consequences
- The framework introduces a layer of abstraction that can sometimes obscure underlying errors.
- The Agent Executor's lifecycle does not perfectly align with FastAPI's single-request dependency injection (e.g., `AsyncSession`), requiring agent tools to instantiate their own DB sessions.
