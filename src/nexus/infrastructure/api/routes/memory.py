"""Memory introspection routes - peek inside the brain."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

from nexus.infrastructure.di.container import Container

router = APIRouter(prefix="/v1/memory", tags=["memory"])


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
    container: Container = Depends(lambda: Container()),
) -> List[ConceptOut]:
    concepts = await container.concept_repo.find_by_label(query, limit)
    return [
        ConceptOut(id=c.id, label=c.label, concept_type=c.concept_type, strength=c.strength, access_count=c.access_count)
        for c in concepts
    ]


@router.get("/concepts/{concept_id}", response_model=ConceptOut)
async def get_concept(concept_id: str, container: Container = Depends(lambda: Container())):
    concept = await container.concept_repo.get(concept_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    return ConceptOut(
        id=concept.id, label=concept.label, concept_type=concept.concept_type,
        strength=concept.strength, access_count=concept.access_count,
    )


@router.get("/search", response_model=List[MemoryOut])
async def search_memory(query: str, limit: int = 10, container: Container = Depends(lambda: Container())):
    memories = await container.memory_repo.retrieve(query, limit=limit)
    return [MemoryOut(id=m.id, content=m.content, memory_type=m.memory_type.value, access_count=m.access_count) for m in memories]
