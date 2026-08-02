# Dreaming — Deep Batch Optimization

The brain "sleeps" at 3 AM. `Celery beat` fires `dreaming.run`, which executes
`DreamSessionUseCase` — four phases in sequence.

## Phase 1: Compression (Episodic → Semantic)

`application/subcortex/dreaming/compress.py`

The day's raw episodic transcripts are batched and sent to the LLM with one
instruction: *"Consolidate into durable, abstract facts about the user, their
projects, preferences, and recurring problems."* The distilled facts are stored as
`SEMANTIC` memories. Originals are flagged `consolidated=True` for cold storage.

## Phase 2: Pruning (Forgetting)

`application/subcortex/dreaming/prune.py`

The #1 killer of RAG systems is vector-space bloat. This phase:
- Finds memories unaccessed for >90 days → **deletes them** (the vector space stays lean).
- Applies exponential decay to every synapse → prunes those below the strength floor.

## Phase 3: Simulation (Solving Tomorrow Tonight)

`application/subcortex/dreaming/simulate.py`

The most advanced part. It scans unresolved problems from the day, asks the LLM to
write candidate solutions, and **runs them in the sandbox overnight**. Verified
solutions are stored as `PROCEDURAL` memory and pushed to working memory as
`dream:findings`. When you wake up, the answer is already waiting.

## Phase 4: Consolidation (Strengthening Core Knowledge)

`application/subcortex/dreaming/consolidate.py`

Identifies clusters of frequently-used concepts (the brain's "core knowledge") and
reinforces the connections inside them, so the most important pathways become
faster and more robust to decay.

## Lifecycle

```
DREAM_TRIGGERED ──► Compression ──► Pruning ──► Simulation ──► Consolidation ──► DREAM_COMPLETED
     ▲                                                                               │
     │                                                                               ▼
  Celery beat (03:00 UTC)                                              knowledge.updated → cortex
```

## Manual Trigger

```bash
curl -X POST http://localhost:8000/v1/system/dream
```
