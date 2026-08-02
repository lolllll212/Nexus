# NEXUS Architecture Documentation

- [Dual-Loop Architecture](dual-loop.md) — the conscious/subconscious split
- [Clean Architecture & Dependency Rule](clean-architecture.md) — the layering enforced by tests
- [Memory System](memory.md) — synaptic graph + vector + working memory
- [Dreaming Pipeline](dreaming.md) — the 4-phase overnight cycle
- [Self-Evolution](self-evolution.md) — dynamic tool generation
- [Autonomous Goals](autonomous-goals.md) — P2 budget/approval/audit guardrails
- [Swarm](swarm.md) — P4 multi-agent leader/worker orchestration

## Multi-modal I/O (P3)

`/v1/chat` accepts images and audio and can reply in speech:

- **Vision**: `image_urls: ["https://.../a.png"]` are attached to the user turn
  as OpenAI content blocks (`{"type": "image_url", "image_url": {"url": ...}}`).
- **Audio in**: `audio: "data:audio/mpeg;base64,..."` is transcribed via the
  `SpeechToText` port (Whisper) and used as (or prefixed to) the message.
- **Audio out**: `voice: "nova"` synthesizes the response via `TextToSpeech`
  (OpenAI TTS) and returns it as an `audio` data URI.

Ports: `nexus/domain/ports/speech.py` · Adapters: `infrastructure/adapters/speech/` ·
Config: `NEXUS_STT_MODEL`, `NEXUS_TTS_MODEL`, `NEXUS_TTS_VOICE`.

## Swarm (P4)

Multi-agent orchestration over the same brain:

- **Agents**: `POST /v1/agents` registers a persona with its own `system_prompt`
  and a `tools` allowlist (empty = all tools). Listed/scoped per tenant.
- **Swarms**: `POST /v1/swarms` names a leader + workers (all must exist in the
  tenant). `POST /v1/swarms/{id}/run` fans the task out to active workers
  (bounded by `NEXUS_SWARM_MAX_WORKERS`, default 5), then the leader synthesizes
  the final answer from the worker reports.
- **Persona enforcement**: the `SwarmAgentExecutor` injects the agent's system
  prompt as the top-most directive and hides non-allowlisted tools from the
  ReAct loop for the duration of the run.
- **Safety**: missing/paused workers become `(worker unavailable)` placeholders;
  a missing leader fails the swarm (`FAILED`). Auth + rate limiting reuse P1.

Entities: `domain/entities/{agent,swarm}.py` · Ports: `domain/ports/swarm.py` ·
App: `application/swarm/swarm.py` · Infra: `adapters/swarm/` · API: `routes/swarm.py` ·
Config: `NEXUS_SWARM_MAX_WORKERS`.
