# Memory Layer Implementation Plan

> **Read this before writing any code.** This is a phased spec, not a checklist to do all at once.
> Work through the phases **in order**. Do not start phase *N+1* until every item in phase *N*'s
> "Acceptance criteria" is green. If something here conflicts with an existing convention in the
> codebase (naming, async style, ORM patterns, folder layout), **follow the existing convention**
> and note the deviation in your final summary instead of asking. Only stop and ask the human if
> honoring a "Non-negotiable" below would require breaking currently-working RAG functionality.

## 1. Goal

Add a pluggable conversation-memory layer to the existing RAG MVP (FastAPI + LangChain + Gemini +
pgvector + HuggingFace embeddings), so the assistant can hold a multi-turn conversation instead of
answering each question in isolation. Four interchangeable strategies — sliding window, summary,
vector, hybrid — selectable via configuration, with no changes to how the RAG retriever itself
finds documents.

## 2. Non-negotiables

- The existing retrieval logic (how documents are found and ranked) is **not modified**. The only
  permitted touchpoint into the existing chain is adding **one new input variable** — conversation
  history — to the existing prompt template. If today's chain has no such variable, add it; do not
  rebuild the chain.
- No Redis. No new message broker. PostgreSQL is the only source of truth for this feature.
- Reuse the **existing embedding model** (the one already used to embed RAG documents). Do not
  introduce a second embedding model for conversation memory. Before writing any embedding code,
  locate where the current embedding model and its output dimension are configured, and reuse that
  dimension for the new `vector` column — do not hardcode a guessed dimension.
- Every strategy implements the same async interface (Section 5). `HybridMemory` must be built by
  **composing instances of the other three strategies**, not by re-implementing their logic. This
  is a direct instance of "composition over inheritance" — treat it as the canonical example for
  the rest of the codebase, not just a one-off.
- Every strategy must respect a token budget passed in by the caller (Section 6). A strategy that
  ignores the budget is a bug, not an optimization to do later.
- If a strategy fails at runtime (DB error, embedding call fails, summarizer LLM call fails), the
  conversation must **not** break. Fall back to an empty context (or, if already available, the
  last successfully built context) and log the failure. The user always gets an answer.

## 3. Target architecture

```
FastAPI chat endpoint
        │
        ▼
ConversationManager  ──persists──▶  PostgreSQL (conversations, messages, conversation_summaries)
        │
        ▼  selects via MEMORY_STRATEGY
MemoryStrategy
 ├── NoMemory            (returns [] — used only during Phase 0 rollout / as a kill switch)
 ├── SlidingWindowMemory
 ├── SummaryMemory
 ├── VectorMemory
 └── HybridMemory        (composes Sliding + Summary + Vector)
        │
        ▼
list[BaseMessage]  (conversation history only — NOT the RAG-retrieved documents)
        │
        ▼
existing Prompt Builder  ──merges with──▶  existing Retriever output  ──▶  existing LLM call
```

`ConversationManager` is the **only** component that knows which strategy is active. Nothing else
in the codebase should import a concrete strategy class.

## 4. Proposed file layout

Adjust names/paths to match existing conventions, but keep memory code isolated in its own package
so it can be deleted or disabled without touching RAG code:

```
app/
  memory/
    __init__.py
    interface.py          # MemoryStrategy ABC
    config.py              # MEMORY_STRATEGY setting + validation
    tokens.py               # shared token-budget helper
    strategies/
      none.py
      sliding_window.py
      summary.py
      vector.py
      hybrid.py
    conversation_manager.py
    models.py               # Conversation, Message, ConversationSummary ORM models
  migrations/
    xxxx_add_conversation_memory.py
```

## 5. Database schema

Confirm the project's existing migration tool (Alembic or otherwise) and existing UUID/timestamp
conventions before writing this — match what's already there. Logical schema:

```sql
CREATE TABLE conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    embedding       VECTOR(<DIM>),   -- <DIM> = existing RAG embedding model's output size. Verify, don't guess.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Embeddings are generated only for `role = 'user'` messages, per the original design.
CREATE INDEX idx_messages_conv_created ON messages (conversation_id, created_at);
CREATE INDEX idx_messages_embedding_hnsw ON messages USING hnsw (embedding vector_cosine_ops);

CREATE TABLE conversation_summaries (
    conversation_id              UUID PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    summary                      TEXT NOT NULL,
    summarized_through_message_id UUID REFERENCES messages(id),
    updated_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`summarized_through_message_id` is added relative to the original draft: it marks exactly which
message the current summary already accounts for, which is what makes **incremental** summarization
possible (see Phase 3 — without it, `SummaryMemory` would have to re-summarize the entire history
every time, which defeats its own "low token usage" purpose as the conversation grows).

## 6. Token budget policy (new — not in the original draft)

Every `build_context` call receives a `max_tokens` budget for the history section. Add a small
shared helper (`memory/tokens.py`) used by all strategies:

- Start with a cheap heuristic: `approx_tokens(text) = len(text) // 4`. This avoids an extra network
  call per turn. Do not introduce `tiktoken` or a Gemini `count_tokens` call for this unless the
  heuristic proves wrong in practice — that's a Phase 5+ refinement, not a blocker now.
- `SlidingWindowMemory`: if the last N messages exceed the budget, drop the **oldest** ones first
  until it fits, even if that means returning fewer than N.
- `HybridMemory`: when over budget, trim in this order — semantic matches first, then recent
  messages — never trim the summary, and never drop the current question.

## 7. The interface

```python
# app/memory/interface.py
from abc import ABC, abstractmethod
from uuid import UUID
from langchain_core.messages import BaseMessage

class MemoryStrategy(ABC):
    @abstractmethod
    async def build_context(
        self,
        conversation_id: UUID,
        current_question: str,
        max_tokens: int,
    ) -> list[BaseMessage]:
        """Return prior-turn messages to prepend to the prompt, oldest first.

        Must NOT include `current_question` — the caller appends it separately.
        Must respect `max_tokens` (see Section 6); never raise on budget overflow, truncate instead.
        Must not raise on transient failures — catch, log, and return the best partial context
        available (or []), per the fallback rule in Section 2.
        """
```

Method is `async` because every real implementation does at least one DB round-trip, and
`SummaryMemory`/`VectorMemory` also do embedding or LLM calls. If the rest of the codebase's
DB/LLM calls are sync, mirror that instead — match existing conventions over this spec.

## 8. ConversationManager responsibilities

- Resolve the active strategy from `MEMORY_STRATEGY` (constructed once, not per-request, except for
  strategies that need fresh sub-dependencies).
- Given `(conversation_id | None, question)`:
  1. If `conversation_id` is `None`, create a new `Conversation` row and use its id from here on.
  2. Call `strategy.build_context(conversation_id, question, max_tokens)`.
  3. Persist the user message (and, after embeddings exist from Phase 2 onward, embed it — see
     note on latency below).
  4. Return the context to the existing prompt-building step; **do not touch retrieval**.
  5. After the LLM responds, persist the assistant message.
  6. If the active strategy needs post-turn bookkeeping (e.g. `SummaryMemory` checking its
     threshold), trigger it **after** the response is returned to the user — as a `BackgroundTasks`
     job (FastAPI) or equivalent — never block the user-facing latency on it.
- If the chat endpoint streams the response (SSE/WebSocket), persist the assistant message only
  after the full stream has completed and been accumulated — not chunk by chunk.

This is the only place in the codebase allowed to import concrete strategy classes.

## 9. Phased plan

### Phase 0 — Foundations (wiring, no behavior change)

**Tasks**
- Create the file layout from Section 4.
- Implement `MemoryStrategy` (interface only) and `NoMemory` (returns `[]` always).
- Add `MEMORY_STRATEGY` setting (see Section 11), defaulting to `none`.
- Add the migration for `conversations`, `messages`, `conversation_summaries` (Section 5) — confirm
  the embedding dimension first, per Section 2.
- Implement `ConversationManager` per Section 8, wired with `NoMemory` as the only available
  strategy for now.
- Update the chat endpoint to accept an optional `conversation_id` and to route through
  `ConversationManager`. Behavior of the actual RAG answer must be byte-for-byte unchanged.

**Acceptance criteria**
- All pre-existing RAG tests still pass unmodified.
- A new conversation row and two message rows (user + assistant) are created per chat call.
- Calling the endpoint twice with the same `conversation_id` reuses the same conversation row.
- `MEMORY_STRATEGY=none` is the default and produces identical answers to the pre-memory MVP.

### Phase 1 — SlidingWindowMemory

**Tasks**
- Implement `SlidingWindowMemory(window_size: int)`, default `window_size=10`, applying the token
  budget rule from Section 6.
- Add `sliding` to valid `MEMORY_STRATEGY` values and make it the new default.

**Acceptance criteria**
- Integration test: seed a conversation with 15 messages, assert `build_context` returns at most
  10, oldest-first, and that the oldest 5 are excluded.
- Manual check: ask a follow-up question that only makes sense with the previous 2 turns in
  context (e.g. "what about for the second one?") and confirm the model answers coherently.

### Phase 2 — VectorMemory

**Tasks**
- On persisting a user message, generate its embedding using the **existing** embedding model and
  store it on the row. If embedding adds noticeable latency to the response path, move it to a
  background task — it's only needed for *future* turns, never the current one.
- Implement `VectorMemory(top_k: int)`, default `top_k=5`: embed `current_question`, query pgvector
  for the most similar **prior** user messages (and their paired assistant reply) in that
  conversation, ordered by similarity.
- Known limitation to document in code comments, not necessarily fix now: pure similarity search
  has no recency awareness — an old, topically-similar message can outrank yesterday's relevant
  one. This is exactly the gap `HybridMemory` exists to close.

**Acceptance criteria**
- Test: two messages early in a long conversation are semantically similar to a later question but
  far outside the sliding window; `VectorMemory.build_context` retrieves them and `SlidingWindowMemory`
  on the same fixture does not.

### Phase 3 — SummaryMemory

**Tasks**
- Implement incremental summarization: when the message count since
  `conversation_summaries.summarized_through_message_id` exceeds a configurable threshold (default
  20), generate a **new** summary from `(previous_summary, messages_since_then)` — never from full
  history — and update `summarized_through_message_id` to the latest message id included.
- Trigger this check as a background task after responding (Section 8), not inline.
- Guard against duplicate concurrent runs for the same `conversation_id` (e.g. a simple
  `SELECT ... FOR UPDATE` on the summary row, or an in-process per-conversation lock — pick whichever
  matches existing concurrency patterns in the codebase).
- `build_context` returns the stored summary (as a single `SystemMessage`) plus the last N raw
  messages since `summarized_through_message_id`.

**Acceptance criteria**
- Test: simulate crossing the threshold twice; assert the second summary call only receives the
  messages added since the first summary, not the whole history (this is the regression test that
  actually proves "incremental" is working, not just "summary exists").
- Test/measure: confirm summary generation does not add latency to the chat response itself
  (response returns before the background summarization task completes).

### Phase 4 — HybridMemory (composition)

**Tasks**
- `HybridMemory.__init__` takes instances of `SummaryMemory`, `VectorMemory`, `SlidingWindowMemory`
  — constructed once and injected, not re-instantiated per call.
- `build_context` order (adopted default — documented as a tunable, not dogma): summary →
  deduplicated semantic matches → recent window → (caller appends `current_question` last).
  Rationale for putting recent messages closest to the question rather than the original
  summary-then-recent-then-semantic order: models tend to weight context closest to the question
  most heavily, and the most recent turns are usually the most relevant to an immediate follow-up.
  If real usage suggests otherwise, this order is the first thing to A/B test — it is not a
  correctness requirement.
- Deduplicate by message id: any message returned by `VectorMemory` that's already present in the
  `SlidingWindowMemory` result must appear only once.
- Apply the trim order from Section 6 if the combined result exceeds `max_tokens`.

**Acceptance criteria**
- Test: construct a fixture where a recent message is also a top semantic match; assert it appears
  exactly once in the final context.
- Test: force a tiny `max_tokens` and confirm the summary and current question always survive while
  semantic/recent content is trimmed first.

### Phase 5 — Hardening

**Tasks**
- Wrap every strategy's `build_context` call site in `ConversationManager` with the fallback rule
  from Section 2 (catch, log with conversation id + strategy name, fall back to `[]`).
- Run the full test suite (existing RAG tests + all memory tests) together.
- Sanity-check with `git diff` (or equivalent) that no file outside `app/memory/`, the migration,
  and the minimal endpoint change from Phase 0 was touched — this is the literal verification of
  "existing RAG pipeline remains unchanged."

**Acceptance criteria**
- All Success Criteria in Section 12 are met.
- Deliberately breaking the DB connection for memory only (not for the main RAG vector store) still
  yields a normal — if memory-less — answer instead of a 500.

## 10. Suggested module size

Keep each strategy file under roughly 100-150 lines. If `SummaryMemory` or `HybridMemory` grows
past that, it's a sign some logic belongs in `ConversationManager` or a shared helper instead of
inside the strategy.

## 11. Configuration reference

| Variable | Values | Default | Notes |
|---|---|---|---|
| `MEMORY_STRATEGY` | `none`, `sliding`, `summary`, `vector`, `hybrid` | `none` until Phase 1 ships, then `sliding` | Renamed from `MEMORY_PROVIDER` in the original draft to match the `MemoryStrategy` class name used throughout the code — keep config and code vocabulary consistent. Validate with an enum/`Literal`; invalid values should fail fast at startup, not silently fall back. |
| `MEMORY_SLIDING_WINDOW_SIZE` | int | `10` | Phase 1 |
| `MEMORY_VECTOR_TOP_K` | int | `5` | Phase 2 |
| `MEMORY_SUMMARY_THRESHOLD` | int | `20` | Phase 3, messages since last summary |
| `MEMORY_MAX_CONTEXT_TOKENS` | int | project-dependent — pick something that leaves comfortable room under the model's context window after the RAG-retrieved documents and system prompt are accounted for | Section 6 |

## 12. Success criteria (overall)

- Existing RAG pipeline's retrieval and ranking logic is byte-for-byte unchanged.
- Memory strategy is switchable via `MEMORY_STRATEGY` with no other code changes.
- Every strategy demonstrably produces different context for the same fixture conversation (covered
  by the per-phase tests above).
- All conversation data is persisted in PostgreSQL; semantic memory uses pgvector with an index.
- A strategy failure degrades gracefully and never breaks the chat response.
- `HybridMemory` is implemented by composing the other three strategy instances, not by duplicating
  their logic.

## 13. Explicitly out of scope for this plan

- Redis (cache, session store, or otherwise).
- Switching to LlamaIndex, Google ADK, or any framework other than the LangChain integration already
  in use.
- Token-exact accounting via `tiktoken` or a model-specific `count_tokens` call — the heuristic in
  Section 6 is sufficient for now.
- Deploying any of this to a cloud environment — local/Docker is the only target.

## 14. Future improvements (unchanged from original draft, for later)

- Redis cache for active conversations / session store.
- Checkpointing for agents; LangGraph integration.
- Long-term memory retention/pruning policies.
- Memory observability and token-usage analytics dashboards.
- Replace the heuristic token counter with exact counts if budget overruns are observed in practice.
