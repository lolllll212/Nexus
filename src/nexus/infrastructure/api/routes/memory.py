"""Memory introspection routes - peek inside the brain.

Tenant-scoped: every query runs against the caller's tenant via Identity.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from nexus.infrastructure.api.dependencies import get_container, require_identity
from nexus.infrastructure.di.container import Container
from nexus.domain.value_objects.identity import Identity

router = APIRouter(prefix="/v1/memory", tags=["memory"], dependencies=[Depends(require_identity)])


class ConceptOut(BaseModel):
    id: str
    label: str
    concept_type: str
    strength: float
    access_count: int


class MemoryOut(BaseModel):
    id: str
    content: str
    memory_type: str
    access_count: int


@router.get("/concepts", response_model=List[ConceptOut])
async def list_concepts(
    query: str = "",
    limit: int = 20,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> List[ConceptOut]:
    concepts = await container.concept_repo.find_by_label(query, limit, tenant_id=identity.tenant_id)
    return [
        ConceptOut(
            id=c.id,
            label=c.label,
            concept_type=c.concept_type,
            strength=c.strength,
            access_count=c.access_count,
        )
        for c in concepts
    ]


@router.get("/concepts/{concept_id}", response_model=ConceptOut)
async def get_concept(
    concept_id: str,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
):
    concept = await container.concept_repo.get(concept_id, tenant_id=identity.tenant_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    return ConceptOut(
        id=concept.id,
        label=concept.label,
        concept_type=concept.concept_type,
        strength=concept.strength,
        access_count=concept.access_count,
    )


@router.get("/search", response_model=List[MemoryOut])
async def search_memory(
    query: str,
    limit: int = 10,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
):
    memories = await container.memory_repo.retrieve(query, limit=limit, tenant_id=identity.tenant_id)
    return [
        MemoryOut(id=m.id, content=m.content, memory_type=m.memory_type.value, access_count=m.access_count)
        for m in memories
    ]


class GraphNodeOut(BaseModel):
    id: str
    label: str
    concept_type: str
    strength: float


class GraphEdgeOut(BaseModel):
    source: str
    target: str
    weight: float
    connection_type: str


class GraphOut(BaseModel):
    nodes: List[GraphNodeOut]
    edges: List[GraphEdgeOut]


@router.get("/graph", response_model=GraphOut)
async def concept_graph(
    limit: int = 80,
    min_weight: float = 0.0,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
):
    """The synaptic graph as nodes + edges for visualization.

    Seeds from the strongest concepts (empty label matches all) then follows
    their synapses, so the dashboard gets a living view of the knowledge graph.
    """
    repo = container.concept_repo
    seed = await repo.find_by_label("", limit=limit, tenant_id=identity.tenant_id)
    nodes: List[GraphNodeOut] = []
    edges: List[GraphEdgeOut] = []
    seen: set = set()
    node_by_id = {}

    async def add_node(concept) -> None:
        if concept.id in seen:
            return
        seen.add(concept.id)
        node = GraphNodeOut(
            id=concept.id,
            label=concept.label,
            concept_type=concept.concept_type,
            strength=concept.strength,
        )
        node_by_id[concept.id] = node
        nodes.append(node)

    for concept in seed:
        await add_node(concept)

    # Follow connections to surface the graph shape beyond the seed set.
    targets: set = set()
    for concept in seed:
        try:
            conns = await repo.get_connections(
                concept.id, min_weight=min_weight, tenant_id=identity.tenant_id
            )
        except Exception:
            continue
        for conn in conns:
            targets.add(conn.target_id)
            edges.append(
                GraphEdgeOut(
                    source=conn.source_id,
                    target=conn.target_id,
                    weight=conn.weight,
                    connection_type=conn.connection_type.value,
                )
            )

    for target_id in targets:
        if target_id not in seen:
            try:
                concept = await repo.get(target_id, tenant_id=identity.tenant_id)
            except Exception:
                concept = None
            if concept is not None:
                await add_node(concept)

    edges.sort(key=lambda e: e.weight, reverse=True)
    return GraphOut(nodes=nodes, edges=edges)
