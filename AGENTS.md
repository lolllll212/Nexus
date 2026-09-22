# AGENTS.md — NEXUS

## Architecture

Hexagonal (ports & adapters). **Dependency rule is enforced by CI.** `nexus.domain` must never import `nexus.infrastructure`.

```
src/nexus/
  domain/          # Pure entities + ports (zero deps)
  application/     # Use cases (depends only on ports)
  infrastructure/  # Adapters, API, DI container
  training/        # Coding training CLI + store
```

The DI container (`infrastructure/di/container.py`) is the **only** place concrete adapters are chosen. Swap an adapter by editing that file.

## Commands

```bash
# Test (no infra needed — all in-memory fakes)
pytest tests/ -q                    # full suite (~170 tests)
pytest tests/unit/test_swarm.py -v  # single file
pytest tests/eval/ -v               # eval harness

# Lint / format / typecheck
ruff check src/ tests/
black --check src/ tests/           # or: black src/ tests/ to fix
mypy src/nexus/domain/ src/nexus/application/ --ignore-missing-imports

# Run server
python -m uvicorn nexus.infrastructure.api.main:app --host 127.0.0.1 --port 8000 --reload

# Import training data
python -m nexus.training.cli import-seed
```

## Key Quirks

- **`.env` is gitignored.** Copy `.env.example` → `.env`. Current config uses LM Studio on `localhost:1234` (Qwen 3.5 9B + Qwen2.5 Coder 7B + all-MiniLM-L6-v2 embeddings).
- **Auth fail-closed.** `NEXUS_API_KEYS={}` means zero keys configured — all requests get 401. Set a key in `.env` before testing endpoints.
- **pytest asyncio_mode = auto.** All async tests run without `@pytest.mark.asyncio` (it's in `pytest.ini`).
- **PowerShell, not bash.** On Windows, `curl` is an alias for `Invoke-WebRequest`. Use `Invoke-RestMethod` for API calls.
- **Qwen 3.5 is a reasoning model.** It uses `reasoning_content` for chain-of-thought. Needs `max_tokens` ≥ 200+ for answers to appear in `content`.
- **`embedding model` actual name in LM Studio:** `text-embedding-all-minlm-l6-v2-embedding` (384 dim), not `all-MiniLM-L6-v2`.
- **`testpaths = ["tests"]` and `pythonpath = ["src"]`** are set in both `pyproject.toml` and `pytest.ini`. Don't remove either.

## File Mapping

| What you're doing | Files to edit |
|---|---|
| Add a tool | `infrastructure/adapters/execution/extended_tools.py` (handlers) + `builtin_tools.py` (registry) |
| Use a discovered database autonomously | Two built-in tools: `find_databases` (scans dirs for `.sqlite/.db` + `docker-compose`/`.env` configs) and `query_database` (sqlite/postgres/mysql/redis). The ReAct prompt already instructs the agent to connect on its own — no wiring needed |
| Add an API endpoint | `infrastructure/api/routes/<name>.py` + register in `main.py` |
| Change LLM behavior | `application/cortex/process_message.py` (ReAct loop) + `react_prompt.py` (system prompt) |
| Add a port | `domain/ports/<name>.py` |
| Swap an adapter | `infrastructure/di/container.py` (one-line change in `_build_*` method) |
| Add training data | `application/training/seed_data.py` or `python -m nexus.training.cli` |
| Add security | `infrastructure/adapters/sandbox/docker_sandbox.py` + set `NEXUS_SANDBOX_BACKEND=docker` |
| Add observability | `infrastructure/adapters/observability/opentelemetry.py` + set `NEXUS_OTEL_ENABLED=true` |
| Fix memory graph | `domain/ports/memory_repository.py` (add `get_memories`) + adapter + `process_message.py:_recall()` |
| Fix swarm tools | `infrastructure/adapters/swarm/executor.py` (pass `tools` param) |

## Testing Pattern

Tests use `tests/fakes/` (package, not file) — `FakeContainer` wires real use cases against in-memory adapters. The `RecordingLLM` and `ScriptedLLM` classes in test files capture LLM calls for assertions. `FakeSandbox` executes code's `solve` function when possible.

## Critical Bugs Fixed

- **Graph memory recall** (`process_message.py:_recall()`): `get_memories()` added to `ConceptRepository` port. Previously graph traversal returned `Concept` objects but never added memories to the prompt.
- **Swarm concurrency** (`executor.py:run_agent()`): Previously mutated shared `self._tools`. Now passes `tools` parameter through `execute()`.
- **ReAct loop tool memory** (`process_message.py:_react_loop()`): The assistant's own `TOOL_CALL` is now appended to the context alongside the observation (as a `user`-role message). Previously only observations were appended, so the model never saw its action paired with its result and re-explored every turn. The loop guard now **forces** an auto-synthesized final answer when the same tool is called 3x in a row (previously it only nudged, which local models ignore).
- **Generated-tool validation** (`generate_tool.py:execute()`): Previously only checked `error is None`. Now validates actual output matches `expected_outputs`.
- **Sandbox default**: `DockerSandbox` is now the production default. Set `NEXUS_SANDBOX_BACKEND=subprocess` to fall back to subprocess.

## Ops — Tier 3 additions

- **`nexus eval`** — golden-set eval vs the live LLM. Config via `NEXUS_EVAL_BASE_URL` (fallback `NEXUS_LLM_BASE_URL`), `NEXUS_EVAL_MODEL` (`qwen2.5-coder-7b-instruct`), `NEXUS_EVAL_API_KEY` (`local-no-key`), `NEXUS_EVAL_MIN_PASS_RATE` (0.0); `python -m nexus.eval --output … --min-pass-rate …`.
- **`NEXUS_INFRA_BACKEND`** — `external` (default: Redis/Qdrant/Neo4j/OpenAI) or `memory` (fully in-process: `InMemoryEventBus`, `InMemoryEmbedder`, `InMemoryMemoryRepository`, `InMemoryConceptRepository`, `InMemoryShortTermMemory`, `InMemoryRateLimiter`).
- **`NEXUS_QUOTA_*`** — `NEXUS_QUOTA_CHAT_PER_DAY`, `NEXUS_QUOTA_TOOL_GEN_PER_DAY`, `NEXUS_QUOTA_MEMORIES_PER_DAY` (0 = unlimited, daily window via `RateLimitQuota` over `RateLimiter`); `NEXUS_GOALS_MAX_ACTIVE` (active-goal ceiling, enforced in `CreateGoalUseCase`).
- **Backups** — `nexus backup [--output-dir backups --retain 7 --tenant t1,t2]` snapshots each `nexus_memory` / `nexus_memory_{tenant}` collection (`POST /collections/{name}/snapshots`) and dumps Neo4j to `backups/neo4j-*.jsonl`; see `docs/backup-dr.md` + `src/nexus/infrastructure/backup/`.

## Known Issues

- `datetime.datetime.utcnow()` is deprecated in Python 3.13+ — replace with `datetime.now(datetime.UTC)` across the codebase.

## Dependencies & Lockfiles

- **Runtime lock**: `requirements.in` → `requirements.txt` keeps `pyproject.toml` `>=` specs in sync. **Re-lock targets Linux/Py3.11** (the Docker image) using `uv`: `uv pip compile requirements.in -o requirements.txt --python-platform linux --python-version 3.11`. Dev lock: `requirements-dev.in` → `requirements-dev.txt` (same flags). Keep both `.txt` files committed.
- Docker builds install only `requirements.txt` (runtime). CI installs the editable package with `.[dev]` from `pyproject.toml`, not the lockfiles.
- `python-dotenv`, `httpx`, `pyyaml`, etc. are pinned transitively in the lock — bump by editing `requirements.in` and re-locking, not hand-editing `.txt`.

## CI

Three jobs on every push: `lint` (ruff + black + mypy), `test` (pytest), `architecture` (import-linter enforces domain independence).
