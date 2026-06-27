---
name: implement-memory-phase
description: Implements the next pending phase of the conversation-memory layer described in MEMORY_LAYER_PLAN.md. Use when the user asks to continue, advance, or work on the memory layer, sliding window memory, summary memory, vector memory, hybrid memory, or any phase of the memory plan.
---

# Implement next memory-layer phase

Adopt the "Memory Layer Engineer" persona defined in `AGENTS.md` for this task.

## Step 1 — Locate current progress

1. Open `context/MEMORY_LAYER_PLAN.md`.
2. Walk phases 0 through 5 in order. For each one, check its "Acceptance criteria" against the
   actual repository state (files present, migrations applied, tests passing) to determine whether
   it's already complete.
3. The **first phase whose acceptance criteria are not all satisfied** is the one to work on now.
   Stop scanning as soon as you find it — do not jump ahead to a later phase even if some of its
   files happen to already exist.
4. If every phase's acceptance criteria are satisfied, say so explicitly and stop. Do not invent
   extra work that isn't in the plan.

## Step 2 — Confirm assumptions before writing any code

- If the phase depends on something the plan tells you to verify rather than guess (the existing
  embedding model's output dimension, the project's async/sync convention, the migration tool in
  use, the chat endpoint's current signature), go find that fact in the actual codebase first. Do
  not proceed on an assumption when the answer is one file read away.
- If satisfying a "Non-negotiable" (from the plan or from `AGENTS.md`) would require changing
  existing RAG retrieval behavior, stop here and ask the human instead of proceeding.

## Step 3 — Implement only that phase

- Follow that phase's "Tasks" list exactly.
- Match existing code style, folder conventions, and test patterns already in the repo over
  anything more generic the plan suggests.
- Do not start any task listed under a later phase, even if it would be convenient to bundle it in
  now. One phase per run of this skill.

## Step 4 — Self-validate before reporting done

1. Write tests covering every item in that phase's "Acceptance criteria" (if they don't already
   exist) and run them.
2. Run the **full** existing test suite, not just the new tests, to confirm nothing in the RAG
   pipeline broke.
3. Only after both pass, report: which phase you implemented, which files changed, and each
   acceptance criterion you verified with how you verified it.

## If something blocks you

Stop and report the blocker instead of working around it silently when:

- An acceptance criterion can't be verified with the information/tools available to you.
- The phase's tasks conflict with something already implemented in the codebase.
- Finishing the phase would require touching a file outside `app/memory/`, the new migration, or
  the minimal chat-endpoint change Phase 0 describes.
