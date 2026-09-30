# Clean Architecture & The Dependency Rule

## Why This Is the Mandatory First Step

A dual-loop brain means simultaneous processes: live chat vs. background thinking.
Without rigid boundaries you get race conditions, memory collisions, and a codebase
that's unmaintainable. The rules below are enforced and proven by the test suite.

## The Four Layers

```
Entry Points (FastAPI, Celery)
        │  calls
        ▼
Application Layer (use cases)
        │  depends only on
        ▼
Domain Ports (interfaces)
        │  implemented by
        ▼
Infrastructure (adapters)
```

And below the ports sits the pure **Domain Core** (entities, value objects) which
nothing outside the domain may depend on, and which depends on nothing.

### 1. Domain Core — `src/nexus/domain/`

Pure Python. **Zero imports from application, infrastructure, or any framework.**
`Memory`, `Concept`, `SynapticConnection`, `Thought`, `Tool`, `Conversation`,
`EmotionalState`, `JSONSchema`, `SynapseConfig`.

- `Memory.consolidate()` produces semantic memory from episodic (dreaming phase 1).
- `Concept.strengthen()` / `Concept.decay()` implement Hebbian neuroplasticity.
- `SynapticConnection.reinforce()` / `.decay()` implement synaptic strength/decay.

### 2. Domain Ports — `src/nexus/domain/ports/`

The interfaces the application needs. Naming them "ports" is deliberate — they are
the seams where technologies plug in:

| Port | What it abstracts |
|---|---|
| `LLMProvider` | GPT-4o today, Llama 3 tomorrow |
| `EmbeddingProvider` | Any embedding model |
| `MemoryRepository` | Qdrant, Pinecone, pgvector |
| `ConceptRepository` | Neo4j, Memgraph, ArangoDB |
| `ShortTermMemory` | Redis, Memcached |
| `EventBus` | Redis Pub/Sub, Kafka, NATS |
| `ToolRegistry` | Any registry storage |
| `ToolExecutor` | Tool dispatch strategy |
| `DeploymentProvider` | Local, Railway, Vercel, AWS Lambda |
| `Sandbox` | Subprocess, Docker, Firecracker |

### 3. Application Layer — `src/nexus/application/`

Use cases orchestrate the brain. **No I/O, no HTTP, no frameworks.** Everything is
injected. `ProcessMessageUseCase` does ReAct; `DreamSessionUseCase` runs the 4 phases;
`GenerateToolUseCase` is the self-evolution.

### 4. Infrastructure — `src/nexus/infrastructure/`

Concrete adapters, FastAPI routes, Celery workers, and the DI container.
**The container is the only place technology is decided.**

## The Proof

```python
# Swap the entire brain's infrastructure without touching application code:
#   domain/application import with ZERO packages installed (verified)
#   14 tests run against in-memory fakes (tests/fakes/) - no Redis/Neo4j/OpenAI
```

To swap Redis → Kafka: write `KafkaEventBus(EventBus)` and change one factory in
`container.py`. To swap OpenAI → Llama: write `LlamaProvider(LLMProvider)`, one line.

## Anti-patterns this prevents

- ❌ Background workers tangling with live chat state → ✅ event bus isolation
- ❌ Frameworks leaking into business logic → ✅ ports/adapters
- ❌ Database client imports in use cases → ✅ repositories injected
- ❌ LLM SDK calls scattered everywhere → ✅ single provider adapter
