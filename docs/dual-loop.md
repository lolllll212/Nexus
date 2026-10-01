# Dual-Loop Architecture

## The Problem With Reactive AI

Standard AI waits in a coma: it wakes for a prompt, computes, and sleeps again.
A brain must have **two concurrently-running loops**.

```
                     ┌──────────────────────────┐
                     │      NEXUS SYSTEM         │
                     └───────────┬──────────────┘
                                 │
              ┌──────────────────┴──────────────────┐
              │                                     │
   ┌──────────▼──────────┐              ┌───────────▼──────────┐
   │   CORTEX             │              │   SUBCORTEX          │
   │   (Conscious)        │              │   (Subconscious)     │
   │   Fast-Twitch        │              │   Slow-Twitch        │
   │   sub-second         │              │   continuous         │
   │                      │              │                      │
   │   FastAPI /v1/chat   │              │   Celery workers     │
   │   ReAct loop         │              │   Entity synthesis   │
   │   Tool execution     │              │   Pattern detection  │
   │   Working memory     │              │   Dreaming (3 AM)    │
   └──────────┬───────────┘              └───────────┬──────────┘
              │                                      │
              │      EVENT BUS (EventBus port)       │
              │  ─────────── nervous system ───────  │
              └──────────── USER_MESSAGE ───────────►│
              ◄──────── CONTEXT_INJECTION ───────────┘
              ◄──────────── KNOWLEDGE_UPDATED ───────┘
```

## The Nervous System: Event Bus

The cortex and subcortex never call each other directly. They communicate
through the `EventBus` port. This is what provides **zero blocking**:

1. User sends a message -> `ProcessMessageUseCase` executes the ReAct loop.
2. **In parallel (fire-and-forget)**: it publishes `USER_MESSAGE` to the bus.
3. The `SubconsciousCoordinator` (running in the subcortex) receives it and
   kicks off synthesis - entity extraction, graph updates, cross-referencing.
4. If the subcortex discovers a strong, non-obvious connection, it publishes
   `CONTEXT_INJECTION`, and the cortex receives a sudden "realization."

Neither loop awaits the other. Ever.

## The ReAct Loop (what the cortex actually does)

`application/cortex/process_message.py::_react_loop()`, capped at
`MAX_REACT_ITERATIONS = 15`:

```
build context (persona -> tone -> recalled memories -> ReAct prompt -> tool catalog)
  │
  ├─ compact old observations if over SUMMARY_TRIGGER_TOKENS (10k est. tokens)
  │     └─ if still over MAX_CONTEXT_TOKENS (12k): synthesize and stop
  │
  ├─ LLM.complete(context)
  │     └─ LLMUnavailableError -> deterministic offline fallback, no exception escapes
  │
  ├─ 1. PARSE TOOL_CALL FIRST                       ← order matters
  │     └─ InvalidToolCallError -> feed the syntax error back, let the model retry
  │
  ├─ 2. no tool call? -> is it a FINAL ANSWER?
  │     ├─ yes -> return
  │     └─ no  -> feed the reasoning back and nudge it to act
  │
  ├─ 3. LOOP GUARD: sha256(tool_id, sorted params)
  │     └─ identical 3x in a row -> force a synthesized answer, stop
  │
  └─ 4. ACT -> observe inside <tool_output> -> append BOTH the model's
        TOOL_CALL (assistant) and the observation (user), so the model can
        actually pair its action with its result
```

Three invariants worth knowing, all covered by
`tests/eval/test_react_guard.py`:

- **Parsing beats answering.** A turn containing both `TOOL_CALL:` and
  `FINAL ANSWER:` acts. Otherwise a model that narrates its plan and *then*
  decides to answer would never use a tool.
- **The guard forces, it does not nudge.** Small local models ignore
  suggestions, so the third identical `(tool_id, params)` ends the loop with a
  synthesized answer from whatever observations exist.
- **Observations are data, not instructions.** Tool output is wrapped in
  `<tool_output>` and every control-flow token inside it (`TOOL_CALL:`,
  `FINAL ANSWER:`, `</tool_output>`, `[OBSERVATION`) is disarmed on ingest.
  Prompt framing alone is not a boundary: a model that faithfully echoes an
  injected `TOOL_CALL:` would otherwise re-enter the loop as the attacker.

## Two LLM Slots

The container builds **two** `LLMProvider`s:

| Slot | Used by | Configured by |
|---|---|---|
| Primary | chat, tool generation, self-heal, swarm agents | `NEXUS_LLM_BASE_URL`, `NEXUS_LLM_MODEL`, `NEXUS_LLM_PROVIDER` |
| Background | entity synthesis, pattern detection, dreaming (compress/simulate) | `NEXUS_BACKGROUND_LLM_BASE_URL`, `NEXUS_BACKGROUND_LLM_MODEL`, `NEXUS_BACKGROUND_LLM_API_KEY` |

Background work falls back to the primary model when unset, so a cheap local
model can serve the user while a stronger one does the nightly thinking.

## Separation of Concerns

| Concern | Lives in |
|---|---|
| Routing, HTTP, serialization | `infrastructure/api/` (18 route modules) |
| ReAct reasoning, memory recall | `application/cortex/process_message.py` |
| Reasoning rules and tool format | `application/cortex/react_prompt.py` |
| Background synthesis | `application/subcortex/synthesis.py` |
| Overnight optimization | `application/subcortex/dreaming/` |
| Event routing | `domain/ports/event_bus.py` + `infrastructure/adapters/eventbus/` |
| What a Memory/Concept/Tool is | `domain/entities/` |
| Which adapter implements which port | `infrastructure/di/container.py` |

## Scaling Independently

- The **cortex** (chat API) is cheap - deploy on a small Vercel/Railway instance.
- The **subcortex** (workers) needs compute - run on GPU servers that wake only
  for synthesis bursts and the 3 AM dream cycle.
- Docker Compose ships them as separate services (`nexus-cortex`, `nexus-worker`,
  `nexus-beat`).

## Running Without Any Infrastructure

The event bus, rate limiter, embedder, and all three memory stores have
in-process implementations. Setting

```bash
NEXUS_INFRA_BACKEND=memory
```

swaps all six for `InMemory*` adapters: no Redis, no Qdrant, no Neo4j, no
embedding endpoint. The same flag is what the nightly eval uses, and it is the
fastest way to run the suite locally. Full port->adapter table in
[architecture-map.md](architecture-map.md); backups in
[backup-dr.md](backup-dr.md).

Note that the event bus and working memory are then process-local: background
workers cannot see the API process's events, and nothing survives a restart.
That is the intended trade for dev, CI, and eval runs - not for production.

## See also

- [Architecture Map](architecture-map.md) - every port and its adapter
- [Clean Architecture & Dependency Rule](clean-architecture.md)
- [Memory System](memory.md)
- [Dreaming Pipeline](dreaming.md)
