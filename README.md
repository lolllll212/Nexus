<div align="center">

# NEXUS &bull; AI WORKSHOP OS

### Autonomous Cognitive Architecture &bull; Second Brain OS &bull; Claude Coding Studio

**Deep ReAct Reasoning &bull; NVIDIA NIM Acceleration &bull; Recursive Self-Evolution &bull; Subconscious Dreaming**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![React 19](https://img.shields.io/badge/react-19.3-61dafb.svg)](https://react.dev/)
[![Tailwind CSS v4](https://img.shields.io/badge/tailwindcss-v4.0-38bdf8.svg)](https://tailwindcss.com/)
[![NVIDIA NIM](https://img.shields.io/badge/NVIDIA-NIM%20Ready-76b900.svg)](https://developer.nvidia.com/nim)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests Passing](https://img.shields.io/badge/tests-244%20passed-brightgreen)](#testing)

</div>

---

## Overview

**NEXUS** is an enterprise-grade autonomous AI cognitive operating system built on strict hexagonal architecture (ports & adapters). It merges high-velocity interactive reasoning (**The Cortex**) with continuous background memory consolidation and synthesis (**The Subcortex**).

The system features four dedicated spatial operating modes and interconnected frontend experiences:
1. **LIVING KNOWLEDGE GRAPH (Tactical OS)**: A full-screen graphite/near-black operating canvas featuring a real-time D3 force-directed knowledge graph, 18 node categories, 5 major enterprise clusters, 3D isometric perspective projection, animated edge data streams, holographic tooltips, and an 11-action tactical context menu.
2. **AUTONOMOUS DEEP RESEARCH MODE**: Multi-hop recursive research engine with directed claim trees, competing hypothesis branches, automated citation corroboration, and one-click graph ingestion.
3. **AUTONOMOUS WORKFLOW CANVAS**: Visual DAG step orchestrator with live status telemetry, execution logs, agent handoffs, and instant knowledge conversion.
4. **HEXAGONAL ARCHITECTURE VIEWER**: Interactive diagram of Ports & Adapters, showing strict domain isolation, adapter latencies, and communication protocols.
5. **AUTONOMOUS AGENT ORCHESTRATION LAYER**: Live telemetry HUD for 10 autonomous enterprise agents (Researcher, Coder, Planner, Browser, Vision, Data Analyst, Writer, Executor, Memory, Fact Checker) with status, tasks, models, tools, latencies, tokens, and animated inter-agent message bus.
6. **EXTERNAL INTEGRATION UNIVERSE**: Dedicated interface for 16 enterprise integrations (GitHub, Google Drive, Google Calendar, Slack, Discord, Notion, Jira, Linear, Gmail, Postgres, REST APIs, Webhooks, Ollama, OpenAI, Anthropic, Groq).
7. **NEXUS Coding & Research Studio**: A dedicated Claude-style coding environment featuring chain-of-thought `<thinking>` accordions, real-time tool execution cards, an isolated Python execution sandbox, interactive split-view artifacts, and GitHub/web research integration.

---

## System Architecture

NEXUS enforces clean hexagonal separation where core domain entities are isolated from concrete infrastructure drivers:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  INTERFACES & FRONTENDS                                                          │
│   J.A.R.V.I.S. Holographic Second Brain (React + D3)                             │
│   Claude-Style Coding & Artifacts Studio (React + Tailwind)                      │
│   REST API (/api/*, /v1/*)  &bull;  SSE Token Streaming  &bull;  WebSockets      │
├──────────────────────────────────────────────────────────────────────────────────┤
│  THE CORTEX (Conscious Loop)                                                     │
│   ProcessMessageUseCase  &bull;  ReAct Multi-Step Tool Chaining                  │
│   NVIDIA NIM Provider (Llama 3.3 70B &bull; Nemotron 70B &bull; Llama 3.1 8B)   │
│   20+ Built-In & Self-Generated Tools  &bull;  Subprocess / Docker Sandbox       │
├──────────────────────────────────────────────────────────────────────────────────┤
│  THE SUBCORTEX (Subconscious Loop & Self-Evolution)                              │
│   EntitySynthesis  &bull;  PatternDetection  &bull;  DreamSession (Nightly Cron) │
│   GenerateToolUseCase  &bull;  SelfHealUseCase  &bull;  SwarmCoordinator         │
│   Autonomous Deep Web Researcher &bull; Recursive Self-Evolution Engine          │
├──────────────────────────────────────────────────────────────────────────────────┤
│  PERSISTENCE & EVENT BUS ADAPTERS                                                │
│   Redis 7 (Event Streams, Quotas, Limits)  &bull;  Neo4j 5 (Synaptic Graph)      │
│   Qdrant (Quantized Vector Memory)         &bull;  Prometheus Observability      │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Capabilities

### 1. Dedicated Claude-Style Coding & Research Studio
* **Chain-of-Thought `<thinking>`**: Collapsible reasoning view detailing problem formulation, edge-case analysis, and tool planning before generating code.
* **Real-Time Tool Calling Cards**: Visual telemetry for `run_python`, `web_search`, `read_file`, and `git_info` invocations.
* **Claude Artifacts Split-View**:
  * **Code View**: Syntax-highlighted code editor with line counts and copy actions.
  * **Live Sandbox Output**: Direct execution in the Python sandbox with stdout, stderr, and timing metrics.
  * **HTML / Component Preview**: Sandboxed iframe for live web artifacts.
  * **Research Reports**: Synthesized intelligence dossiers with citations.
* **Prompt Templates**: Quick starters for LRU Cache, Asyncio Debugging, HNSW Vector Benchmarks, and GitHub PR generation.

### 2. Autonomous Deep Research with Recursive Self-Evolution
* **Multi-Site Web Crawler**: Crawls DuckDuckGo and verified technical documentation with automated boilerplate removal.
* **Recursive Self-Evolution ("How Can I Upgrade Myself?")**:
  * Reflects upon research findings to discover architectural gaps in its own codebase.
  * Formulates capability boosts and writes executable Python code for a synthesized tool.
  * One-click **Apply Self-Upgrade**: Compiles the tool into the active runtime `ToolRegistry`, binds an execution handler, and creates a dynamic node in the Second Brain knowledge graph.

### 3. Production Hardening & Observability
* **SSRF Guard (`ssrf.py`)**: Intercepts all outgoing crawler and HTTP requests, blocking loopback (`127.0.0.1`), cloud metadata (`169.254.169.254`), and private RFC 1918 subnets.
* **Prometheus Metrics (`/metrics`)**: Standard text exposition format reporting uptime, active tools, NIM status, graph entities, and request counts.
* **Live WebSocket Telemetry (`/ws/telemetry`)**: 2-second push stream delivering system pulses to connected HUDs.
* **Probes & Tracing**: Liveness (`/healthz`) and readiness (`/readyz`) supporting both `GET` and `HEAD` requests, with `X-Request-ID` correlation and `X-Response-Time-Ms` timing headers.

### 4. Four Main Spatial Operating Modes
* **Mode 1: Living Knowledge Graph (`GRAPH`)**:
  * Real-time Canvas & D3 force-directed knowledge graph with 18 node categories and 5 major enterprise clusters (Deep Research Lab, Claude Coding Studio, Cognitive Memory, Autonomous Workflows, Integration Universe).
  * **Tactical Controls**: `FIT`, `FOCUS`, `RESET`, `ZOOM (+/-)`, `LAYOUT (Force, Ring, Cluster, Radial)`, `TRACE`, `EXPAND`, `2D/3D`.
  * **3D Isometric View**: Perspective projection with elevation pillars, z-depth based on node importance, ground shadows, and perspective grid.
  * **Intelligent Right-Click Context Menu**:
    * `RESEARCH`: Deep Research Node
    * `TRACE CONNECTIONS`: High-intensity synaptic pulse tracing
    * `OPEN SOURCE`: View source document and citations
    * `ADD TO WORKFLOW`: Append to autonomous execution canvas
    * `CREATE TASK`: Decompose into actionable planner task
    * `ASK NEXUS`: Natural language query via Command Center
    * `SUMMARIZE`: Instant executive synthesis dossier
    * `MEMORIZE`: Subcortex Qdrant vector checkpointing
    * `EXECUTE`: Dispatch directly to Claude Coding Studio
    * `PIN / UNPIN`: Lock or release physics simulation coordinate
    * `FILTER`: Filter graph viewport by node category
  * **Compact Holographic Tooltip**: HUD-styled metadata card with category, confidence %, importance score, hub, source, and synapse counts.
* **Mode 2: Deep Research Mode (`RESEARCH`)**:
  * Visual multi-stage research pipeline: Query Formulation &rarr; Broad Crawl &rarr; Citation Graph &rarr; Contradiction Detection &rarr; Synthesis.
  * Competing hypothesis tree with empirical claim verification badges and real-time operational trace.
  * Direct "Inject Into Graph" artifact publisher.
* **Mode 3: Autonomous Workflow Canvas (`WORKFLOW`)**:
  * Step-by-step DAG pipeline execution view with real-time logs, duration metrics, agent assignments, and tool telemetry.
  * Interactive step inspection and dynamic "Export to Knowledge Universe" action.
* **Mode 4: Hexagonal Ports & Adapters Architecture (`ARCHITECTURE`)**:
  * Interactive architectural diagram showing Core Domain Entities isolated from Primary Adapters (REST, SSE, WebSockets, CLI) and Secondary Adapters (NVIDIA NIM, OpenAI, Anthropic, Qdrant, Neo4j, Redis, Sandboxes).
  * Live adapter ping latency, protocol inspection, and fault isolation telemetry.

### 5. Autonomous Agent Orchestration Layer (10 Enterprise Agents)
A multi-agent swarm architecture coordinating specialized autonomous agents over a shared message bus:
1. **Researcher Agent**: Multi-hop arXiv preprint crawling and paper extraction.
2. **Coder Agent**: Sandbox code generation, AST validation, and test repair.
3. **Planner Agent**: Hierarchical task decomposition and DAG dependency scheduling.
4. **Browser Agent**: Headless web crawling, DOM extraction, and SSRF security guard.
5. **Vision Agent**: MediaPipe gesture tracking, camera HUD reticles, and diagram parsing.
6. **Data Analyst Agent**: Fourier spatial grid analysis, vector clustering, and stats profiling.
7. **Writer Agent**: Executive synthesis dossiers, citation formatting, and LaTeX exports.
8. **Executor Agent**: Isolated Docker/cgroup sandbox container process execution.
9. **Memory Agent**: Subcortex Fourier grid indexing and Qdrant vector consolidation.
10. **Fact Checker Agent**: Cross-source empirical validation and contradiction scoring.

### 6. External Integration Universe (16 Enterprise Integrations)
A complete unified integration cockpit connecting NEXUS to the modern enterprise ecosystem:
* **Code & CI/CD**: GitHub Enterprise (repos, PRs, issues, webhooks)
* **Storage & Cloud**: Google Drive (docs, PDFs, spreadsheets)
* **Productivity & Issues**: Google Calendar, Notion, Jira, Linear
* **Communication**: Slack Enterprise, Discord Bot & Voice, Gmail Workspace
* **Databases & APIs**: PostgreSQL + pgvector, REST API Engine, HMAC Webhooks
* **Foundation LLMs**: Ollama (Air-gapped local execution), OpenAI API, Anthropic Claude (Extended Thinking), Groq (480+ t/s LPU), NVIDIA NIM (Llama 3.3 70B & Nemotron)

### 7. Real-Time Cortex vs. Subcortex Information Flow Ticker
A cybernetic telemetry ticker monitoring conscious ReAct thoughts alongside unconscious background operations:
* **`[CORTEX]` ReAct Engine & Thalamus Router**: Active reasoning steps, multi-modal perception routing, and tool execution.
* **`[SUBCORTEX]` Basal Ganglia & Amygdala**: Habit policy enforcement, emotional valence scoring, and safety validation.
* **`[SUBCORTEX]` Dreaming & Fourier Grid Cells**: Nightly memory consolidation, stale synapse pruning, and 6-fold spatial lattice routing.

---

## Registered Tool Matrix (20 Built-In Tools)

| Tool ID | Category | Description |
|---|---|---|
| `run_python` | Execution | Runs Python code inside the isolated sandbox |
| `run_shell` | Execution | Runs shell commands with output and exit code capture |
| `read_file` | Workspace | Reads file content with path normalization |
| `write_file` | Workspace | Creates or overwrites files with directory creation |
| `list_directory` | Workspace | Lists directory contents with sizes and file types |
| `grep` | Workspace | Regex search across codebase files |
| `diff_text` | Coding | Computes unified diffs between two code buffers |
| `web_search` | Research | DuckDuckGo search with SSRF validation |
| `web_fetch` | Research | Fetches and cleans webpage HTML content |
| `git_info` | Git | Extracts branch name, commit hash, and dirty status |
| `calculator` | Utility | Safe AST-based mathematical expression evaluator |
| `hash_text` | Utility | Cryptographic hashing (SHA-256, MD5, SHA-1) |
| `base64_encode` | Utility | Base64 string encoding |
| `json_query` | Utility | Extracts values from nested JSON structures |
| `json_transform` | Utility | Safe evaluation of Python expressions over JSON data |
| `current_datetime` | Utility | Returns UTC ISO timestamps and unix epoch |
| `system_info` | System | Reports CPU, memory, OS platform, and Python version |
| `http_request` | Network | Outgoing HTTP requests protected by SSRF guard |
| `find_databases` | Database | Scans workspace for SQLite and database files |
| `query_database` | Database | Executes read-only SQL queries against SQLite databases |

---

## Cortex vs. Subcortex: Cost & Resource Profiling

NEXUS divides cognitive workload between two distinct engines:

| Engine | Component | Model Tier | Trigger | Cost Profile |
|---|---|---|---|---|
| **The Cortex** | Conscious ReAct Loop | Flagship (Llama 3.3 70B, GPT-4o) | User prompts, API requests | **Highest per-minute cost during active sessions** |
| **The Subcortex** | Entity Synthesis & Dreaming | Compact/Local (Llama 3.1 8B, Qwen 2.5) | Redis events, Celery Beat cron | **Highest background cumulative cost if unthrottled** |

### Detailed Analysis:
1. **Why the Cortex charges most during active work:**
   * Every step in an autonomous ReAct loop feeds the entire scratchpad history (system prompt, 20 tool schemas, retrieved episodic memories, scraped web HTML, and code diffs) back into the high-parameter model.
   * A single complex 5-step coding or research turn can consume **25,000 to 60,000 tokens**.
2. **Why the Subcortex can accumulate higher cumulative costs:**
   * The Subcortex runs asynchronously 24/7.
   * **Entity Synthesis** fires on every message event in the Redis bus.
   * **Nightly Dreaming (`03:00 UTC`)** iterates over the entire Qdrant vector memory and Neo4j concept graph to reweight edges, simulate counterfactual solutions, and prune stale nodes.
3. **Cost Optimization Best Practice:**
   Set `NEXUS_BACKGROUND_LLM_BASE_URL` to a free local endpoint (e.g. Ollama or LM Studio running an 8B model) and restrict `NEXUS_AUTONOMY_HOURLY_BUDGET=20` so background dreaming costs nothing.

---

## Quick Start Guide

### 1. Installation

```bash
# Clone and enter directory
cd Nexus

# Install Python requirements
pip install -r requirements.txt

# Install Frontend dependencies and build assets
cd web && npm install && npm run build && cd ..
```

### 2. Configuration

Create your environment configuration:

```bash
cp .env.example .env
```

Configure your LLM provider and backend:

```env
# Self-contained local mode (zero external database requirements)
NEXUS_INFRA_BACKEND=memory

# NVIDIA NIM Configuration
NVIDIA_API_KEY=nvapi-your-key-here
NEXUS_LLM_PROVIDER=nvidia
NEXUS_NIM_MODEL=meta/llama-3.3-70b-instruct
NEXUS_NIM_BASE_URL=https://integrate.api.nvidia.com/v1

# Security & CORS
NEXUS_CORS_ORIGINS=*
NEXUS_JSON_LOGS=true
```

### 3. Launch Services

Start the conscious API engine:

```bash
uvicorn nexus.infrastructure.api.main:app --host 0.0.0.0 --port 8000
```

Start the Vite development frontend (with HMR):

```bash
npm run dev --prefix web -- --host 0.0.0.0 --port 3000
```

### 4. Access Interfaces

* **J.A.R.V.I.S. Second Brain OS**: `http://localhost:3000`
* **Claude Coding & Research Studio**: `http://localhost:3000/?view=claude` (or press <kbd>C</kbd>)
* **API Documentation (Swagger)**: `http://localhost:8000/docs`
* **Prometheus Metrics**: `http://localhost:8000/metrics`
* **Health & Readiness**: `http://localhost:8000/healthz` and `/readyz`

---

## Production Deployment (Docker Compose)

For high-availability production environments with persistent storage:

```bash
# Launch Redis 7, Neo4j 5, Qdrant, Celery workers, Cortex, and Prometheus
docker compose -f docker-compose.prod.yml up -d --build
```

### Production Stack Components:
* **`nexus-cortex`**: Multi-worker Uvicorn API with container health checks.
* **`nexus-worker`**: Celery worker pool executing background research and tool generation.
* **`nexus-beat`**: Celery beat dreaming scheduler (03:00 UTC).
* **`redis`**: Persistent AOF cache and event bus with 2GB RAM limits.
* **`neo4j`**: Synaptic graph database with APOC plugins and tuned heap limits.
* **`qdrant`**: Vector memory cluster with scalar quantization.
* **`prometheus`**: Automated metrics scraper querying `nexus-cortex:8000/metrics`.

---

## API Reference

### Coding & Research Studio (`/api/coding/*`)

| Endpoint | Method | Description |
|---|---|---|
| `/api/coding/chat` | POST | Conversational coding with ReAct tool chaining and artifacts |
| `/api/coding/execute` | POST | Executes Python code in the sandbox runner |
| `/api/coding/test-runner` | POST | Runs unit test suites and reports assertion outcomes |
| `/api/coding/templates` | GET | Returns preset coding, algorithm, and research templates |

### Autonomous Deep Research (`/api/research/*`)

| Endpoint | Method | Description |
|---|---|---|
| `/api/research/execute` | POST | Crawls websites, extracts text, and generates self-evolution analysis |
| `/api/research/apply-upgrade` | POST | Registers synthesized tool into ToolRegistry and Second Brain |
| `/api/research/history` | GET | Returns past research dossiers |

### NVIDIA NIM Cortex (`/api/nim/*`)

| Endpoint | Method | Description |
|---|---|---|
| `/api/nim/status` | GET | Current NIM connection status and active model |
| `/api/nim/models` | GET | List available NIM foundation models |
| `/api/nim/chat` | POST | Direct query to NVIDIA NIM LLM |
| `/api/nim/chat/stream` | POST | Server-Sent Events (SSE) token-by-token streaming |
| `/api/nim/configure` | POST | Dynamically update NIM API key or active model |

### Telemetry & Observability

| Endpoint | Method | Description |
|---|---|---|
| `/healthz` | GET, HEAD | Lightweight liveness probe |
| `/readyz` | GET, HEAD | Deep dependency readiness probe |
| `/metrics` | GET | Prometheus text exposition format |
| `/ws/telemetry` | WebSocket | Real-time push stream for HUD telemetry |
| `/api/system/telemetry` | GET | JSON telemetry summary for HUD gauges |

---

## Testing

NEXUS includes a 240+ test suite covering unit operations, production hardening, real-world algorithmic problems, and self-evolution:

```bash
# Run all unit tests
pytest tests/unit -q

# Run real-world coding and research tests
pytest tests/unit/test_coding_assistant_real_world.py -v

# Run recursive self-evolution tests
pytest tests/unit/test_self_evolution_research.py -v

# Run production hardening tests (SSRF, metrics, probes, webhooks)
pytest tests/unit/test_production_hardening.py -v
```

---

## License

MIT &copy; 2026 lolllll212/Nexus contributors.
