# Dreaming - Deep Batch Optimization

The brain "sleeps" at 3 AM. `Celery beat` fires `dreaming.run`, which executes
`DreamSessionUseCase` - four phases in sequence.

The hour is configurable: `NEXUS_DREAM_HOUR` (default `3`).

## Phase 1: Compression (Episodic -> Semantic)

`application/subcortex/dreaming/compress.py`

The day's raw episodic transcripts are batched and sent to the **background** LLM
with one instruction: *"Consolidate into durable, abstract facts about the user,
their projects, preferences, and recurring problems."* The distilled facts are
stored as `SEMANTIC` memories. Originals are flagged `consolidated=True` for cold
storage.

## Phase 2: Pruning (Forgetting)

`application/subcortex/dreaming/prune.py`

The #1 killer of RAG systems is vector-space bloat. This phase:

- Finds memories unaccessed for more than the staleness window and **deletes
  them** (the vector space stays lean).
- Applies exponential decay to every synapse, then prunes those below the
  strength floor from `SynapseConfig`.

## Phase 3: Simulation (Solving Tomorrow Tonight)

`application/subcortex/dreaming/simulate.py`

The most advanced part. It scans unresolved problems from the day, asks the LLM to
write candidate solutions, and **runs them in the sandbox overnight**. Verified
solutions are stored as `PROCEDURAL` memory and pushed to working memory under
`dream:findings`. When you wake up, the answer is already waiting.

Phase 3 is the one that touches the `Sandbox` port, so it inherits the Docker
default - an unverified candidate solution never runs unsandboxed. Set
`NEXUS_SANDBOX_BACKEND=subprocess` to trade isolation for speed on a trusted
host.

## Phase 4: Consolidation (Strengthening Core Knowledge)

`application/subcortex/dreaming/consolidate.py`

Identifies clusters of frequently-used concepts (the brain's "core knowledge") and
reinforces the connections inside them, so the most important pathways become
faster and more robust to decay.

## Lifecycle

```
DREAM_TRIGGERED --> Compression --> Pruning --> Simulation --> Consolidation --> DREAM_COMPLETED
     |                                                                               |
     +--------------- event bus (EventBus port) -------------- knowledge.updated ----+
                                   |
                       Celery beat (NEXUS_DREAM_HOUR)                       cortex
```

## Manual Trigger

```bash
# via the CLI
python -m nexus dream
python -m nexus dream --local      # in-process, NEXUS_INFRA_BACKEND=memory

# via the API
curl -X POST http://localhost:8000/v1/system/dream
```

## Measuring Whether It Worked

`DreamSessionResult` reports the before/after recall delta:

```
DreamSessionResult
  .compressed / .pruned / .simulated / .consolidated   # per-phase counts
  .recall_delta                                       # float | None
  .duration_seconds
```

`recall_delta` is `None` when there were no probes to measure against, so a
`None` is a skipped measurement, not a regression. The API surfaces recent runs
at `GET /v1/system/dreams`.

## Running the Dream Cycle Without Infrastructure

Every phase is pure application logic over ports, so the whole thing runs
in-process with no Redis, Qdrant, or Neo4j:

```bash
NEXUS_INFRA_BACKEND=memory python -m nexus dream --local
```

That is also the mode the eval harness and `pytest tests/unit/` use. It is
process-local, though: nothing survives the run, and the graph is empty on the
next start. Use `external` if you want the memories to still be there tomorrow.

## Ordering Guarantee

The four phases run strictly in order, and each one's output feeds the next.
Compression before pruning is not cosmetic - pruning first would delete the
episodic records the compressor has not yet distilled. Simulation runs after
pruning so the solver sees a lean graph, and consolidation runs last so the
synapses strengthened by a successful simulation are not immediately decayed.

## See also

- [Memory System](memory.md) - what is being compressed and pruned
- [Self-Evolution](self-evolution.md) - what the `PROCEDURAL` results feed
- [Architecture Map](architecture-map.md) - the `Sandbox` and memory ports
