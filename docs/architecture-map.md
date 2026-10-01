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
| `ports/secrets.py` | `SecretStore` | `EnvSecretStore`, or `ChainedSecretStore` over `JsonFileSecretStore` when `NEXUS_SECRET_BACKEND=json:<path>` | same |
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

## Built-in tools (21)

Registered by `BuiltinToolRegistry(default_builtin_tools())`; handlers live in
`infrastructure/adapters/execution/extended_tools.py`.

`web_search`, `web_fetch`, `calculator`, `run_python`, `run_shell`, `read_file`,
`write_file`, `list_directory`, `json_query`, `json_transform`,
`current_datetime`, `diff_text`, `hash_text`, `base64_encode`, `git_info`,
`http_request`, `grep`, `system_info`, `find_databases`, `query_database`,
`process_multimodal_media`.

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

## See also

- [Dual-Loop Architecture](dual-loop.md)
- [Clean Architecture & Dependency Rule](clean-architecture.md)
- [Memory System](memory.md)
- [Backup & DR](backup-dr.md)
