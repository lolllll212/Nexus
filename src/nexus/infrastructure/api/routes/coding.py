"""
Coding API - production-grade coding training endpoints.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexus.infrastructure.api.dependencies import get_container, require_identity, require_rate_limit
from nexus.infrastructure.di.container import Container
from nexus.domain.value_objects.identity import Identity

router = APIRouter(
    prefix="/v1/coding",
    tags=["coding"],
    dependencies=[Depends(require_identity), Depends(require_rate_limit("chat"))],
)


class CodingRequest(BaseModel):
    message: str = Field("", min_length=0)
    session_id: Optional[str] = None
    language: Optional[str] = None
    category: Optional[str] = None
    few_shot: int = Field(3, ge=0, le=10)


class CodingResponse(BaseModel):
    response: str
    session_id: str
    tools_used: list
    memories_recalled: int
    examples_used: int


class AddExampleRequest(BaseModel):
    task: str
    solution: str
    language: str = "python"
    category: str = "general"
    tags: List[str] = []
    explanation: str = ""
    test_cases: str = ""
    difficulty: str = "medium"


class FeedbackRequest(BaseModel):
    succeeded: bool
    rating: float = Field(0.0, ge=0.0, le=5.0)
    improved_solution: Optional[str] = None


class ImportGitRequest(BaseModel):
    repo_path: str
    patterns: List[str] = ["*.py"]


class StatsResponse(BaseModel):
    total: int
    categories: dict
    languages: dict
    total_uses: int
    overall_success_rate: float
    qdrant_connected: bool


def _get_store():
    from nexus.application.training.coding_store import CodingStore
    from nexus.infrastructure.di.container import Config
    config = Config()
    return CodingStore(
        store_path="data/coding_examples.json",
        qdrant_host=config.qdrant_host,
        qdrant_port=config.qdrant_port,
        embedding_dim=config.embedding_dimension,
    )


# ── Coding chat ──────────────────────────────────────────────────────────

@router.post("", response_model=CodingResponse)
async def coding_chat(
    req: CodingRequest,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> CodingResponse:
    if not req.message:
        raise HTTPException(status_code=422, detail="Provide a coding task")
    from nexus.application.training.coding_prompt import CodingRAG
    store = _get_store()
    rag = CodingRAG(store, max_examples=req.few_shot)
    system_prompt = rag.build_coding_prompt(req.message, category=req.category)
    examples = store.search(req.message, category=req.category, limit=req.few_shot)
    result = await container.process_message.execute(
        user_id=identity.user_id, message=req.message, session_id=req.session_id,
        tenant_id=identity.tenant_id, system_prompt=system_prompt,
    )
    return CodingResponse(
        response=result.response, session_id=result.session_id,
        tools_used=result.tools_used, memories_recalled=result.memories_recalled,
        examples_used=len(examples),
    )


# ── Stats ────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=StatsResponse)
async def training_stats(identity: Identity = Depends(require_identity)) -> StatsResponse:
    return StatsResponse(**_get_store().stats())


# ── CRUD ─────────────────────────────────────────────────────────────────

@router.get("/examples")
async def list_examples(
    identity: Identity = Depends(require_identity), limit: int = 50, category: Optional[str] = None,
) -> list:
    store = _get_store()
    examples = store.list_all()
    if category:
        examples = [e for e in examples if e.category == category]
    return [e.to_dict() for e in examples[:limit]]


@router.get("/examples/{example_id}")
async def get_example(example_id: str, identity: Identity = Depends(require_identity)) -> dict:
    ex = _get_store().get(example_id)
    if not ex:
        raise HTTPException(status_code=404, detail="Example not found")
    return ex.to_dict()


@router.post("/examples")
async def add_example(req: AddExampleRequest, identity: Identity = Depends(require_identity)) -> dict:
    from nexus.application.training.coding_store import CodingExample
    store = _get_store()
    ex = CodingExample(
        task=req.task, solution=req.solution, language=req.language,
        category=req.category, tags=req.tags, explanation=req.explanation,
        test_cases=req.test_cases, difficulty=req.difficulty, source="manual",
    )
    store.add(ex)
    return {"id": ex.id, "message": "Example added"}


@router.put("/examples/{example_id}")
async def update_example(
    example_id: str, req: AddExampleRequest, identity: Identity = Depends(require_identity),
) -> dict:
    from nexus.application.training.coding_store import CodingExample
    store = _get_store()
    existing = store.get(example_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Example not found")
    updated = CodingExample(
        id=example_id, task=req.task, solution=req.solution, language=req.language,
        category=req.category, tags=req.tags, explanation=req.explanation,
        test_cases=req.test_cases, difficulty=req.difficulty,
        version=existing.version + 1, source=existing.source,
        use_count=existing.use_count, success_count=existing.success_count,
        fail_count=existing.fail_count, avg_rating=existing.avg_rating,
    )
    store.update(updated)
    return {"id": example_id, "message": "Updated", "version": updated.version}


@router.delete("/examples/{example_id}")
async def delete_example(example_id: str, identity: Identity = Depends(require_identity)) -> dict:
    if not _get_store().delete(example_id):
        raise HTTPException(status_code=404, detail="Example not found")
    return {"message": "Deleted"}


@router.get("/examples/search")
async def search_examples(
    q: str = "", category: Optional[str] = None, limit: int = 5,
    identity: Identity = Depends(require_identity),
) -> list:
    return [e.to_dict() for e in _get_store().search(q, category=category, limit=limit)]


# ── Quality ──────────────────────────────────────────────────────────────

@router.post("/examples/{example_id}/feedback")
async def submit_feedback(
    example_id: str, req: FeedbackRequest, identity: Identity = Depends(require_identity),
) -> dict:
    store = _get_store()
    ex = store.get(example_id)
    if not ex:
        raise HTTPException(status_code=404, detail="Example not found")
    ex.record_use(req.succeeded, req.rating)
    if req.improved_solution:
        ex.solution = req.improved_solution
        ex.version += 1
    store.update(ex)
    return {"message": "Recorded", "success_rate": ex.success_rate, "avg_rating": ex.avg_rating}


@router.get("/quality/top")
async def top_rated(limit: int = 10, identity: Identity = Depends(require_identity)) -> list:
    return [e.to_dict() for e in _get_store().get_top_rated(limit)]


@router.get("/quality/low")
async def low_quality(threshold: float = 0.5, identity: Identity = Depends(require_identity)) -> list:
    return [e.to_dict() for e in _get_store().get_low_quality(threshold)]


@router.get("/quality/underused")
async def underused(min_uses: int = 2, identity: Identity = Depends(require_identity)) -> list:
    return [e.to_dict() for e in _get_store().get_underused(min_uses)]


# ── Auto-learning ────────────────────────────────────────────────────────

@router.post("/learn")
async def auto_learn(
    task: str, solution: str, language: str = "python",
    succeeded: bool = True, rating: float = 0.0,
    identity: Identity = Depends(require_identity),
) -> dict:
    from nexus.application.training.auto_learner import AutoLearner
    learner = AutoLearner(_get_store())
    example = learner.learn(task=task, solution=solution, language=language, succeeded=succeeded, rating=rating)
    if example:
        return {"id": example.id, "message": "Learned from session"}
    return {"message": "Not suitable for learning"}


# ── Import/Export ─────────────────────────────────────────────────────────

@router.post("/import/git")
async def import_git_repo(req: ImportGitRequest, identity: Identity = Depends(require_identity)) -> dict:
    count = _get_store().import_from_git(req.repo_path, req.patterns)
    return {"imported": count}


@router.get("/export")
async def export_data(version: str = "latest", identity: Identity = Depends(require_identity)) -> dict:
    path = _get_store().export_version(version)
    return {"file": str(path), "version": version}


@router.post("/deprecate/{example_id}")
async def deprecate_example(example_id: str, identity: Identity = Depends(require_identity)) -> dict:
    if not _get_store().deprecate(example_id):
        raise HTTPException(status_code=404, detail="Example not found")
    return {"message": "Deprecated"}
