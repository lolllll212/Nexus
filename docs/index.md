# NEXUS

A new kind of AI brain - dual-loop architecture with subconscious synthesis,
dreaming, and self-evolution.

## What NEXUS Is

NEXUS is not a chatbot wrapper. It is a cerebral architecture with two loops:

- **The conscious loop** (`/v1/chat`) - a ReAct reasoning engine with tool use,
  multimodal I/O (vision + speech), session-level emotional state, and hybrid
  memory recall (vector + graph).
- **The subconscious loop** - asynchronous synthesis, pattern detection,
  autonomic self-healing, nocturnal dreaming, conscious goal pursuit, and
  multi-agent swarms.

The two loops communicate over an event bus. The cortex never blocks on the
subcortex; the subcortex reshapes memory, tools, and strategies overnight.

## Getting Started

```bash
pip install -e ".[dev]"
uvicorn nexus.infrastructure.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Then:

- `POST /v1/chat` - talk to the conscious engine
- `POST /v1/chat/stream` - watch it think, event by event (SSE)
- `GET /dashboard` - the live brain dashboard
- `POST /v1/system/dream` - trigger a dreaming cycle
- `POST /v1/swarms/{id}/run` - fan a task out to a swarm

### The `nexus` CLI (PyPI package)

```bash
nexus serve                  # run the server (uvicorn)
nexus dream                  # run a dreaming cycle, print the report
nexus train <add|search|...> # coding-training data CLI
```

## Architecture Docs

- [Dual-Loop Architecture](dual-loop.md) - the conscious/subconscious split
- [Clean Architecture & Dependency Rule](clean-architecture.md) - layering
  enforced by tests
- [Memory System](memory.md) - synaptic graph + vector + working memory
- [Dreaming Pipeline](dreaming.md) - the 4-phase overnight cycle
- [Self-Evolution](self-evolution.md) - dynamic tool generation
- [Autonomous Goals](autonomous-goals.md) - P2 budget/approval/audit guardrails
- [Swarm](swarm.md) - P4 multi-agent leader/worker orchestration

## Multi-modal I/O (P3)

`/v1/chat` accepts images and audio and can reply in speech:

- **Vision**: `image_urls: ["https://.../a.png"]` attach as OpenAI content blocks.
- **Audio in**: `audio: "data:audio/mpeg;base64,..."` is transcribed via Whisper.
- **Audio out**: `voice: "nova"` synthesizes the response to an `audio` data URI.

## Swarm (P4)

Multi-agent orchestration over the same brain - register agents with persona
prompts and tool allowlists, name a leader + workers, and run them:

- **Agents**: `POST /v1/agents` registers a persona with its own `system_prompt`
  and a `tools` allowlist (empty = all tools).
- **Swarms**: `POST /v1/swarms` names a leader + workers (all in the tenant).
  `POST /v1/swarms/{id}/run` fans the task out to active workers (bounded by
  `NEXUS_SWARM_MAX_WORKERS`), then the leader synthesizes the final answer.
- **Dashboard**: `GET /v1/memory/graph` renders the synaptic knowledge graph;
  `GET /v1/system/dreams` and `GET /v1/swarms/runs` surface recent activity.