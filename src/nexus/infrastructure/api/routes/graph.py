"""
Graph API - 3D force-directed knowledge graph for the HOLO frontend.

Uses the established hexagonal ports (ConceptRepository / MemoryRepository)
via the DI container. No Neo4j driver logic lives in this route.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from nexus.infrastructure.api.dependencies import get_container
from nexus.infrastructure.di.container import Container

router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph")
async def get_graph(
    limit: int = Query(80, ge=1, le=200, description="Max concepts to seed graph"),
    min_weight: float = Query(0.0, ge=0.0, le=1.0),
    tenant_id: str = Query("default", description="Tenant scope"),
    container: Container = Depends(get_container),
) -> dict:
    """
    Return a force-graph payload:

      {
        "nodes": [{"id": "...", "group": "...", "val": 1}, ...],
        "links": [{"source": "...", "target": "..."}, ...]
      }

    Nodes combine Neo4j Concepts (group = concept_type) and their linked
    Memories (group = memory). Links are synaptic CONNECTS edges plus
    concept->memory MENTIONS edges. Uses domain ports only (hexagonal).
    """
    repo = container.concept_repo
    memory_repo = container.memory_repo

    nodes: List[dict] = []
    links: List[dict] = []
    seen: set[str] = set()

    def _add_node(nid: str, group: str, val: float = 1.0) -> None:
        if nid in seen:
            return
        seen.add(nid)
        nodes.append({"id": nid, "group": group, "val": float(val or 1.0)})

    try:
        # Seed concepts — strongest first, empty label matches all (repo semantics)
        concepts = await repo.find_by_label("", limit=limit, tenant_id=tenant_id)
    except Exception:
        concepts = []

    # Fallback demo graph if empty (ensures 3D view always renders)
    if not concepts:
        return {
            "nodes": [
                {"id": "Dinosaur", "group": "Dinosaur", "val": 8},
                {"id": "Space", "group": "Space", "val": 10},
                {"id": "Python", "group": "topic", "val": 5},
                {"id": "Neo4j", "group": "topic", "val": 4},
                {"id": "Memory: welcome", "group": "memory", "val": 2},
            ],
            "links": [
                {"source": "Dinosaur", "target": "Python"},
                {"source": "Space", "target": "Neo4j"},
                {"source": "Python", "target": "Neo4j"},
                {"source": "Neo4j", "target": "Memory: welcome"},
            ],
        }

    # Add concept nodes
    for c in concepts:
        grp = getattr(c, "concept_type", "topic") or "topic"
        # Use label as human id when available, fallback to id; keep id stable for links
        # For visualization we want id == label for Dinosaur/Space to match .glb condition
        # so we expose label as id if it matches special groups, else use id.
        nid = c.label if c.label in ("Dinosaur", "Space") else c.id
        val = float(getattr(c, "strength", 1.0) or 1.0)
        # normalize val for graph sizing (1..12)
        val = max(1.0, min(12.0, val * 4))
        _add_node(nid, grp if grp not in ("Dinosaur", "Space") else c.label, val)

    # Follow synaptic connections
    for c in concepts:
        source_id = c.label if c.label in ("Dinosaur", "Space") else c.id
        try:
            conns = await repo.get_connections(c.id, min_weight=min_weight, tenant_id=tenant_id)
        except Exception:
            continue
        for conn in conns:
            target_id = conn.target_id
            # Try to resolve target concept to get its label/group for node creation
            target_concept = None
            try:
                target_concept = await repo.get(target_id, tenant_id=tenant_id)
            except Exception:
                target_concept = None
            if target_concept is not None:
                t_group = getattr(target_concept, "concept_type", "topic") or "topic"
                t_nid = target_concept.label if target_concept.label in ("Dinosaur", "Space") else target_concept.id
                t_val = max(1.0, min(12.0, float(getattr(target_concept, "strength", 1.0) or 1.0) * 4))
                _add_node(t_nid, t_group if t_group not in ("Dinosaur", "Space") else target_concept.label, t_val)
                target_id = t_nid
            else:
                # unknown target, still add as generic node if not seen
                _add_node(target_id, "topic", 3)

            links.append({"source": source_id, "target": target_id})

    # Add memory nodes linked to concepts (via ConceptRepository.get_memories)
    # This enriches the graph without bypassing hexagonal ports
    for c in concepts[:20]:  # cap to avoid explosion
        source_id = c.label if c.label in ("Dinosaur", "Space") else c.id
        try:
            mems = await repo.get_memories(c.id, tenant_id=tenant_id)
        except Exception:
            mems = []
        for m in mems[:3]:
            mid = f"Memory:{m.id[:8]}" if len(m.id) > 8 else f"Memory:{m.id}"
            _add_node(mid, "memory", 2)
            links.append({"source": source_id, "target": mid})

    # Deduplicate links
    seen_links: set[tuple[str, str]] = set()
    uniq_links: List[dict] = []
    for l in links:
        key = (l["source"], l["target"])
        if key not in seen_links and l["source"] in seen and l["target"] in seen:
            seen_links.add(key)
            uniq_links.append(l)

    return {"nodes": nodes, "links": uniq_links}
