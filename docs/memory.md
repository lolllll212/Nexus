# Memory System — Synaptic Graph + Vector + Working

## Three Stores, Three Jobs

| Store | Adapter | Role |
|---|---|---|
| **Synaptic Graph** | `Neo4jConceptRepository` | Concepts as nodes, weighted connections as edges |
| **Vector Space** | `QdrantMemoryRepository` | Semantic similarity search over memory fragments |
| **Working Memory** | `RedisShortTermMemory` | Ephemeral session context, wiped daily |

## Neuroplasticity (Hebbian Learning)

The graph is not static. Every access strengthens; every silence decays.

- `Concept.strengthen(amount)` — accessed concepts get heavier.
- `SynapticConnection.reinforce(amount)` — co-occurring concepts wire tighter.
- `Concept.decay(rate)` / `SynapticConnection.decay(rate)` — ignored paths weaken.
- Below `min_weight`, a synapse is pruned. Below `min_strength`, a concept is pruned.

This is why retrieval stays fast forever: the active vector space is kept lean by
constant pruning, and the graph continuously reshapes around what you actually use.

## Memory Taxonomy

| Type | Meaning | Example | Consolidation |
|---|---|---|---|
| `EPISODIC` | Raw experiences | "Ashutosh: my deploy failed" | → consolidated into semantic |
| `SEMANTIC` | Abstract facts | "Ashutosh prefers Vercel" | kept |
| `PROCEDURAL` | Skills/capabilities | verified dream solutions | kept |
| `EMOTIONAL` | Weighted associations | `EmotionalWeight` on a memory | prioritized |

## Contextual Fluidity

Every `Memory` carries a `context_state` snapshot — the emotional state and active
task at the moment it was created. `Conversation` tracks `EmotionalState` (valence,
arousal, dominant emotion). This is the seed for "remembering not just what you said,
but the state of mind in which you said it."

## Hybrid Recall

`ProcessMessageUseCase._recall()` merges two paths:
1. **Vector recall** — embed the query, search Qdrant for semantically similar memories.
2. **Graph recall** — from each active concept, traverse strong connections to related
   concepts and their memories. Every traversal *reinforces* the synapse it travels.

Results are de-duplicated, ranked, and injected into the ReAct context.
