"""Cosmos API - the NEXUS automation mesh behind the JARVIS-style UI.

The cosmos is the system's live joint structure: every subsystem is a NODE
(core, memory, concepts, tools, swarm, dream, integrations), every edge is a
data-flow link. ``GET /api/cosmos`` merges the static mesh declared in
``frontend/config/nexus.config.json`` with LIVE status pulled from the DI
container (ports only), and ``POST /api/cosmos/trigger`` runs the automation
attached to a node (dream cycle, swarm run, tool generation, integration
toggle, ...). Reads are public like ``/api/graph``; triggers require identity
(the local-UI bypass makes the shipped deck seamless on localhost).
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexus.domain.value_objects.identity import Identity
from nexus.infrastructure.api.dependencies import get_container, require_identity
from nexus.infrastructure.api.paths import frontend_dir
from nexus.infrastructure.di.container import Container

router = APIRouter(prefix="/api", tags=["cosmos"])

_FALLBACK_MESH = {
    "nodes": [
        {
            "id": "N.E.X.U.S",
            "group": "core",
            "val": 18,
            "color": "#ffcf7d",
            "desc": "Neural EXpansion Unified System — conscious + subconscious loops",
        },
        {
            "id": "H.O.L.O",
            "group": "ui",
            "val": 12,
            "color": "#7dffd9",
            "desc": "Hand-gesture deck / 3D stage",
        },
        {
            "id": "memory",
            "group": "memory",
            "val": 8,
            "color": "#a9ffe6",
            "desc": "Vector + episodic memory stores",
        },
        {"id": "concept", "group": "concept", "val": 8, "color": "#c9ffe6", "desc": "Synaptic concept graph"},
        {"id": "swarm", "group": "swarm", "val": 7, "color": "#d9fff2", "desc": "Multi-agent orchestration"},
        {"id": "dream", "group": "subconscious", "val": 7, "color": "#ffe9c4", "desc": "Dreaming pipeline"},
        {
            "id": "tools",
            "group": "self-evolution",
            "val": 7,
            "color": "#9dffe4",
            "desc": "Self-generated tools",
        },
        {"id": "gmail", "group": "integration", "val": 6, "color": "#ea4335", "desc": "Gmail bridge"},
        {"id": "drive", "group": "integration", "val": 6, "color": "#34a853", "desc": "Drive bridge"},
        {"id": "github", "group": "integration", "val": 6, "color": "#4078c0", "desc": "GitHub bridge"},
        {"id": "whatsapp", "group": "integration", "val": 6, "color": "#25D366", "desc": "WhatsApp bridge"},
        {"id": "telegram", "group": "integration", "val": 6, "color": "#229ED9", "desc": "Telegram bot bridge"},
        {"id": "threads", "group": "integration", "val": 6, "color": "#d9d9d9", "desc": "Threads bridge"},
        {
            "id": "social",
            "group": "integration",
            "val": 7,
            "color": "#ff7a59",
            "desc": "Social media automation — RUN drafts a cross-post",
        },
        {"id": "youtube", "group": "integration", "val": 6, "color": "#ff4e45", "desc": "YouTube bridge"},
    ],
    "links": [
        {"source": "N.E.X.U.S", "target": "H.O.L.O", "weight": 1.0},
        {"source": "N.E.X.U.S", "target": "memory", "weight": 0.9},
        {"source": "N.E.X.U.S", "target": "concept", "weight": 0.9},
        {"source": "N.E.X.U.S", "target": "swarm", "weight": 0.8},
        {"source": "N.E.X.U.S", "target": "dream", "weight": 0.8},
        {"source": "N.E.X.U.S", "target": "tools", "weight": 0.7},
        {"source": "N.E.X.U.S", "target": "social", "weight": 0.8},
        {"source": "social", "target": "threads", "weight": 0.75},
        {"source": "social", "target": "youtube", "weight": 0.75},
        {"source": "social", "target": "whatsapp", "weight": 0.7},
        {"source": "social", "target": "telegram", "weight": 0.7},
        {"source": "social", "target": "swarm", "weight": 0.8},
        {"source": "gmail", "target": "memory", "weight": 0.6},
        {"source": "drive", "target": "memory", "weight": 0.6},
        {"source": "github", "target": "concept", "weight": 0.6},
        {"source": "whatsapp", "target": "memory", "weight": 0.6},
        {"source": "telegram", "target": "memory", "weight": 0.6},
        {"source": "memory", "target": "concept", "weight": 0.9},
        {"source": "memory", "target": "dream", "weight": 0.7},
        {"source": "tools", "target": "swarm", "weight": 0.6},
    ],
}

# Bridges whose only automation today is a persisted enable flag (the real
# bridge lands via OAuth/plugin later). "social" is special: RUN drafts a
# cross-post through the swarm instead of toggling a flag.
_DEFAULT_INTEGRATIONS = (
    "gmail",
    "drive",
    "github",
    "whatsapp",
    "telegram",
    "threads",
    "youtube",
)
_AUTOMATION_INTEGRATIONS = ("social",)


def _integration_ids(cfg_json: dict | None = None) -> set:
    """Integration node ids = config-declared ∪ built-in defaults."""
    declared = set((cfg_json or _load_config()).get("integrations", {}).keys())
    return declared | set(_DEFAULT_INTEGRATIONS) | set(_AUTOMATION_INTEGRATIONS)


# --------------------------------------------------------------------------
# Config + state helpers
# --------------------------------------------------------------------------


def _load_config() -> dict[str, Any]:
    root = frontend_dir()
    if root is not None:
        try:
            return json.loads((root / "config" / "nexus.config.json").read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _integrations_state_path() -> str | None:
    root = frontend_dir()
    if root is None:
        return None
    try:
        os.makedirs(root / "state", exist_ok=True)
    except OSError:
        return None
    return str(root / "state" / "cosmos-integrations.json")


def _load_integrations_state() -> dict[str, bool]:
    path = _integrations_state_path()
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {k: bool(v) for k, v in data.items() if isinstance(k, str)}
    except Exception:
        return {}


def _save_integrations_state(state: dict[str, bool]) -> bool:
    path = _integrations_state_path()
    if not path:
        return False
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------
# LLM (LM Studio) status probe — cached so the UI can poll cheaply
# --------------------------------------------------------------------------

_LLM_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_LLM_CACHE_TTL = 15.0


def _llm_kind(base_url: str | None) -> str:
    b = (base_url or "").lower()
    if ":1234" in b:
        return "LM Studio"
    if ":11434" in b:
        return "Ollama"
    if "api.openai.com" in b:
        return "OpenAI"
    return "OpenAI-compatible"


async def llm_status(container: Container, force: bool = False) -> dict[str, Any]:
    """Probe the configured OpenAI-compatible endpoint (LM Studio by default)."""
    now = time.time()
    if not force and _LLM_CACHE["data"] is not None and now - _LLM_CACHE["ts"] < _LLM_CACHE_TTL:
        return _LLM_CACHE["data"]

    cfg = getattr(container, "config", None)
    model = getattr(cfg, "llm_model", None) or "unknown"
    base_url = getattr(cfg, "llm_base_url", None) or "https://api.openai.com/v1"
    bg_model = getattr(cfg, "background_llm_model", None) or model
    embed_model = getattr(cfg, "embedding_model", None)
    kind = _llm_kind(base_url)

    reachable = False
    latency_ms: float | None = None
    models: list[str] = []
    error: str | None = None
    url = base_url.rstrip("/") + "/models"
    headers = {}
    api_key = getattr(cfg, "openai_api_key", "") or "local-no-key"
    headers["Authorization"] = f"Bearer {api_key}"
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.5, connect=1.2)) as client:
            resp = await client.get(url, headers=headers)
        latency_ms = (time.perf_counter() - started) * 1000
        if resp.status_code == 200:
            reachable = True
            try:
                payload = resp.json()
                models = [m.get("id", "?") for m in (payload.get("data") or [])][:8]
            except Exception:
                models = []
        else:
            error = f"HTTP {resp.status_code}"
    except Exception as exc:  # connection refused etc — offline is normal locally
        error = type(exc).__name__
        latency_ms = (time.perf_counter() - started) * 1000

    data = {
        "kind": kind,
        "base_url": base_url,
        "model": model,
        "background_model": bg_model,
        "embedding_model": embed_model,
        "reachable": reachable,
        "latency_ms": round(latency_ms or 0.0, 1),
        "models_loaded": models,
        "error": error,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    _LLM_CACHE.update({"ts": time.time(), "data": data})
    return data


@router.get("/llm/status")
async def get_llm_status(
    force: bool = False,
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Live status of the chat LLM (LM Studio on localhost:1234 by default)."""
    return await llm_status(container, force=force)


# --------------------------------------------------------------------------
# Live node status
# --------------------------------------------------------------------------


async def _safe(coro, default=None):
    try:
        return await coro
    except Exception:
        return default


def _recent(container: Container, kind: str, limit: int) -> list[dict[str, Any]]:
    feed = getattr(container, "activity_feed", None)
    if feed is None:
        return []
    try:
        return list(feed.recent(kind, limit=limit))
    except Exception:
        return []


async def _node_status(node_id: str, container: Container, ctx: dict[str, Any]) -> dict[str, Any]:
    """Compute a node's live status + a short detail string for the UI."""
    if node_id == "N.E.X.U.S":
        llm = ctx["llm"]
        state = "online" if llm["reachable"] else "degraded"
        detail = f"{llm['kind']}: {llm['model']}" + (
            f" · {llm['latency_ms']:.0f}ms" if llm["reachable"] else " · offline"
        )
        return {"status": state, "detail": detail, "triggerable": True, "action": "pulse"}

    if node_id == "H.O.L.O":
        return {
            "status": "online" if frontend_dir() is not None else "offline",
            "detail": "gesture deck + cosmos stage",
            "triggerable": True,
            "action": "state",
        }

    if node_id == "memory":
        return {
            "status": "online",
            "detail": "vector + episodic stores",
            "triggerable": True,
            "action": "digest",
        }

    if node_id == "concept":
        count = ctx.get("concept_count")
        return {
            "status": "online",
            "detail": f"{count} concepts indexed" if count is not None else "synaptic graph",
            "triggerable": True,
            "action": "stats",
            "stats": {"concepts": count},
        }

    if node_id == "swarm":
        count = ctx.get("swarm_count", 0)
        agents = ctx.get("agent_count", 0)
        return {
            "status": "online" if (count or agents) else "idle",
            "detail": f"{count} swarms · {agents} agents",
            "triggerable": True,
            "action": "run",
            "stats": {"swarms": count, "agents": agents},
        }

    if node_id == "dream":
        dreams = ctx.get("dreams", [])
        last = dreams[0] if dreams else None
        detail = f"last cycle {last.get('session_id', '?')[:8]}" if last else "no cycles yet — press RUN"
        return {
            "status": "idle",
            "detail": detail,
            "triggerable": True,
            "action": "dream",
            "stats": {"recent_cycles": len(dreams)},
        }

    if node_id == "tools":
        tools = ctx.get("tools", [])
        self_gen = sum(1 for t in tools if getattr(t, "is_self_generated", False))
        return {
            "status": "online",
            "detail": f"{len(tools)} tools · {self_gen} self-made",
            "triggerable": True,
            "action": "generate",
            "stats": {"tools": len(tools), "self_generated": self_gen},
        }

    if node_id in _integration_ids(ctx["config"]):
        enabled = ctx["integrations_state"].get(node_id, False)
        cfg = ctx["config"].get("integrations", {}).get(node_id, {})
        oauth_cfg = cfg.get("oauth", {})
        env_name = oauth_cfg.get("clientIdEnv")
        configured = bool(env_name and os.getenv(env_name))
        status = "enabled" if enabled else ("configured" if configured else "disabled")
        detail = "bridge active" if enabled else ("credentials configured" if configured else "not configured")
        if node_id == "social":
            return {
                "status": status,
                "detail": "drafts cross-posts via the swarm"
                + ("" if enabled else " · flag off (RUN still works)"),
                "triggerable": True,
                "action": "run_social",
                "stats": {"enabled": enabled, "configured": True},
            }
        return {
            "status": status,
            "detail": detail,
            "triggerable": True,
            "action": "toggle",
            "stats": {"enabled": enabled, "configured": configured},
        }

    return {"status": "online", "detail": "mesh member", "triggerable": False}


async def build_cosmos(container: Container, tenant_id: str = "default") -> dict[str, Any]:
    cfg_json = _load_config()
    mesh = cfg_json.get("cosmos") or _FALLBACK_MESH
    llm = await llm_status(container)

    concept_repo = getattr(container, "concept_repo", None)
    concept_count: int | None = None
    if concept_repo is not None:
        concepts = await _safe(concept_repo.find_by_label("", limit=200, tenant_id=tenant_id), [])
        if concepts is not None:
            concept_count = len(concepts)

    swarms = await _safe(container.list_swarms.execute(tenant_id), []) or []
    agents = await _safe(container.list_agents.execute(tenant_id), []) or []
    tools = await _safe(container.tool_registry.list_all(), []) or []
    dreams = _recent(container, "dream", 5)
    cosmos_events = _recent(container, "cosmos", 25)

    last_runs: dict[str, dict[str, Any]] = {}
    for ev in cosmos_events:
        node = ev.get("node")
        if node and node not in last_runs:
            last_runs[node] = ev

    ctx: dict[str, Any] = {
        "llm": llm,
        "config": cfg_json,
        "integrations_state": _load_integrations_state(),
        "concept_count": concept_count,
        "swarm_count": len(swarms),
        "agent_count": len(agents),
        "tools": list(tools),
        "dreams": dreams,
    }

    nodes: list[dict[str, Any]] = []
    for n in mesh.get("nodes", []):
        node = dict(n)
        info = await _node_status(node.get("id", ""), container, ctx)
        node.update(info)
        lr = last_runs.get(node.get("id"))
        if lr:
            node["last_run"] = {
                "ok": lr.get("ok"),
                "summary": lr.get("summary", ""),
                "ts": lr.get("ts"),
            }
        nodes.append(node)

    return {
        "system": cfg_json.get("system", "N.E.X.U.S"),
        "tagline": cfg_json.get("tagline", "a new kind of brain — cosmos joint"),
        "nodes": nodes,
        "links": mesh.get("links", []),
        "llm": llm,
        "activity": cosmos_events[:10],
        "counts": {
            "nodes": len(nodes),
            "links": len(mesh.get("links", [])),
            "concepts": concept_count,
            "tools": len(tools),
            "swarms": len(swarms),
            "agents": len(agents),
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/cosmos")
async def get_cosmos(
    tenant_id: str = "default",
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """The live automation mesh: config-declared joints + real-time status."""
    return await build_cosmos(container, tenant_id=tenant_id)


# --------------------------------------------------------------------------
# Triggers — run the automation attached to a mesh node
# --------------------------------------------------------------------------


class TriggerRequest(BaseModel):
    node: str = Field(..., min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


async def _ensure_cosmos_swarm(container: Container, tenant_id: str, owner_id: str):
    agents = await container.list_agents.execute(tenant_id)
    agent = next((a for a in agents if a.name == "cosmos-worker"), None)
    if agent is None:
        agent = await container.register_agent.execute(
            name="cosmos-worker",
            tenant_id=tenant_id,
            owner_id=owner_id,
            system_prompt=(
                "You are a NEXUS cosmos automation worker. Answer in one short "
                "paragraph, factual and direct."
            ),
            role="worker",
        )
    swarms = await container.list_swarms.execute(tenant_id)
    swarm = next((s for s in swarms if s.name == "cosmos-mesh"), None)
    if swarm is None:
        swarm = await container.create_swarm.execute(
            name="cosmos-mesh",
            tenant_id=tenant_id,
            owner_id=owner_id,
            leader_id=agent.id,
            worker_ids=[agent.id],
        )
    return swarm


async def _run_trigger(
    node: str, params: dict[str, Any], identity: Identity, container: Container
) -> dict[str, Any]:
    tenant_id = identity.tenant_id

    if node == "N.E.X.U.S":
        llm = await llm_status(container, force=True)
        concepts = await _safe(container.concept_repo.find_by_label("", limit=200, tenant_id=tenant_id), [])
        tools = await _safe(container.tool_registry.list_all(), []) or []
        summary = (
            f"Core pulse: LLM {llm['kind']} {'online' if llm['reachable'] else 'unreachable'} "
            f"({llm['model']}), {len(concepts or [])} concepts, {len(tools)} tools loaded."
        )
        return {"ok": True, "kind": "pulse", "summary": summary, "llm": llm}

    if node == "H.O.L.O":
        from nexus.infrastructure.api.routes.holo import get_holo_state

        state = await get_holo_state()
        return {
            "ok": True,
            "kind": "state",
            "summary": (
                f"Deck state: last event '{state.get('event', 'none')}'"
                + (f" on '{state.get('card')}'" if state.get("card") else "")
            ),
            "state": state,
        }

    if node == "dream":
        result = await container.dream_session.run()
        return {
            "ok": True,
            "kind": "dream",
            "summary": f"Dream cycle complete (session {result.session_id[:8]}…)",
            "session_id": result.session_id,
        }

    if node == "swarm":
        task = str(params.get("task") or "Summarize your role in the NEXUS mesh in one line.")
        swarm = await _ensure_cosmos_swarm(container, tenant_id, identity.user_id)
        result = await container.swarm_coordinator.run(swarm, task, tenant_id)
        return {
            "ok": True,
            "kind": "swarm",
            "summary": (result.final_response or "")[:400],
            "task": task,
            "swarm_id": swarm.id,
            "worker_responses": result.worker_responses,
            "session_id": result.session_id,
        }

    if node == "tools":
        problem = str(params.get("problem_statement") or params.get("description") or "").strip()
        if not problem or len(problem) < 10:
            tools = await _safe(container.tool_registry.list_all(), []) or []
            return {
                "ok": True,
                "kind": "tools",
                "summary": (
                    f"{len(tools)} tools loaded. Pass params.problem_statement (>=10 chars) "
                    "to self-evolve a new one."
                ),
                "tools": [getattr(t, "name", str(t)) for t in tools][:40],
                "skipped": True,
            }
        from nexus.application.tools.generate_tool import ToolSpecRequest

        result = await container.tool_generator.execute(
            ToolSpecRequest(
                name=str(params.get("name") or f"cosmos_tool_{int(time.time())}"),
                description=str(params.get("description") or problem[:200]),
                problem_statement=problem,
                requirements=list(params.get("requirements") or []),
                input_examples=list(params.get("input_examples") or []),
                expected_outputs=list(params.get("expected_outputs") or []),
            )
        )
        return {
            "ok": True,
            "kind": "generate",
            "summary": f"Tool '{getattr(result, 'name', '?')}' generated "
            f"({getattr(result, 'tests_passed', 0)} tests passed)",
            "tool_id": getattr(result, "tool_id", None),
            "tests_passed": getattr(result, "tests_passed", 0),
        }

    if node == "concept":
        concepts = (
            await _safe(container.concept_repo.find_by_label("", limit=200, tenant_id=tenant_id), []) or []
        )
        strengths = sorted(
            ((getattr(c, "label", "?"), float(getattr(c, "strength", 0.0) or 0.0)) for c in concepts),
            key=lambda kv: kv[1],
            reverse=True,
        )
        top = [label for label, _ in strengths[:10]]
        return {
            "ok": True,
            "kind": "stats",
            "summary": f"Concept graph: {len(concepts)} concepts. Strongest: "
            + (", ".join(top[:5]) if top else "none yet"),
            "concepts": len(concepts),
            "top": top,
        }

    if node == "memory":
        concepts = await _safe(container.concept_repo.find_by_label("", limit=200, tenant_id=tenant_id), [])
        dreams = _recent(container, "dream", 3)
        from nexus.infrastructure.api.routes.holo import get_holo_state

        state = await get_holo_state()
        return {
            "ok": True,
            "kind": "digest",
            "summary": (
                f"Memory digest: {len(concepts or [])} concepts indexed, "
                f"{len(dreams)} recent dream cycles, last gesture "
                f"'{state.get('event', 'none')}'."
            ),
        }

    if node == "social":
        # Social media automation: the swarm drafts the cross-post; bridges of
        # threads/youtube/whatsapp/telegram/instagram carry it out once enabled.
        task = str(
            params.get("task")
            or "Draft one short social post (max 2 lines) about what NEXUS has "
            "been working on. No hashtags. Plain text only."
        )
        swarm = await _ensure_cosmos_swarm(container, tenant_id, identity.user_id)
        result = await container.swarm_coordinator.run(swarm, task, tenant_id)
        state = _load_integrations_state()
        state["social"] = True
        _save_integrations_state(state)
        return {
            "ok": True,
            "kind": "social",
            "summary": (result.final_response or "")[:400],
            "draft": (result.final_response or "")[:800],
            "task": task,
            "session_id": result.session_id,
        }

    if node in _integration_ids():
        state = _load_integrations_state()
        requested = params.get("enabled")
        state[node] = (not state.get(node, False)) if requested is None else bool(requested)
        persisted = _save_integrations_state(state)
        return {
            "ok": True,
            "kind": "toggle",
            "summary": f"{node} bridge {'ENABLED' if state[node] else 'disabled'}"
            + ("" if persisted else " (state not persisted)"),
            "enabled": state[node],
            "integrations": state,
        }

    raise HTTPException(status_code=404, detail=f"Unknown cosmos node: {node}")


@router.post("/cosmos/trigger")
async def trigger_cosmos(
    req: TriggerRequest,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Run the automation attached to a mesh node and log it to the feed."""
    try:
        result = await _run_trigger(req.node, req.params, identity, container)
    except HTTPException:
        raise
    except Exception as exc:
        result = {"ok": False, "kind": "error", "summary": f"{req.node} failed: {exc}"}

    feed = getattr(container, "activity_feed", None)
    if feed is not None:
        try:
            feed.record(
                "cosmos",
                # NB: payload must not contain its own "kind" key — the feed's
                # {"kind": kind, **payload} merge would let it shadow the kind.
                {
                    "node": req.node,
                    "op": result.get("kind"),
                    "ok": result.get("ok"),
                    "summary": result.get("summary", "")[:200],
                    "ts": time.time(),
                    "tenant_id": identity.tenant_id,
                },
            )
        except Exception:
            pass
    return result


class IntegrationToggle(BaseModel):
    enabled: bool


@router.post("/cosmos/integrations/{name}")
async def set_integration(
    name: str,
    req: IntegrationToggle,
    identity: Identity = Depends(require_identity),
) -> dict[str, Any]:
    if name not in _integration_ids():
        raise HTTPException(status_code=404, detail=f"Unknown integration: {name}")
    state = _load_integrations_state()
    state[name] = req.enabled
    persisted = _save_integrations_state(state)
    return {"ok": True, "name": name, "enabled": req.enabled, "persisted": persisted, "integrations": state}
