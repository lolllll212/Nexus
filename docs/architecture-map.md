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

## Value objects (15 modules)

`domain/value_objects/` — immutable, compared by value.

| Module | Types |
|---|---|
| `ai_feedback.py` | `AIFeedback`, `FeedbackCategory`, `summarize_feedback` |
| `ai_guardrails.py` | `GuardrailPolicy`, `GuardrailDecision`, `GuardrailFinding`, `GuardrailAction`, `combine_guardrail_decisions` |
| `clock.py` | `utc_now()` (the only sanctioned clock — avoids the `utcnow()` deprecation) |
| `context_pack.py` | `ContextCandidate`, `ContextItem`, `ContextPack`, `build_context_pack`, `estimate_tokens` |
| `emotion.py` | `EmotionalState` |
| `execution_quality.py` | `ExecutionProfile`, `ResponseQualityReport`, `build_execution_profile`, `build_execution_contract`, `assess_response_quality`, adaptive effort/evidence policy and bounded repair prompts |
| `hex_fourier.py` | `HexCoord`-space `AxisSpectrum`, `HexSpectrum` |
| `hex_grid.py` | `HexCoord`, `HexGrid` |
| `hex_index.py` | `HexIndex` |
| `identity.py` | `Identity`, `Role` |
| `schema.py` | `JSONSchema` |
| `solution_brief.py` | `SolutionBrief`, `RepositoryRequest`, `DeterministicToolCall`, multi-workstream request execution briefs and practical fallback rendering |
| `synapse.py` | `SynapseConfig`, `ConnectionType` |
| `upgrade_spaces.py` | `UpgradeSpace`, `upgrade_spaces_catalog` |
| `valence.py` | `ValenceTag` |

## Modern AI platform layer

The cortex wraps each run in four provider-independent platform features.
`GuardrailPolicy` evaluates input before sanitized text reaches session state,
subconscious dispatch, recall, prompts, tools, or episodic memory; evaluates
displayed reasoning, tool observations, rendered memories, and the final
answer on the way out; and returns safe allow/redact/flag/block metadata
without matched sensitive values. Blocked secret-exfiltration and tool-bypass
inputs never reach dispatch, recall, an LLM, a tool, or episodic encoding.

`build_context_pack` fuses up to 16 semantic and 8 graph candidates with
weighted reciprocal-rank fusion (`semantic=1.0`, `graph=0.85`, RRF `k=60`),
merges repeated IDs/normalized text, applies MMR diversity (`lambda=0.72`),
and renders at most 8 cited items inside a 1,200-token evidence budget.
`MessageResult` and the chat API expose the run `response_id`, combined
guardrail metadata, and each selected item's citation/source/rank/score/token
provenance.

The Elite Execution Engine keeps policy in
`domain/value_objects/execution_quality.py`: `build_execution_profile`
resolves Auto/Fast/Balanced/Deep/Max into sampling, token, repair, quality,
and evidence requirements, and `build_execution_contract` renders a compact
workstream/evidence contract from the solution brief. The cortex applies that
profile to its provider calls, canonicalizes provider-native tool calls into
the existing approval/audit path with textual ReAct fallback, assesses the
candidate final answer with `assess_response_quality`, and performs only the
profile/deployment-capped number of private repairs. `MessageResult` returns
API-safe `execution` and `quality` metadata, and metrics record reports,
scores, issues, and repairs by tenant/effort/status. The 25-case golden eval
set grades effective effort and minimum verified quality for its
`execution_quality` cases.

Response feedback is a deliberately thin persistence concern rather than a new
domain port in this slice: the DI container binds the `ai_feedback` routes to
`infrastructure/adapters/persistence/ai_feedback_store.py`
(`AIFeedbackStore`), an atomic JSON/in-memory store scoped by verified tenant
and user. It updates an existing vote for the same response, scrubs comments
through the output guardrail, and computes personal/admin-tenant quality
summaries from `domain/value_objects/ai_feedback.py`. See
[Modern AI Platform](ai-platform.md) for the API and operator contract.

## Built-in tools (48)

Registered by `BuiltinToolRegistry(default_builtin_tools())`; handlers live in
`infrastructure/adapters/execution/extended_tools.py`.

`web_search`, `web_fetch`, `calculator`, `run_python`, `run_shell`, `read_file`,
`write_file`, `list_directory`, `edit_file`, `delete_file`, `create_directory`,
`create_repository`, `project_scan`, `find_files`, `directory_tree`,
`read_files`, `file_outline`, `find_symbol`, `code_diagnostics`, `git_diff`,
`project_checks`, `secret_scan`, `release_readiness`, `changelog_draft`,
`write_files`, `batch_edit_files`, `move_path`, `copy_path`,
`delete_directory`, `json_query`, `json_transform`,
`current_datetime`, `diff_text`, `hash_text`, `base64_encode`, `git_info`,
`http_request`, `grep`, `system_info`, `find_databases`, `query_database`,
`process_multimodal_media`, `pytest_runner`, `csv_query`, `memory_graph_query`,
`code_search_semantic`, `dependency_audit`, `regex_extract`.

The coding power tools are designed for existing projects larger than a
single file. `project_scan` maps languages, manifests, frameworks,
entrypoints, tests, and Git state in one pruned traversal. `find_files`,
`directory_tree`, `read_files`, `file_outline`, and `find_symbol` provide
fast project navigation with less context waste than repeated one-file reads.
`code_diagnostics`, `git_diff`, and `project_checks` find syntax problems,
show actual changes, and run bounded Python/npm/Git verification.
`write_files` and `batch_edit_files` prevalidate coordinated changes and
stage writes with rollback, while `move_path`, `copy_path`, and
`delete_directory` solve file/folder reorganization problems under the same
workspace confinement and approval rules as the one-file mutation tools.
`secret_scan` reports likely committed credentials with redacted previews,
`release_readiness` combines scan/diagnostics/secrets/dependencies/Git and
optional checks into a ship/no-ship gate, and `changelog_draft` turns real
Git history into categorized release notes while listing uncommitted files
separately.

Two of these support authorized project/database exploration:
`find_databases` scans a tree for `.sqlite`/`.db` files and
`docker-compose`/`.env` connection config; `query_database` speaks
sqlite/postgres/mysql/redis. The ReAct prompt treats database access as
read-only by default, forbids printing `.env` secrets or guessing external
targets, and requires an explicit instruction for mutations.

`create_repository` is the approval-gated local project builder. It writes a
runnable template, starter tests, README, license, and optional CI under a
confined workspace folder; initializes Git when requested; refuses unknown
non-empty targets unless overwrite is explicit; and returns the actual files,
Git status, and next commands. It can configure an existing GitHub remote but
never creates or pushes a remote repository by itself.

## API route modules (22)

`infrastructure/api/routes/`: `chat`, `memory`, `tools`, `coding`, `goals`,
`swarm`, `graph`, `system`, `telemetry`, `research`, `analyze`, `workflows`,
`mcp`, `multimodal`, `audio`, `nim`, `integrations`, `coding_assistant`,
`workspace`, `history`, `models`, `ai_feedback`.

### Chat history and model changer

The `history` routes expose owner-scoped conversation sessions under
`/api/history/sessions` for the web chat's history window. The DI container
binds them to the concrete persistence adapter
`infrastructure/adapters/persistence/chat_history_store.py` (`ChatHistoryStore`),
an atomic JSON-file store (tmp file + `os.replace`) with an in-memory mode for
tests and ephemeral deploys. It is deliberately not a domain port: chat
transcripts are a UI concern, kept separate from semantic/graph memory.

The `models` route (`GET /api/models`) is the model picker's catalog and also
publishes top-level `execution` discovery metadata (supported/default effort,
adaptive-routing availability, quality gate, native tool calling, and repair
cap). A chat request may carry `model: "auto"` or any NVIDIA NIM model id from
the catalog. An explicit NIM selection always wins; in Auto on a NIM-backed
cortex, the execution profile chooses fast, balanced, flagship/deep, or vision
catalog entries. Either way, the selected NIM model runs on a fresh
per-request `NvidiaNimProvider` passed through
`ProcessMessageUseCase.execute(llm=..., effort=...)`, so the shared container
provider is never mutated. The request's `effort` is validated against
Auto/Fast/Balanced/Deep/Max and falls back to `NEXUS_AI_DEFAULT_EFFORT` when
Auto is left to the operator default. Claude-style capability flags on the
same request (`extended_thinking`, `deep_research`, `artifacts`) become prompt
instructions plus a sanitized `thinking` trace in the response/SSE frames.
There is no Anthropic integration — "Claude-style" describes the UX, not a
provider.

### AI capabilities, feedback, and quality

The `ai_feedback` route exposes `GET /api/ai/capabilities`—including
`features.execution_quality` checks/settings and quality metric names—
owner-scoped `POST`/`GET /api/ai/feedback`, the caller's
`GET /api/ai/feedback/summary`, and admin-only aggregate `GET /api/ai/quality`.
`POST /v1/chat` returns `response_id`, `guardrail`, `context_sources`,
`execution`, and `quality`; the SSE endpoint includes resolved effort in its
start frame, may emit `quality_repair` while a draft is being improved, places
the response ID in its `answer` frame, and emits all settled metadata in a
`metadata` frame before `done`.

The main React app also has a full-screen hybrid chat workspace: Claude-like
warmth and composer ergonomics, Gemini-like gradient/sparkle suggestion cards,
and ChatGPT-like top model selection/message actions, over a reduced-motion
aware Nexus aurora/constellation background. Its searchable light model
changer is used in the header, composer, and Customize view; Projects includes
a direct Repository Builder form. The agent path is the same ReAct loop, which
injects every registered tool into the model context. The tools route
additionally exposes schemas/categories
on `GET /v1/tools`, tenant approval state on `GET /v1/tools/approvals`,
admin grants on `POST /v1/tools/approvals/grant`, and admin-only direct
execution on `POST /v1/tools/execute` for the workspace's Tools/Code panel.
Direct execution still passes through registry schema validation, sandboxing,
workspace path confinement, the sensitive-file denylist, and approval gates
for shell and mutating file tools.

Before the ReAct prompt, the cortex inserts a deterministic real-world
request-execution brief from `domain/value_objects/solution_brief.py`. The
brief keeps a dominant intent for compatibility but also preserves every
workstream in a compound Claude-style ask (for example research → inspect →
fix → test → summarize). It extracts explicit budget/deadline/location,
audience, technology, format, quantity, and must/avoid constraints from the
latest message plus recent human turns; identifies deliverables and referenced
paths; classifies the operation as answer-only, read-only, external research,
workspace mutation, or mixed; and emits ordered execution phases plus
acceptance criteria. Its readiness gate distinguishes ready work,
proceed-with-assumptions, proceed-with-caution, confirmation-required,
safety-first, and clarify-first requests. The ReAct prompt mirrors this with
an understand → inspect/gather evidence → act → verify → deliver contract.
The NVIDIA NIM simulation uses the same pure module for a structured
practical fallback and, inside ReAct, can emit a real `create_repository`
call plus narrow deterministic read-only calls (`calculator`,
`list_directory`, `read_file`, `grep`, `git_info`, `pytest_runner`,
`current_datetime`, `system_info`, and `hash_text`), summarizing only the
returned observation. The golden eval set includes a `real_life` category for
compound inspection, current research, data analysis, constrained planning,
and safe clarification before a destructive action.

## Website surfaces

Nexus has three website families that deliberately share contracts instead of
copying state:

- The main React app in `web/` hosts the hybrid chat, workspace cockpit,
  searchable Upgrade Spaces panel, tool approvals/results, voice controls, and
  the swarm dashboard. The swarm view connects to the same-origin `/bridge`
  WebSocket proxy, authenticates with a first message rather than a URL token,
  and labels data live only after a bridge snapshot or delta arrives.
- The buildless workspace in `frontend/workspace.html` is served by the sibling
  `backend/` app. Its `/api/workspace/spaces` endpoint imports the same
  `domain/value_objects/upgrade_spaces.py` catalog as the core API, with
  server-side search and priority filtering.
- The buildless Brain Chat and galaxy pages use `frontend/shared/voice.js` as
  the single Indian-English (`en-IN`) voice source. Their chat docks support
  browser-side cancellation, IME-safe Enter, session drafts, smart scrolling,
  and escaped/text-node rendering for model and graph output.
- The core API's static dashboard renders tools, dreams, swarm runs, graph
  labels, and Upgrade Spaces without interpolating API strings into HTML; its
  API key is kept only in session storage.

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
| `infrastructure/api/` | `main`, `dependencies`, `routes/` (22), `schemas` |
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
| `NEXUS_HISTORY_PATH` | JSON file for the chat history window's server-side conversation sessions (`data/chat_history.json`). Empty or `memory` keeps history process-local and ephemeral. The file is gitignored — it contains transcripts. |
| `NEXUS_AI_GUARDRAILS_ENABLED` | Enables the deterministic input/output guardrail (`true` by default; `false`, `0`, `no`, or `off` disables it for controlled debugging only). |
| `NEXUS_AI_GUARDRAIL_REDACT_PII` | Enables email/phone/SSN/payment-card redaction in the guardrail (`true` by default; `false`, `0`, `no`, or `off` disables only that category). |
| `NEXUS_AI_FEEDBACK_PATH` | Atomic JSON file for tenant/user-scoped response feedback (`data/ai_feedback.json`). Empty, `memory`, `:memory:`, or `none` keeps feedback process-local. Treat the file as user data. |
| `NEXUS_AI_QUALITY_GATE_ENABLED` | Enables deterministic final-answer assessment and bounded repair (`true` by default; `false`, `0`, `no`, or `off` disables it). |
| `NEXUS_AI_NATIVE_TOOL_CALLING_ENABLED` | Enables provider-native tool calls (`true` by default); textual ReAct remains the per-request fallback. |
| `NEXUS_AI_QUALITY_MAX_REPAIRS` | Deployment-wide quality-repair ceiling (`3`, clamped to 0–5), further capped by the effective effort profile. |
| `NEXUS_AI_DEFAULT_EFFORT` | Operator chat effort default (`auto`), normalized to Auto/Fast/Balanced/Deep/Max for requests that do not select a non-Auto effort. |

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
- [Modern AI Platform](ai-platform.md)
- [Backup & DR](backup-dr.md)
- [Upgrade Spaces](upgrade-spaces.md)
