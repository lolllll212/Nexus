"""
Graph API - Force-directed knowledge graph for the AI WORKSHOP OS & HOLO frontend.

Uses the established hexagonal ports (ConceptRepository / MemoryRepository)
via the DI container. When repository has no seeded concepts, serves a rich
production-grade Second Brain graph structured into the core Hubs
(Skill Suites, Local Businesses, AI Workshop, Claude Code) and node types
(Router, Concepts, Suites, Skills, Tools, Worlds, Notes, Files).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from nexus.infrastructure.api.dependencies import get_container, require_identity
from nexus.infrastructure.di.container import Container

router = APIRouter(prefix="/api", tags=["graph"], dependencies=[Depends(require_identity)])

DYNAMIC_GRAPH_NODES: list[dict[str, Any]] = []
DYNAMIC_GRAPH_LINKS: list[dict[str, Any]] = []


def inject_dynamic_graph_node(
    node_id: str,
    group: str = "Concepts",
    hub: str = "AI Workshop",
    desc: str = "",
    target_link: str = "AI Workshop",
    val: float = 12.0,
) -> dict[str, Any]:
    """Dynamically register a new node into the live Second Brain knowledge graph."""
    node = {
        "id": node_id,
        "group": group,
        "val": val,
        "hub": hub,
        "desc": desc,
    }
    if not any(n["id"] == node_id for n in DYNAMIC_GRAPH_NODES):
        DYNAMIC_GRAPH_NODES.append(node)
        DYNAMIC_GRAPH_LINKS.append({"source": target_link, "target": node_id})
    return node


def get_default_second_brain_graph() -> dict[str, Any]:
    """
    Generate rich, highly realistic Second Brain knowledge graph data
    organized by the 4 Top Hubs and 8 Node Types.
    """
    raw_nodes = [
        # Top Hubs & Routers
        {
            "id": "Neural Cortex Router",
            "group": "Router",
            "val": 14,
            "hub": "AI Workshop",
            "desc": "Central message router coordinating conscious ReAct loops and subconscious synthesis.",
        },
        {
            "id": "Subconscious Bus",
            "group": "Router",
            "val": 12,
            "hub": "AI Workshop",
            "desc": "Async Redis event bus for entity synthesis, pattern detection, and dreaming.",
        },
        {
            "id": "Fast-Twitch FastRouter",
            "group": "Router",
            "val": 11,
            "hub": "Skill Suites",
            "desc": "Low-latency streaming router dispatching quick reflexes and tools.",
        },
        {
            "id": "Spatial Fourier Router",
            "group": "Router",
            "val": 10,
            "hub": "Claude Code",
            "desc": "Fourier grid navigation and multi-dimensional concept routing.",
        },
        # 1. AI Workshop Hub & Cluster
        {
            "id": "AI Workshop",
            "group": "Suites",
            "val": 16,
            "hub": "AI Workshop",
            "desc": "Autonomous ReAct agent nucleus, tool registry, dreaming, and cognitive architecture.",
        },
        {
            "id": "NVIDIA NIM Accelerator",
            "group": "Tools",
            "val": 13,
            "hub": "AI Workshop",
            "desc": "NVIDIA Inference Microservices API for high-throughput Llama 3.3 & Nemotron inference.",
        },
        {
            "id": "ReAct Reasoning Engine",
            "group": "Concepts",
            "val": 11,
            "hub": "AI Workshop",
            "desc": "Autonomous Thought-Action-Observation multi-step reasoning cycle.",
        },
        {
            "id": "Dynamic Tool Registry",
            "group": "Tools",
            "val": 10,
            "hub": "AI Workshop",
            "desc": "Extensible registry mapping 13+ builtin tools plus dynamic runtime-generated tools.",
        },
        {
            "id": "Synaptic Graph Weaver",
            "group": "Concepts",
            "val": 9,
            "hub": "AI Workshop",
            "desc": "Graph neural linker maintaining synaptic weights and neuroplastic decay.",
        },
        {
            "id": "Episodic Memory Bank",
            "group": "Concepts",
            "val": 9,
            "hub": "AI Workshop",
            "desc": "Qdrant vector collection storing compressed memories and conversation turns.",
        },
        {
            "id": "Vector Embedder",
            "group": "Tools",
            "val": 8,
            "hub": "AI Workshop",
            "desc": "High-dimensional embedding pipeline converting text to 1536d semantic coordinates.",
        },
        {
            "id": "Dream Consolidator",
            "group": "Concepts",
            "val": 8,
            "hub": "AI Workshop",
            "desc": "Nightly batch process pruning stale concepts and consolidating realizations.",
        },
        {
            "id": "Self-Evolution Protocol",
            "group": "Concepts",
            "val": 8,
            "hub": "AI Workshop",
            "desc": "Code generation pipeline creating, sandboxing, and testing new tools autonomously.",
        },
        {
            "id": "Celery Task Beat",
            "group": "Tools",
            "val": 7,
            "hub": "AI Workshop",
            "desc": "Periodic background workers managing dream schedules and pattern sweeps.",
        },
        {
            "id": "Subprocess Sandbox",
            "group": "Worlds",
            "val": 7,
            "hub": "AI Workshop",
            "desc": "Isolated runtime environment executing generated code safely.",
        },
        {
            "id": "Docker Sandbox",
            "group": "Worlds",
            "val": 8,
            "hub": "AI Workshop",
            "desc": "Containerized environment for high-security code execution.",
        },
        # 2. Skill Suites Hub & Cluster
        {
            "id": "Skill Suites",
            "group": "Suites",
            "val": 15,
            "hub": "Skill Suites",
            "desc": "Curated collections of agent competencies, swarm workers, and workflows.",
        },
        {
            "id": "Code Synthesis Suite",
            "group": "Suites",
            "val": 10,
            "hub": "Skill Suites",
            "desc": "Autonomous Python/TypeScript code generation, testing, and linting.",
        },
        {
            "id": "Security Audit Suite",
            "group": "Suites",
            "val": 9,
            "hub": "Skill Suites",
            "desc": "AST vulnerability scanner, prompt injection defender, and quota enforcer.",
        },
        {
            "id": "Agent Swarm Orchestrator",
            "group": "Suites",
            "val": 11,
            "hub": "Skill Suites",
            "desc": "Multi-agent coordinator distributing concurrent tasks across worker agents.",
        },
        {
            "id": "Data Ingestion Pipeline",
            "group": "Suites",
            "val": 8,
            "hub": "Skill Suites",
            "desc": "Document parser, Markdown chunker, and knowledge extractor.",
        },
        {
            "id": "Multi-Modal Speech Suite",
            "group": "Suites",
            "val": 9,
            "hub": "Skill Suites",
            "desc": "Whisper STT and TTS speech generation for vocal Iron Man interface.",
        },
        {
            "id": "Autonomous Self-Heal Suite",
            "group": "Suites",
            "val": 10,
            "hub": "Skill Suites",
            "desc": "Dynamic exception interceptor repairing broken tool schemas on the fly.",
        },
        {
            "id": "Python Metaprogramming",
            "group": "Skills",
            "val": 7,
            "hub": "Skill Suites",
            "desc": "Runtime dynamic code evaluation, AST manipulation, and typing inspect.",
        },
        {
            "id": "Async Streaming Protocol",
            "group": "Skills",
            "val": 6,
            "hub": "Skill Suites",
            "desc": "Server-Sent Events streaming token deltas at 60fps.",
        },
        {
            "id": "Prompt Engineering Matrix",
            "group": "Skills",
            "val": 7,
            "hub": "Skill Suites",
            "desc": "Few-shot calibration, ReAct steering, and structured JSON output prompts.",
        },
        {
            "id": "Tool Schema Generation",
            "group": "Skills",
            "val": 6,
            "hub": "Skill Suites",
            "desc": "Automated JSONSchema extraction from Python callable signatures.",
        },
        {
            "id": "Token Budget Manager",
            "group": "Skills",
            "val": 6,
            "hub": "Skill Suites",
            "desc": "Sliding window rate-limiter and daily quota calculation.",
        },
        {
            "id": "Subconscious Realization",
            "group": "Concepts",
            "val": 8,
            "hub": "Skill Suites",
            "desc": "Heuristic discovery when two concepts form strong synaptic resonance.",
        },
        # 3. Local Businesses Hub & Cluster
        {
            "id": "Local Businesses",
            "group": "Suites",
            "val": 14,
            "hub": "Local Businesses",
            "desc": "Enterprise integrations, automated workflows, and CRM operations.",
        },
        {
            "id": "CRM Database Sync",
            "group": "Tools",
            "val": 8,
            "hub": "Local Businesses",
            "desc": "Sync customer records, contacts, and interaction history.",
        },
        {
            "id": "Inventory Tracker",
            "group": "Tools",
            "val": 7,
            "hub": "Local Businesses",
            "desc": "Real-time stock alerts, inventory forecasting, and reorder triggers.",
        },
        {
            "id": "Lead Enrichment Engine",
            "group": "Skills",
            "val": 8,
            "hub": "Local Businesses",
            "desc": "Web scraping and public registry lookup for client prospecting.",
        },
        {
            "id": "Local SEO Optimizer",
            "group": "Skills",
            "val": 7,
            "hub": "Local Businesses",
            "desc": "Keyword density analyzer, Google My Business review summarizer.",
        },
        {
            "id": "Customer Voice Agent",
            "group": "Suites",
            "val": 9,
            "hub": "Local Businesses",
            "desc": "Voice-enabled J.A.R.V.I.S. answering incoming business inquiries.",
        },
        {
            "id": "Invoice Dispatcher",
            "group": "Tools",
            "val": 7,
            "hub": "Local Businesses",
            "desc": "PDF invoice generator and payment status webhook tracker.",
        },
        {
            "id": "Tenant Quota Isolation",
            "group": "Concepts",
            "val": 8,
            "hub": "Local Businesses",
            "desc": "Multi-tenant boundary enforcement and per-organization limits.",
        },
        {
            "id": "PostgreSQL Ledger",
            "group": "Worlds",
            "val": 8,
            "hub": "Local Businesses",
            "desc": "Transactional database storing accounting records and audit trails.",
        },
        {
            "id": "Webhook Dispatch Mesh",
            "group": "Tools",
            "val": 6,
            "hub": "Local Businesses",
            "desc": "HMAC-signed webhook emitters notifying external web services.",
        },
        {
            "id": "Business Metric Dash",
            "group": "Notes",
            "val": 5,
            "hub": "Local Businesses",
            "desc": "KPI aggregation: MRR, active users, pipeline velocity.",
        },
        # 4. Claude Code Hub & Cluster
        {
            "id": "Claude Code",
            "group": "Suites",
            "val": 15,
            "hub": "Claude Code",
            "desc": "Deep codebase intelligence, refactoring agents, and continuous integration.",
        },
        {
            "id": "AST Semantic Parser",
            "group": "Tools",
            "val": 8,
            "hub": "Claude Code",
            "desc": "Abstract Syntax Tree inspection verifying code compliance and safety.",
        },
        {
            "id": "Auto-Patch Generator",
            "group": "Tools",
            "val": 9,
            "hub": "Claude Code",
            "desc": "Unified diff generator applying precision code edits across files.",
        },
        {
            "id": "Git Automation Daemon",
            "group": "Tools",
            "val": 8,
            "hub": "Claude Code",
            "desc": "Automatic git branch management, commits, and pull requests.",
        },
        {
            "id": "Test Harness Driver",
            "group": "Tools",
            "val": 8,
            "hub": "Claude Code",
            "desc": "Pytest runner executing unit, eval, and regression suites.",
        },
        {
            "id": "Linter Feedback Loop",
            "group": "Skills",
            "val": 7,
            "hub": "Claude Code",
            "desc": "Ruff, flake8, and black syntax verification loop.",
        },
        {
            "id": "Architecture Compliance",
            "group": "Concepts",
            "val": 8,
            "hub": "Claude Code",
            "desc": "Hexagonal boundary verification: domain never imports infrastructure.",
        },
        {
            "id": "Continuous CI Pipeline",
            "group": "Worlds",
            "val": 7,
            "hub": "Claude Code",
            "desc": "GitHub Actions workflow validating automated pull requests.",
        },
        {
            "id": "Coding Examples Corpus",
            "group": "Files",
            "val": 6,
            "hub": "Claude Code",
            "desc": "Curated repository of algorithmic solutions and data structures.",
        },
        # Tools Cluster
        {
            "id": "read_file",
            "group": "Tools",
            "val": 6,
            "hub": "Claude Code",
            "desc": "Read arbitrary text or configuration files safely.",
        },
        {
            "id": "write_file",
            "group": "Tools",
            "val": 6,
            "hub": "Claude Code",
            "desc": "Create or overwrite files with automated safety guards.",
        },
        {
            "id": "run_python",
            "group": "Tools",
            "val": 7,
            "hub": "AI Workshop",
            "desc": "Execute Python scripts inside the sandboxed environment.",
        },
        {
            "id": "run_shell",
            "group": "Tools",
            "val": 7,
            "hub": "AI Workshop",
            "desc": "Execute shell commands with timeout and output capture.",
        },
        {
            "id": "web_search",
            "group": "Tools",
            "val": 7,
            "hub": "Skill Suites",
            "desc": "Search web endpoints for real-time live data retrieval.",
        },
        {
            "id": "calculator",
            "group": "Tools",
            "val": 5,
            "hub": "Skill Suites",
            "desc": "AST-safe mathematical expression evaluator.",
        },
        {
            "id": "system_info",
            "group": "Tools",
            "val": 5,
            "hub": "AI Workshop",
            "desc": "Inspect CPU, memory, OS uptime, and process status.",
        },
        {
            "id": "diff_text",
            "group": "Tools",
            "val": 5,
            "hub": "Claude Code",
            "desc": "Compute visual unified diff between two code buffers.",
        },
        # Worlds & Simulation Clusters
        {
            "id": "Stark Industries Sim",
            "group": "Worlds",
            "val": 9,
            "hub": "AI Workshop",
            "desc": "J.A.R.V.I.S. simulated runtime with tactile HUD and holographic overlays.",
        },
        {
            "id": "Apollo 11 Capsule",
            "group": "Worlds",
            "val": 8,
            "hub": "AI Workshop",
            "desc": "Smithsonian 3D photogrammetry scan grabbable in mid-air.",
        },
        {
            "id": "Triceratops BioSphere",
            "group": "Worlds",
            "val": 8,
            "hub": "AI Workshop",
            "desc": "High-fidelity paleontological 3D model with skeletal mesh.",
        },
        {
            "id": "Production Cloud",
            "group": "Worlds",
            "val": 8,
            "hub": "Local Businesses",
            "desc": "Railway / Vercel deployment targets with live SSL endpoints.",
        },
        # Notes Cluster
        {
            "id": "04-holo.md",
            "group": "Notes",
            "val": 6,
            "hub": "AI Workshop",
            "desc": "Hand-gesture control deck specifications and webcam tracking guide.",
        },
        {
            "id": "08-second-brain.md",
            "group": "Notes",
            "val": 7,
            "hub": "AI Workshop",
            "desc": "Your notes, remembered forever, answered out loud in your own voice.",
        },
        {
            "id": "agents-spec.md",
            "group": "Notes",
            "val": 6,
            "hub": "Claude Code",
            "desc": "Agent swarm taxonomy, supervisor protocol, and consensus rules.",
        },
        {
            "id": "architecture-plan.md",
            "group": "Notes",
            "val": 7,
            "hub": "AI Workshop",
            "desc": "Clean hexagonal ports & adapters specification.",
        },
        {
            "id": "nim-deployment.md",
            "group": "Notes",
            "val": 7,
            "hub": "AI Workshop",
            "desc": "NVIDIA NIM microservice container configuration and benchmarks.",
        },
        {
            "id": "daily-dream-summary.md",
            "group": "Notes",
            "val": 5,
            "hub": "AI Workshop",
            "desc": "Automated log of midnight dream consolidation and realization sparks.",
        },
        # Files Cluster
        {
            "id": "container.py",
            "group": "Files",
            "val": 6,
            "hub": "AI Workshop",
            "desc": "Composition root wiring domain ports to infrastructure adapters.",
        },
        {
            "id": "main.py",
            "group": "Files",
            "val": 6,
            "hub": "AI Workshop",
            "desc": "FastAPI conscious engine hosting REST and SSE endpoints.",
        },
        {
            "id": "holo.html",
            "group": "Files",
            "val": 5,
            "hub": "AI Workshop",
            "desc": "Holographic gesture interface with Three.js rendering.",
        },
        {
            "id": "nvidia_nim_provider.py",
            "group": "Files",
            "val": 6,
            "hub": "AI Workshop",
            "desc": "NVIDIA NIM streaming LLM adapter.",
        },
        {
            "id": "builtin_tools.py",
            "group": "Files",
            "val": 5,
            "hub": "AI Workshop",
            "desc": "Definition and schemas for all built-in core tools.",
        },
        {
            "id": "docker-compose.yml",
            "group": "Files",
            "val": 5,
            "hub": "Local Businesses",
            "desc": "Infrastructure definitions: Redis, Neo4j, Qdrant.",
        },
        {
            "id": "requirements.txt",
            "group": "Files",
            "val": 4,
            "hub": "Claude Code",
            "desc": "Pinned Python dependencies compiled by uv.",
        },
    ]

    raw_links = [
        # Inter-Hub Backbones
        {"source": "Neural Cortex Router", "target": "AI Workshop"},
        {"source": "Neural Cortex Router", "target": "Skill Suites"},
        {"source": "Neural Cortex Router", "target": "Local Businesses"},
        {"source": "Neural Cortex Router", "target": "Claude Code"},
        {"source": "Subconscious Bus", "target": "Neural Cortex Router"},
        {"source": "Subconscious Bus", "target": "AI Workshop"},
        {"source": "Fast-Twitch FastRouter", "target": "Skill Suites"},
        {"source": "Fast-Twitch FastRouter", "target": "Neural Cortex Router"},
        {"source": "Spatial Fourier Router", "target": "Claude Code"},
        {"source": "Spatial Fourier Router", "target": "Neural Cortex Router"},
        # AI Workshop Links
        {"source": "AI Workshop", "target": "NVIDIA NIM Accelerator"},
        {"source": "AI Workshop", "target": "ReAct Reasoning Engine"},
        {"source": "AI Workshop", "target": "Dynamic Tool Registry"},
        {"source": "AI Workshop", "target": "Synaptic Graph Weaver"},
        {"source": "AI Workshop", "target": "Episodic Memory Bank"},
        {"source": "AI Workshop", "target": "Vector Embedder"},
        {"source": "AI Workshop", "target": "Dream Consolidator"},
        {"source": "AI Workshop", "target": "Self-Evolution Protocol"},
        {"source": "AI Workshop", "target": "Celery Task Beat"},
        {"source": "AI Workshop", "target": "Stark Industries Sim"},
        {"source": "NVIDIA NIM Accelerator", "target": "ReAct Reasoning Engine"},
        {"source": "NVIDIA NIM Accelerator", "target": "nim-deployment.md"},
        {"source": "NVIDIA NIM Accelerator", "target": "nvidia_nim_provider.py"},
        {"source": "ReAct Reasoning Engine", "target": "run_python"},
        {"source": "ReAct Reasoning Engine", "target": "run_shell"},
        {"source": "Dynamic Tool Registry", "target": "builtin_tools.py"},
        {"source": "Dynamic Tool Registry", "target": "read_file"},
        {"source": "Dynamic Tool Registry", "target": "write_file"},
        {"source": "Synaptic Graph Weaver", "target": "Episodic Memory Bank"},
        {"source": "Dream Consolidator", "target": "daily-dream-summary.md"},
        {"source": "Episodic Memory Bank", "target": "08-second-brain.md"},
        {"source": "Self-Evolution Protocol", "target": "Subprocess Sandbox"},
        {"source": "Self-Evolution Protocol", "target": "Docker Sandbox"},
        {"source": "Stark Industries Sim", "target": "04-holo.md"},
        {"source": "Stark Industries Sim", "target": "Apollo 11 Capsule"},
        {"source": "Stark Industries Sim", "target": "Triceratops BioSphere"},
        {"source": "Stark Industries Sim", "target": "holo.html"},
        # Skill Suites Links
        {"source": "Skill Suites", "target": "Code Synthesis Suite"},
        {"source": "Skill Suites", "target": "Security Audit Suite"},
        {"source": "Skill Suites", "target": "Agent Swarm Orchestrator"},
        {"source": "Skill Suites", "target": "Data Ingestion Pipeline"},
        {"source": "Skill Suites", "target": "Multi-Modal Speech Suite"},
        {"source": "Skill Suites", "target": "Autonomous Self-Heal Suite"},
        {"source": "Skill Suites", "target": "Python Metaprogramming"},
        {"source": "Skill Suites", "target": "Prompt Engineering Matrix"},
        {"source": "Agent Swarm Orchestrator", "target": "agents-spec.md"},
        {"source": "Agent Swarm Orchestrator", "target": "Subconscious Realization"},
        {"source": "Code Synthesis Suite", "target": "Tool Schema Generation"},
        {"source": "Security Audit Suite", "target": "Token Budget Manager"},
        {"source": "Multi-Modal Speech Suite", "target": "Stark Industries Sim"},
        {"source": "Data Ingestion Pipeline", "target": "Vector Embedder"},
        {"source": "Autonomous Self-Heal Suite", "target": "Self-Evolution Protocol"},
        {"source": "Python Metaprogramming", "target": "container.py"},
        # Local Businesses Links
        {"source": "Local Businesses", "target": "CRM Database Sync"},
        {"source": "Local Businesses", "target": "Inventory Tracker"},
        {"source": "Local Businesses", "target": "Lead Enrichment Engine"},
        {"source": "Local Businesses", "target": "Local SEO Optimizer"},
        {"source": "Local Businesses", "target": "Customer Voice Agent"},
        {"source": "Local Businesses", "target": "Invoice Dispatcher"},
        {"source": "Local Businesses", "target": "Tenant Quota Isolation"},
        {"source": "Local Businesses", "target": "Production Cloud"},
        {"source": "Customer Voice Agent", "target": "Multi-Modal Speech Suite"},
        {"source": "Lead Enrichment Engine", "target": "web_search"},
        {"source": "CRM Database Sync", "target": "PostgreSQL Ledger"},
        {"source": "Invoice Dispatcher", "target": "Webhook Dispatch Mesh"},
        {"source": "Local Businesses", "target": "Business Metric Dash"},
        {"source": "Production Cloud", "target": "docker-compose.yml"},
        # Claude Code Links
        {"source": "Claude Code", "target": "AST Semantic Parser"},
        {"source": "Claude Code", "target": "Auto-Patch Generator"},
        {"source": "Claude Code", "target": "Git Automation Daemon"},
        {"source": "Claude Code", "target": "Test Harness Driver"},
        {"source": "Claude Code", "target": "Linter Feedback Loop"},
        {"source": "Claude Code", "target": "Architecture Compliance"},
        {"source": "Claude Code", "target": "Continuous CI Pipeline"},
        {"source": "Claude Code", "target": "Coding Examples Corpus"},
        {"source": "AST Semantic Parser", "target": "diff_text"},
        {"source": "Auto-Patch Generator", "target": "write_file"},
        {"source": "Test Harness Driver", "target": "requirements.txt"},
        {"source": "Architecture Compliance", "target": "architecture-plan.md"},
        {"source": "Architecture Compliance", "target": "main.py"},
        {"source": "Architecture Compliance", "target": "container.py"},
        {"source": "Claude Code", "target": "Code Synthesis Suite"},
        {"source": "Claude Code", "target": "AI Workshop"},
    ]

    all_nodes = list(raw_nodes) + list(DYNAMIC_GRAPH_NODES)
    all_links = list(raw_links) + list(DYNAMIC_GRAPH_LINKS)

    return {"nodes": all_nodes, "links": all_links}


@router.get("/graph")
async def get_graph(
    limit: int = Query(120, ge=1, le=300, description="Max concepts to seed graph"),
    min_weight: float = Query(0.0, ge=0.0, le=1.0),
    tenant_id: str = Query("default", description="Tenant scope"),
    container: Container = Depends(get_container),
) -> dict:
    """
    Return the force-graph payload for the AI WORKSHOP OS dashboard:

      {
        "nodes": [{"id": "...", "group": "...", "val": 1, "hub": "..."}, ...],
        "links": [{"source": "...", "target": "..."}, ...]
      }
    """
    repo = container.concept_repo

    try:
        concepts = await repo.find_by_label("", limit=limit, tenant_id=tenant_id)
    except Exception:
        concepts = []

    # If repo has no active concepts, return our rich Second Brain knowledge graph
    if not concepts:
        return get_default_second_brain_graph()

    # If concepts exist in the repository, merge them with the hub structure
    default_graph = get_default_second_brain_graph()
    nodes: list[dict] = list(default_graph["nodes"])
    links: list[dict] = list(default_graph["links"])
    seen: set[str] = {n["id"] for n in nodes}

    for c in concepts:
        grp = getattr(c, "concept_type", "Concepts") or "Concepts"
        # Map concept_type into the 8 filter categories
        type_mapping = {
            "topic": "Concepts",
            "concept": "Concepts",
            "tool": "Tools",
            "suite": "Suites",
            "skill": "Skills",
            "world": "Worlds",
            "memory": "Notes",
            "file": "Files",
            "router": "Router",
        }
        mapped_grp = type_mapping.get(grp.lower(), "Concepts")
        nid = c.label or c.id
        if nid not in seen:
            seen.add(nid)
            val = max(4.0, min(14.0, float(getattr(c, "strength", 1.0) or 1.0) * 4))
            nodes.append(
                {
                    "id": nid,
                    "group": mapped_grp,
                    "val": val,
                    "hub": "AI Workshop",
                    "desc": f"Repository concept: {nid} ({mapped_grp})",
                }
            )
            links.append({"source": "AI Workshop", "target": nid})

    return {"nodes": nodes, "links": links}
