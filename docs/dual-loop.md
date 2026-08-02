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
   │   FastAPI /v1        │              │   Celery workers     │
   │   ReAct loop         │              │   Entity synthesis   │
   │   Tool execution     │              │   Pattern detection  │
   │   Working memory     │              │   Dreaming (3 AM)    │
   └──────────┬───────────┘              └───────────┬──────────┘
              │                                      │
              │      EVENT BUS (Redis Pub/Sub)       │
              │  ─────────── nervous system ───────  │
              └──────────── USER_MESSAGE ───────────►│
              ◄──────── CONTEXT_INJECTION ───────────┘
              ◄──────────── KNOWLEDGE_UPDATED ───────┘
```

## The Nervous System: Event Bus

The cortex and subcortex never call each other directly. They communicate
through the `EventBus` port. This is what provides **zero blocking**:

1. User sends a message → `ProcessMessageUseCase` executes the ReAct loop.
2. **In parallel (fire-and-forget)**: it publishes `USER_MESSAGE` to the bus.
3. The `SubconsciousCoordinator` (running in the subcortex) receives it and
   kicks off synthesis — entity extraction, graph updates, cross-referencing.
4. If the subcortex discovers a strong, non-obvious connection, it publishes
   `CONTEXT_INJECTION`, and the cortex receives a sudden "realization."

Neither loop awaits the other. Ever.

## Separation of Concerns

| Concern | Lives in |
|---|---|
| Routing, HTTP, serialization | `infrastructure/api/` |
| ReAct reasoning, memory recall | `application/cortex/process_message.py` |
| Background synthesis | `application/subcortex/synthesis.py` |
| Overnight optimization | `application/subcortex/dreaming/` |
| Event routing | `domain/ports/event_bus.py` + `infrastructure/adapters/eventbus/` |
| What a Memory/Concept/Tool is | `domain/entities/` |

## Scaling Independently

- The **cortex** (chat API) is cheap — deploy on a small Vercel/Railway instance.
- The **subcortex** (workers) needs compute — run on GPU servers that wake only
  for synthesis bursts and the 3 AM dream cycle.
- Docker Compose ships them as separate services (`nexus-cortex`, `nexus-worker`, `nexus-beat`).
