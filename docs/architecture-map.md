# Architecture Map

Every port, entity, and value object, and the concrete adapter the DI container
binds to each one. **Generated from the code, not from memory** — the
port→adapter table is cross-checked by
[`tests/eval/test_architecture_map.py`](../tests/eval/test_architecture_map.py),
which fails if the container drifts from this page.

Source of truth for the bindings: `src/nexus/infrastructure/di/container.py`
(one `_build_*` method per port). Swap an adapter by editing that file and
nothing else.

## Layers

```
src/nexus/
  domain/          pure entities + value objects + ports    (zero imports from the layers above)
  application/     use cases, depends only on ports
  infrastructure/  adapters, FastAPI routes, DI container, workers, CLI
  eval/            golden-set harness shared by pytest and the nightly job
  training/        coding-training CLI + store
```

`domain/` never imports `application/` or `infrastructure/`. Enforced in CI by
import-linter (`.github/workflows/importlinter.toml`) and by
`tests/unit/test_domain_clean_architecture.py`.

## Ports (18 modules, 28 abstract types)

`NEXUS_INFRA_BACKEND` selects a column. Only six ports branch on it.

Class names in the adapter columns are the only thing the container source is
checked against, so env-var names are deliberately left un-backticked here —
they are read by the `Config` dataclass at the top of `container.py`, not by
the `Container` class. See [Ops configuration](#ops-configuration).

| Port (module) | Abstract type | `external` (default) | `memory` |
|---|---|---|---|
| `ports/secrets.py` | `SecretStore` | `EnvSecretStore`, or `ChainedSecretStore` over `JsonFileSecretStore` when NEXUS_SECRET_BACKEND is set to json:<path> | same |
| `ports/auth.py` | `Authenticator` | `ApiKeyAuthenticator` | same |
| `ports/observability.py` | `Tracer` | `OTELTracer` if `config.otel_enabled`, else `LoggingTracer` | same |
| `ports/observability.py` | `Metrics` | `OTELMetrics` if `config.otel_enabled`, else `InMemoryMetrics` | same |
| `ports/activity_feed.py` | `ActivityFeed` | `InMemoryActivityFeed` | same |
| `ports/rate_limiter.py` | `RateLimiter` | `RedisRateLimiter` | `InMemoryRateLimiter` |
| `ports/quota.py` | `QuotaService` | `RateLimitQuota` (wraps `RateLimiter`) | same |
| `ports/event_bus.py` | `EventBus` (`EventPublisher` + `EventSubscriber`) | `RedisEventBus` | `InMemoryEventBus` |
| `ports/llm_provider.py` | `EmbeddingProvider` | `OpenAIEmbedder` | `InMemoryEmbedder` |
| `ports/llm_provider.py` | `LLMProvider` (primary) | `OpenAIProvider`, or `NvidiaNimProvider` if `config.llm_provider` is `nvidia`/`nim` | same |
| `ports/llm_provider.py` | `LLMProvider` (background) | `OpenAIProvider` with its own base URL / model / key | same |
| `ports/llm_provider.py` | `StreamingLLMProvider` | capability of `OpenAIProvider`; not bound separately | — |
| `ports/speech.py` | `SpeechToText` | `OpenAISpeechToText` | same |
| `ports/speech.py` | `TextToSpeech` | `OpenAITextToSpeech` | same |
| `ports/sandbox.py` | `Sandbox` | `DockerSandbox` (default), `SubprocessSandbox` if `config.sandbox_backend` is `subprocess` | same |
| `ports/memory_repository.py` | `MemoryRepository` | `QdrantMemoryRepository` | `InMemoryMemoryRepository` |
| `ports/memory_repository.py` | `ConceptRepository` | `Neo4jConceptRepository` | `InMemoryConceptRepository` |
| `ports/memory_repository.py` | `ShortTermMemory` | `RedisShortTermMemory` | `InMemoryShortTermMemory` |
| `ports/tool_registry.py` | `ToolRegistry` | `BuiltinToolRegistry(default_builtin_tools())` | same |
| `ports/execution.py` | `ToolExecutor` | `RegistryBackedToolExecutor` (+ `PluginLoader` over `config.plugins_dir`) | same |
| `ports/deployment.py` | `DeploymentProvider` | `RailwayDeployer` / `VercelDeployer` by `config.deploy_platform`, else `LocalDeployer` | same |
| `ports/cognition.py` | `CorticalColumnRegistry` | `InMemoryCorticalColumnRegistry` | same |
| `ports/cognition.py` | `ActionPolicyStore` | `InMemoryActionPolicyStore` | same |
| `ports/goal_repository.py` | `GoalRepository` | `InMemoryGoalRepository` | same |
| `ports/autonomy.py` | `AutonomyPolicy` | `DefaultAutonomyPolicy` | same |
| `ports/swarm.py` | `AgentRepository` | `InMemoryAgentRepository` | same |
| `ports/swarm.py` | `SwarmRepository` | `InMemorySwarmRepository` | same |

### Sandbox wiring and socket profile

`ports/sandbox.py` binds `DockerSandbox` by default for secure, ephemeral container execution.
In containerized environments (Docker Compose), the hardened Docker sandbox requires
mounting `/var/run/docker.sock` via the explicit opt-in `docker-sandbox` profile
(e.g., `docker compose --profile docker-sandbox up`).
If `NEXUS_SANDBOX_BACKEND` is unset in a container without socket access, the DI composition root
logs a LOUD warning and deliberately falls back to `SubprocessSandbox`.
To silence the warning and explicitly select subprocess sandboxing, set `NEXUS_SANDBOX_BACKEND=subprocess`.

Ports with **no** external variant (`memory` column = `external` column): the
`memory` backend exists to remove Redis/Qdrant/Neo4j from local dev, CI, and
evals, so anything that was already in-process stays in-process.

### Port count by concern

| Concern | Ports |
|---|---|
| Reasoning | `LLMProvider`, `StreamingLLMProvider`, `EmbeddingProvider` |
| Memory | `MemoryRepository`, `ConceptRepository`, `ShortTermMemory` |
| Tools | `ToolRegistry`, `ToolExecutor`, `DeploymentProvider`, `Sandbox` |
| Messaging | `EventPublisher`, `EventSubscriber`, `EventBus` |
| Autonomy | `GoalRepository`, `AutonomyPolicy`, `CorticalColumnRegistry`, `ActionPolicyStore` |
| Multi-agent | `AgentRepository`, `SwarmRepository` |
| Security | `Authenticator`, `SecretStore`, `RateLimiter`, `QuotaService` |
| Ops | `Tracer`, `Metrics`, `ActivityFeed` |
| Multimodal | `SpeechToText`, `TextToSpeech` |

## Entities (9 modules)

`domain/entities/` — mutable, behaviour-carrying, no I/O.

| Module | Types |
|---|---|
| `agent.py` | `Agent`, `AgentStatus` |
| `concept.py` | `Concept`, `SynapticConnection` |
| `conversation.py` | `Conversation`, `Session`, `Message`, `MessageRole` |
| `cortex.py` | `CorticalColumn` |
| `goal.py` | `Goal`, `GoalStep`, `GoalEvent`, `GoalStatus`, `GoalPriority`, `StepStatus` |
| `memory.py` | `Memory`, `EmotionalWeight`, `MemoryType` |
| `swarm.py` | `Swarm`, `SwarmResult`, `SwarmStatus` |
| `thought.py` | `Thought`, `ThoughtType` |
| `tool.py` | `Tool`, `ToolStatus` |

## Value objects (9 modules)

`domain/value_objects/` — immutable, compared by value.

| Module | Types |
|---|---|
| `clock.py` | `utc_now()` (the only sanctioned clock — avoids the `utcnow()` deprecation) |
| `emotion.py` | `EmotionalState` |
| `hex_fourier.py` | `HexCoord`-space `AxisSpectrum`, `HexSpectrum` |
| `hex_grid.py` | `HexCoord`, `HexGrid` |
| `hex_index.py` | `HexIndex` |
| `identity.py` | `Identity`, `Role` |
| `schema.py` | `JSONSchema` |
| `synapse.py` | `SynapseConfig`, `ConnectionType` |
| `valence.py` | `ValenceTag` |

## Built-in tools (27)

Registered by `BuiltinToolRegistry(default_builtin_tools())`; handlers live in
`infrastructure/adapters/execution/extended_tools.py`.

`web_search`, `web_fetch`, `calculator`, `run_python`, `run_shell`, `read_file`,
`write_file`, `list_directory`, `json_query`, `json_transform`,
`current_datetime`, `diff_text`, `hash_text`, `base64_encode`, `git_info`,
`http_request`, `grep`, `system_info`, `find_databases`, `query_database`,
`process_multimodal_media`, `pytest_runner`, `csv_query`, `memory_graph_query`,
`code_search_semantic`, `dependency_audit`, `regex_extract`.

Two of these exist specifically so the ReAct prompt can tell the agent to act
on its own: `find_databases` scans a tree for `.sqlite`/`.db` files and
`docker-compose`/`.env` connection config; `query_database` speaks
sqlite/postgres/mysql/redis.

## API route modules (18)

`infrastructure/api/routes/`: `chat`, `memory`, `tools`, `coding`, `goals`,
`swarm`, `graph`, `system`, `telemetry`, `research`, `analyze`, `workflows`,
`mcp`, `multimodal`, `audio`, `nim`, `integrations`, `coding_assistant`.

## Wiring summary by module

| Layer | Modules |
|---|---|
| `application/cortex/` | `process_message` (ReAct loop), `react_prompt`, `session_manager` |
| `application/subcortex/` | `synthesis`, `pattern_detection`, `thalamus`, `basal_ganglia`, `amygdala`, `dreaming/{dream_session,compress,prune,simulate,consolidate}`, `spatial/{fourier_router,grid_cells,hex_scaling}` |
| `application/autonomy/` | `goals` |
| `application/swarm/` | `swarm` |
| `application/tools/` | `generate_tool`, `self_heal`, `multimodal_perception` |
| `application/interfaces/` | `subconscious_coordinator` |
| `infrastructure/adapters/` | `auth`, `autonomy`, `cognition`, `eventbus`, `execution`, `inmemory`, `llm`, `observability`, `persistence`, `sandbox`, `security`, `speech`, `swarm`, `embedding` |
| `infrastructure/api/` | `main`, `dependencies`, `routes/` (18), `schemas` |
| `infrastructure/workers/` | Celery tasks + beat schedule (`dream`, `autonomy_loop`, `pattern_detection`, `entity_synthesis`) |
| `infrastructure/backup/` | `QdrantBackup`, `Neo4jBackup`, `BackupManager` |
| `infrastructure/di/` | `container.py` — the only place adapters are chosen |

## Ops configuration

Every knob below is read once at startup (default in brackets) — most by the
`Config` dataclass at the top of `container.py`, the rest by the adapter that
needs them (`NEXUS_OTEL_ENDPOINT` by the OTEL exporter, `NEXUS_WORKSPACE_ROOT`
by the file tools, `NEXUS_SECRET_BACKEND` by `_build_secret_store`).
`.env` is gitignored: copy `.env.example` to `.env`.

This table is not maintained by hand.
[`tests/eval/test_docs_env_vars.py`](../tests/eval/test_docs_env_vars.py) fails
if the code reads a variable this page does not mention, or if this page
mentions a variable the code never reads.

| Variable | Effect |
|---|---|
| `NEXUS_INFRA_BACKEND` | `external` (default): Redis / Qdrant / Neo4j / OpenAI embeddings. `memory`: fully in-process adapters, for offline dreaming, evals and CI. |
| `NEXUS_SECRET_BACKEND` | `env` (default), or `json:<path>` to chain a JSON-file secret store in front of the env store. |
| `NEXUS_QUOTA_CHAT_PER_DAY` | Per-tenant daily chat-message cap (`0` = unlimited), enforced by `RateLimitQuota` over `RateLimiter`. |
| `NEXUS_QUOTA_TOOL_GEN_PER_DAY` | Per-tenant daily generated-tool cap (`0` = unlimited). |
| `NEXUS_QUOTA_MEMORIES_PER_DAY` | Per-tenant daily memory-write cap (`0` = unlimited). |
| `NEXUS_GOALS_MAX_ACTIVE` | Ceiling on simultaneously active autonomous goals (`10`), enforced in `CreateGoalUseCase`. |
| `NEXUS_SANDBOX_BACKEND` | `docker` (default) or `subprocess`. |
| `NEXUS_OTEL_ENABLED` | `true` binds `OTELTracer` + `OTELMetrics`; otherwise the logging / in-memory pair. |
| `NEXUS_LLM_PROVIDER` | `openai` (default), or `nvidia`/`nim` for `NvidiaNimProvider`. |
| `NEXUS_LLM_BASE_URL` | Points the OpenAI-compatible adapters at a local server (LM Studio, Ollama). |
| `NEXUS_API_KEYS` | JSON map of key to `{user_id, tenant_id, role}`. Empty means fail-closed: every request gets 401. |
| `NEXUS_TENANTS` | Comma-separated tenant ids; each one gets its memory collection pre-created at startup. |

### Models and providers

| Variable | Effect |
|---|---|
| `NEXUS_LLM_MAX_TOKENS` | Max tokens per completion (`8192`). |
| `NEXUS_NVIDIA_API_KEY` | Key for the `nvidia`/`nim` provider; falls back to `NVIDIA_API_KEY` then `NIM_API_KEY`. |
| `NEXUS_EMBEDDING_MODEL` | Embedding model name (`text-embedding-3-large`). |
| `NEXUS_EMBEDDING_BASE_URL` | Base URL for the embedding provider, for a local server. |
| `NEXUS_EMBEDDING_DIMENSION` | Embedding vector width (`1536`); must match what the model actually returns. |
| `NEXUS_OTEL_ENDPOINT` | OTLP endpoint for traces and metrics (`http://localhost:4317`). |

### Limits, tenancy and plumbing

| Variable | Effect |
|---|---|
| `NEXUS_TOOL_GEN_RATE_LIMIT` | Tool-generation requests allowed per window (`20`). |
| `NEXUS_RATE_LIMIT_FAIL_CLOSED` | `true` rejects on rate-limiter backend failure instead of allowing. |
| `NEXUS_PATTERN_INTERVAL_SECONDS` | Seconds between pattern-detection runs (`1800`). |
| `NEXUS_PLUGINS_DIR` | Directory scanned by `PluginLoader` (`plugins`). |
| `NEXUS_WORKSPACE_ROOT` | Root directory the file tools are confined to (`.`). |
| `NEXUS_WEBHOOK_URL` | Resolved into `config.webhook_url`, consumed by `scripts/notify.py` webhook delivery (daemon-thread, 5s socket timeout, 10s hard join). |

### Multi-agent upgrade layer

| Variable | Effect |
|---|---|
| `NEXUS_MODEL_ROUTING` | `1`/`true`/`yes` wraps the primary LLM in `RoutingProvider` + `TokenBudgetMiddleware` (complexity-based routing with local fallback). |
| `NEXUS_LOCAL_BACKEND` | Local tier for the router: `ollama` (default), `lmstudio`/`openai-compatible` for an OpenAI-compatible server, or `none` to disable. |
| `NEXUS_LMSTUDIO_URL` | Base URL of the LM Studio server when `NEXUS_LOCAL_BACKEND=lmstudio` (`http://127.0.0.1:1234/v1`). |
| `NEXUS_LMSTUDIO_MODEL_HIGH` | LM Studio model for HIGH-complexity fallbacks (`qwen/qwen3.5-9b`). |
| `NEXUS_LMSTUDIO_MODEL_LOW` | LM Studio model for LOW-complexity routine tasks (`deepseek-r1-distill-qwen-7b`). |
| `NEXUS_LOCAL_TIMEOUT` | Seconds the local tier allows per completion (`120`) - local inference needs far more than a socket check. |
| `NEXUS_OLLAMA_URL` | Base URL of the local Ollama server when `NEXUS_LOCAL_BACKEND=ollama` (`http://127.0.0.1:11434`). |
| `NEXUS_LOCAL_MODEL_HIGH` | Ollama model for HIGH-complexity fallbacks (`qwen3.5:9b`). |
| `NEXUS_LOCAL_MODEL_LOW` | Ollama model for LOW-complexity routine tasks (`qwen2.5-coder:7b-instruct`). |
| `NEXUS_DAILY_TOKEN_BUDGET` | Per-agent daily token cap for the budget middleware (`500000`); over-budget traffic routes down to the local tier. |
| `NEXUS_TOKEN_BUDGET_LEDGER` | Path of the per-day token spend ledger (`token_budget_ledger.json`), kept to the last 30 days. |
| `NEXUS_BRIDGE_TOKEN` | Shared secret required before a WebSocket client may speak on the headless IDE bridge. |
| `NEXUS_BRIDGE_ALLOWLIST` | Comma-separated op allowlist for the bridge; default is `ping,open`, with `run` and `edit` added only when the env explicitly includes them. |
| `NEXUS_BRIDGE_RATE_LIMIT` | Maximum allowed bridge commands per op within the rate window (`10`). |
| `NEXUS_BRIDGE_RATE_WINDOW_SECONDS` | Sliding window in seconds for bridge rate limiting (`60`). |

### Daemon and heal loop

These are read by the ops scripts (`scripts/`), not by the `src/` modules — the
[env-var guard](../tests/eval/test_docs_env_vars.py) scans both.

| Variable | Effect |
|---|---|
| `NEXUS_DAEMON_KILL_SWITCH` | `1` stops the overnight daemon, `0` disarms the switch; unset means the marker file `.nexus_overnight_stop` governs (create it to stop between items). |
| `NEXUS_DAEMON_BLACKOUTS` | Blackout windows for the daemon, e.g. `09:00-17:00,22:00-06:00` (default empty = run anytime). Wrap-around-midnight windows supported; invalid entries are skipped, not fatal. |
| `NEXUS_HEAL_PYTEST_TIMEOUT` | Seconds the heal loop allows per pytest run (`900`). |
| `NEXUS_API_KEY` | Key for the heal loop's primary LLM (falls back to `OPENAI_API_KEY`). Not the API server's auth map — that is `NEXUS_API_KEYS`. |

## See also

- [Dual-Loop Architecture](dual-loop.md)
- [Clean Architecture & Dependency Rule](clean-architecture.md)
- [Memory System](memory.md)
- [Backup & DR](backup-dr.md)
- [Upgrade Spaces](upgrade-spaces.md)
