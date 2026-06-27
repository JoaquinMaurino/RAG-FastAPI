---
name: validate-memory-phase
description: Reports which phases of the memory layer plan in MEMORY_LAYER_PLAN.md are complete, in progress, or not started, by checking each phase's acceptance criteria against the actual repository state. Use when the user asks for status, progress, or "where are we" on the memory layer.
---

# Validate memory-layer plan progress

This is a **read-only diagnostic** skill. Do not write, edit, or run migrations against any file
while running it — only inspect and report.

## Steps

1. Open `context/MEMORY_LAYER_PLAN.md` and list phases 0 through 5.
2. For each phase, check every item in its "Acceptance criteria" against the real repository
   state: run the relevant tests if they exist, check for the files/migrations/config the phase
   describes, and explicitly note anything you cannot verify automatically (e.g. something that
   needs a manual/human check, like a live latency measurement).
3. Produce a status table: phase number, phase name, status (`done`, `partial`, `not started`),
   and — for any `partial` phase — exactly which acceptance criteria are still failing and why.
4. If a phase reports `done` but a later phase's prerequisites for it don't actually hold (for
   example, an index the plan requires is missing, or a config value differs from the plan),
   flag that as an inconsistency instead of silently trusting the earlier "done" status.

## Output format

Always lead with the status table. List any inconsistencies found after it. Only if explicitly
asked, close with a one-line recommendation for what `/implement-memory-phase` should tackle next
— this skill reports state, it does not decide or perform the next action.
