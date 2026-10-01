# Memory System - Synaptic Graph + Vector + Working

## Three Stores, Three Jobs

| Store | Port | `external` adapter | `memory` adapter |
|---|---|---|---|
| **Synaptic Graph** | `ConceptRepository` | `Neo4jConceptRepository` | `InMemoryConceptRepository` |
| **Vector Space** | `MemoryRepository` | `QdrantMemoryRepository` | `InMemoryMemoryRepository` |
| **Working Memory** | `ShortTermMemory` | `RedisShortTermMemory` | `InMemoryShortTermMemory` |

The `memory` column is selected by `NEXUS_INFRA_BACKEND=memory`, which runs the
whole brain with no Redis, Qdrant, or Neo4j. See
[architecture-map.md](architecture-map.md) for every port and its binding.

## Neuroplasticity (Hebbian Learning)

The graph is not static. Every access strengthens; every silence decays.

- `Concept.strengthen(amount)` - accessed concepts get heavier.
- `SynapticConnection.reinforce(amount)` - co-occurring concepts wire tighter.
- `Concept.decay(rate)` / `SynapticConnection.decay(rate)` - ignored paths weaken.
- Below `min_weight`, a synapse is pruned. Below `min_strength`, a concept is pruned.
  Both floors come from `SynapseConfig` (`domain/value_objects/synapse.py`).

This is why retrieval stays fast forever: the active vector space is kept lean by
constant pruning, and the graph continuously reshapes around what you actually use.

## Memory Taxonomy

| Type | Meaning | Example | Consolidation |
|---|---|---|---|
| `EPISODIC` | Raw experiences | "user: my deploy failed" | becomes semantic during dreaming |
| `SEMANTIC` | Abstract facts | "user prefers Vercel" | kept |
| `PROCEDURAL` | Skills/capabilities | verified dream solutions | kept |
| `EMOTIONAL` | Weighted associations | `EmotionalWeight` on a memory | prioritized |

## Contextual Fluidity

Every `Memory` carries a `context_state` snapshot - the emotional state and active
task at the moment it was created. `Conversation` tracks `EmotionalState` (valence,
arousal, dominant emotion). This is the seed for "remembering not just what you said,
but the state of mind in which you said it."

## Hybrid Recall

`ProcessMessageUseCase._recall()` runs two paths concurrently with
`asyncio.gather` and merges them:

1. **Vector recall** - embed the query, search for semantically similar memories.
2. **Graph recall** - for each of the first 5 active concepts, fetch
   `ConceptRepository.get_memories(cid)` (up to 3 memories) and walk the first 2
   concepts' connections.

Every synapse a traversal travels is `reinforce()`d in a **background task** -
recall never blocks on a write. Accesses are recorded the same way
(`record_access` per memory), so a slow store cannot delay a reply.

Results are de-duplicated by id, capped at `MEMORY_RECALL_LIMIT = 8`, and
injected into the ReAct context as a system message.

> Graph traversal returning `Concept` objects is not enough on its own - it has to
> return the **memories** attached to those concepts, or the whole path is wasted.
> That is why `ConceptRepository.get_memories()` exists as an explicit port method.
> See "Critical Bugs Fixed" in `AGENTS.md`.

## Memory Quota

`NEXUS_QUOTA_MEMORIES_PER_DAY` caps how many memories a tenant can encode per
day (0 = unlimited, the default). The check happens in
`ProcessMessageUseCase._encode_episodic()` and **fails soft**: when the quota is
exhausted the exchange is still answered, but it is simply not encoded, and
`memory_quota_skips_total{tenant_id}` is incremented. A tenant can never silently
balloon the vector space, and no user ever sees an error because of it.

## Quotas and Rate Limits at a Glance

| Var | Resource | Default | Enforced in |
|---|---|---|---|
| `NEXUS_QUOTA_CHAT_PER_DAY` | `chat` | `0` (unlimited) | chat route |
| `NEXUS_QUOTA_TOOL_GEN_PER_DAY` | `tool_gen` | `0` (unlimited) | tool-generation route |
| `NEXUS_QUOTA_MEMORIES_PER_DAY` | `memories` | `0` (unlimited) | `_encode_episodic()` |
| `NEXUS_CHAT_RATE_LIMIT` | sliding window | per `Config` | chat route |
| `NEXUS_RATE_LIMIT_WINDOW_SECONDS` | window width | per `Config` | rate limiter |

All daily quotas share one implementation: `RateLimitQuota` wrapping the
`RateLimiter` port, with a per-tenant key and a rolling 24h window. Because it
goes through `RateLimiter`, quotas survive in Redis under `external` and work
in-process under `memory`.

## The only sanctioned clock

`domain/value_objects/clock.py::utc_now()`. Use it instead of
`datetime.datetime.utcnow()`, which is deprecated on Python 3.13+. `clock.py` is
the one "value object" module with no classes - it exists so the domain layer
has one place to hide the deprecation.

## See also

- [Architecture Map](architecture-map.md) - the three memory ports and their adapters
- [Dreaming Pipeline](dreaming.md) - what compresses and prunes this data
- [Backup & DR](backup-dr.md) - keeping the graph and vectors recoverable
