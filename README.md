<div align="center">

# NEXUS

### A New Kind of AI Brain

**Autonomous ReAct reasoning &bull; Subconscious synthesis &bull; Dreaming &bull; Self-evolution**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://github.com/lolllll212/Nexus/actions/workflows/ci.yml/badge.svg)](https://github.com/lolllll212/Nexus/actions/workflows/ci.yml)

</div>

---

## What is NEXUS?

NEXUS is a **production-grade AI agent framework** built on strict hexagonal architecture (ports & adapters). It gives any LLM the ability to **reason, act, and learn autonomously** — not just answer questions, but explore codebases, execute code, chain tool calls, and remember everything.

### Core Capabilities

| Capability | Description |
|---|---|
| **Autonomous ReAct Loop** | Agent reasons through problems step-by-step, picks tools without human intervention, chains calls across iterations |
| **13 Built-in Tools** | `read_file`, `write_file`, `list_directory`, `grep`, `run_python`, `run_shell`, `calculator`, `diff_text`, `hash_text`, `base64_encode`, `json_query`, `json_transform`, `web_fetch`, `web_search`, `git_info`, `system_info`, `current_datetime`, `http_request` |
| **Subconscious Synthesis** | Background event bus extracts entities, builds a synaptic graph, fires realizations mid-conversation |
| **Dreaming Pipeline** | Nightly batch: compress episodic memory, prune stale data, simulate solutions, consolidate concepts |
| **Self-Evolution** | Brain generates, tests, deploys, and registers its own tools via `POST /v1/tools/generate` |
| **Multi-Agent Swarms** | Fan-out tasks to worker agents with per-agent tool allowlists and system prompts |
| **Coding Training** | RAG-powered few-shot retrieval from a versioned training corpus with quality scoring |
| **Plugin System** | Drop Python packages into `plugins/` — auto-discovered and injected into the tool registry |

---

## Architecture

Strict clean architecture. The **dependency rule** is enforced and tested.

```
┌──────────────────────────────────────────────────────────────────────┐
│  ENTRY POINTS                                                       │
│   FastAPI /v1  &bull;  Celery workers  &bull;  Celery beat (dreams)    │
├──────────────────────────────────────────────────────────────────────┤
│  APPLICATION LAYER  (use cases, no I/O)                              │
│   ProcessMessage  EntitySynthesis  DreamSession  GenerateTool        │
│   PatternDetection  SelfHeal  SubconsciousCoordinator  Swarm         │
├──────────────────────────────────────────────────────────────────────┤
│  DOMAIN PORTS  (abstractions)                                        │
│   LLMProvider  MemoryRepository  ConceptRepository  EventBus        │
│   ToolRegistry  ToolExecutor  ShortTermMemory  Sandbox               │
├──────────────────────────────────────────────────────────────────────┤
│  DOMAIN CORE  (pure Python, zero dependencies)                       │
│   Memory  Concept  SynapticConnection  Thought  Tool  Conversation  │
└──────────────────────────────────────────────────────────────────────┘

Adaptations (swappable in one file: di/container.py):
  Neo4j  &bull;  Qdrant  &bull;  Redis  &bull;  OpenAI  &bull;  SubprocessSandbox
```

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- **LM Studio** running on `localhost:1234` (or any OpenAI-compatible endpoint)
- Optional: Redis, Neo4j, Qdrant for full persistence

### 1. Install

```bash
cd NEXUS
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac
pip install -e .[dev]
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` — minimal config for local LM Studio:

```env
NEXUS_LLM_BASE_URL=http://localhost:1234/v1
NEXUS_LLM_MODEL=qwen/qwen3.5-9b
NEXUS_LLM_MAX_TOKENS=35000
OPENAI_API_KEY=local-no-key

NEXUS_BACKGROUND_LLM_BASE_URL=http://localhost:1234/v1
NEXUS_BACKGROUND_LLM_MODEL=qwen2.5-coder-7b-instruct

NEXUS_EMBEDDING_BASE_URL=http://localhost:1234/v1
NEXUS_EMBEDDING_MODEL=all-MiniLM-L6-v2
NEXUS_EMBEDDING_DIMENSION=384
```

### 3. Run

```bash
# Start LM Studio (load Qwen 3.5 9B + embedding model)

# Start NEXUS
python -m uvicorn nexus.infrastructure.api.main:app --host 127.0.0.1 --port 8000 --reload
```

### 4. Talk to It

```bash
# OpenAI-compatible endpoint
curl http://localhost:8000/v1/chat/completions -H "Authorization: Bearer your-api-key" -H "Content-Type: application/json" -d '{"model": "qwen-3.5", "messages": [{"role": "user", "content": "List all Python files in C:\\path\\to\\project and tell me what each one does"}]}'

# Native endpoint
curl -X POST http://localhost:8000/v1/chat -H "Authorization: Bearer your-api-key" -H "Content-Type: application/json" -d '{"message": "Analyze the architecture of the codebase at C:\\path\\to\\project"}'
```

The agent will **autonomously**:
1. Call `list_directory` to explore the structure
2. Call `grep` to find patterns across files
3. Call `read_file` to get specific code
4. Chain tool calls across multiple iterations
5. Output `FINAL ANSWER:` when it has enough information

---

## API Reference

### Chat

| Endpoint | Method | Description |
|---|---|---|
| `/v1/chat` | POST | Native chat with metadata (thoughts, tools used, memories) |
| `/v1/chat/completions` | POST | OpenAI-compatible chat completions |
| `/v1/coding` | POST | RAG-powered coding mode with few-shot retrieval |

**Request body (`/v1/chat`):**
```json
{
  "message": "Analyze the codebase at C:\\project",
  "session_id": "optional-session-id",
  "image_urls": ["optional image urls"]
}
```

**Response:**
```json
{
  "response": "FINAL ANSWER: The codebase has 12 Python files...",
  "session_id": "abc123",
  "thoughts": [...],
  "tools_used": ["list_directory", "grep", "read_file"],
  "memories_recalled": 3
}
```

### Memory

| Endpoint | Method | Description |
|---|---|---|
| `/v1/memory/search` | GET | Vector search across long-term memory |
| `/v1/memory/concepts` | GET | Browse the synaptic concept graph |

### Tools

| Endpoint | Method | Description |
|---|---|---|
| `/v1/tools` | GET | List registered tools |
| `/v1/tools/generate` | POST | Self-evolution: generate a new tool from a problem description |

### Training (Coding)

| Endpoint | Method | Description |
|---|---|---|
| `/v1/coding` | POST | RAG-powered coding chat |
| `/v1/coding/stats` | GET | Training data statistics |
| `/v1/coding/examples` | GET/POST | Browse and add training examples |
| `/v1/coding/examples/{id}` | GET/PUT/DELETE | CRUD on individual examples |
| `/v1/coding/quality/top` | GET | Top-rated training examples |
| `/v1/coding/quality/low` | GET | Low success-rate examples (review candidates) |
| `/v1/coding/learn` | POST | Auto-learn from a coding session |
| `/v1/coding/import/git` | POST | Import training examples from a git repo |

### Multi-Agent Swarms

| Endpoint | Method | Description |
|---|---|---|
| `/v1/agents` | GET/POST | Register and list AI agents |
| `/v1/swarms` | GET/POST | Create and list swarms |
| `/v1/swarms/{id}/run` | POST | Execute a swarm on a task |

### System

| Endpoint | Method | Description |
|---|---|---|
| `/v1/system/dream` | POST | Manually trigger a dream cycle |
| `/v1/health` | GET | Health check |

---

## Built-in Tools

All tools are autonomous — the agent picks them based on the task, you never call them manually.

| Tool | Description |
|---|---|
| `read_file` | Read file contents from disk |
| `write_file` | Write/create files |
| `list_directory` | List directory entries with sizes |
| `grep` | Regex search across files |
| `run_python` | Execute Python code in a sandbox |
| `run_shell` | Execute shell commands |
| `calculator` | Evaluate math expressions safely |
| `diff_text` | Unified diff between two strings |
| `hash_text` | SHA-256 hash of text |
| `base64_encode` | Base64 encode text |
| `json_query` | Navigate JSON structures |
| `json_transform` | Evaluate expressions on JSON data |
| `git_info` | Repository branch, status, last commit |
| `current_datetime` | UTC timestamp and formatted datetime |
| `system_info` | OS, Python version, CPU count |
| `web_fetch` | Fetch URL content |
| `web_search` | DuckDuckGo search |
| `http_request` | Generic HTTP requests |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `NEXUS_LLM_BASE_URL` | `http://localhost:1234/v1` | LLM endpoint |
| `NEXUS_LLM_MODEL` | `gpt-4o` | Model name |
| `NEXUS_LLM_MAX_TOKENS` | `8192` | Max tokens per response |
| `NEXUS_BACKGROUND_LLM_*` | — | Separate LLM for background loops |
| `NEXUS_EMBEDDING_*` | — | Embedding provider config |
| `NEXUS_PLUGINS_DIR` | `plugins` | Plugin directory |
| `REDIS_HOST` | `localhost` | Redis host |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j bolt URI |
| `QDRANT_HOST` | `localhost` | Qdrant host |
| `NEXUS_API_KEYS` | `{}` | API keys (JSON) |
| `NEXUS_AUTONOMY_HOURLY_BUDGET` | `0` | Max autonomous steps/hour (0=unlimited) |
| `NEXUS_SWARM_MAX_WORKERS` | `5` | Max swarm workers |

### Hybrid LLM Split

Run a fast model for chat and a cheap local model for background work:

```env
# Interactive (chat, tool use, swarms)
NEXUS_LLM_BASE_URL=https://api.groq.com/openai/v1
NEXUS_LLM_MODEL=llama-3.3-70b-versatile

# Background (dreaming, synthesis, autonomy)
NEXUS_BACKGROUND_LLM_BASE_URL=http://localhost:11434/v1
NEXUS_BACKGROUND_LLM_MODEL=llama3:8b
```

---

## Project Structure

```
NEXUS/
├── src/nexus/
│   ├── domain/                         # Pure core — zero dependencies
│   │   ├── entities/                   #   Memory, Concept, Tool, Conversation, Thought
│   │   ├── value_objects/              #   EmotionalState, SynapseConfig, JSONSchema
│   │   ├── ports/                      #   Interfaces (LLMProvider, EventBus, etc.)
│   │   └── exceptions/
│   ├── application/                    # Use cases — orchestration, no I/O
│   │   ├── cortex/                     #   ProcessMessage (ReAct loop), SessionManager
│   │   ├── subcortex/                  #   EntitySynthesis, PatternDetection
│   │   │   └── dreaming/              #   Compress, Prune, Simulate, Consolidate
│   │   ├── tools/                      #   GenerateTool, SelfHeal
│   │   ├── swarm/                      #   SwarmCoordinatorUseCase
│   │   └── training/                   #   CodingStore, AutoLearner, GitIngester
│   └── infrastructure/                 # Concrete adapters — swappable
│       ├── adapters/
│       │   ├── persistence/            #   Neo4j, Qdrant, Redis
│       │   ├── llm/                    #   OpenAI provider
│       │   ├── execution/              #   Tool executor + 18 built-in tools
│       │   ├── plugins/                #   Plugin loader (auto-discovers plugins/)
│       │   └── swarm/                  #   SwarmAgentExecutor
│       ├── api/                        #   FastAPI routes
│       ├── di/                         #   Container — the composition root
│       └── workers/                    #   Celery background tasks
├── plugins/                            # Drop-in tool extensions
├── data/                               # Training data, code examples
├── tests/                              # Unit tests + architecture guards (zero infra required)
├── .env.example                        # Full config template
└── pyproject.toml                      # Dependencies, tool config
```

---

## Plugins

Drop a Python package into `plugins/` and it's auto-discovered:

```
plugins/
└── my_custom_tools/
    └── __init__.py
```

**`__init__.py` must expose:**
- `TOOL_DEFS` — list of tool definition dicts
- `TOOL_HANDLERS` — dict mapping tool_id to async handler

```python
TOOL_DEFS = [
    {
        "id": "my_tool",
        "name": "my_tool",
        "description": "Does something useful",
        "input": {"param": {"type": "string"}},
        "output": {"type": "string"},
    }
]

TOOL_HANDLERS = {
    "my_tool": lambda params: {"result": f"Handled {params['param']}"}
}
```

---

## Testing

```bash
# Run the full test suite (no infrastructure needed)
pytest

# Run with coverage
pytest --cov=nexus --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_process_message.py -v
```

Tests use in-memory fakes for all adapters — no Redis, Neo4j, or Qdrant required.

---

## Docker

```bash
# Full stack (Redis + Neo4j + Qdrant + NEXUS)
docker compose up -d

# Or just infrastructure
docker compose up -d redis neo4j qdrant
```

---

## License

MIT
