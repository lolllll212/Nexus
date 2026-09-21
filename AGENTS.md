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
| Add an API endpoint | `infrastructure/api/routes/<name>.py` + register in `main.py` |
| Change LLM behavior | `application/cortex/process_message.py` (ReAct loop) + `react_prompt.py` (system prompt) |
| Add a port | `domain/ports/<name>.py` |
| Swap an adapter | `infrastructure/di/container.py` (one-line change in `_build_*` method) |
| Add training data | `application/training/seed_data.py` or `python -m nexus.training.cli` |

## Testing Pattern

Tests use `tests/fakes/container.py` — a `FakeContainer` that wires real use cases against in-memory adapters. This is how you test without Redis/Neo4j/Qdrant. The `RecordingLLM` and `ScriptedLLM` classes in test files capture LLM calls for assertions.

## CI

Three jobs on every push: `lint` (ruff + black + mypy), `test` (pytest), `architecture` (import-linter enforces domain independence).
