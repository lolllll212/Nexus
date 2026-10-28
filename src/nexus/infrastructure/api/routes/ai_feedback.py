"""Modern AI platform API: capabilities, response feedback, and quality.

The chat use case returns a stable ``response_id`` plus guardrail and
context-provenance metadata.  Clients can attach a thumbs/star rating to that
response here; operators can then read aggregate quality without exposing one
user's feedback comments to another user.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from nexus.domain.value_objects.ai_feedback import FeedbackCategory
from nexus.domain.value_objects.ai_guardrails import GuardrailPolicy
from nexus.domain.value_objects.coding_excellence import coding_capability_catalog
from nexus.domain.value_objects.identity import Identity
from nexus.infrastructure.api.dependencies import get_container, require_admin, require_identity
from nexus.infrastructure.di.container import Container

router = APIRouter(
    prefix="/api/ai",
    tags=["ai-platform"],
    dependencies=[Depends(require_identity)],
)


class FeedbackRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=200)
    response_id: str = Field(..., min_length=1, max_length=200)
    rating: Literal[-1, 1]
    stars: int | None = Field(default=None, ge=1, le=5)
    categories: list[FeedbackCategory] = Field(default_factory=list, max_length=7)
    comment: str = Field(default="", max_length=2000)
    model: str | None = Field(default=None, max_length=200)


def _get_store(container: Container):
    store = getattr(container, "ai_feedback_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="AI feedback storage is not configured.")
    return store


def _get_policy(container: Container) -> GuardrailPolicy:
    policy = getattr(container, "ai_guardrail_policy", None)
    if policy is None:
        policy = getattr(getattr(container, "process_message", None), "_guardrails", None)
    return policy if isinstance(policy, GuardrailPolicy) else GuardrailPolicy()


def _get_execution_config(container: Container) -> dict[str, Any]:
    config = getattr(container, "ai_execution_config", None)
    if isinstance(config, dict):
        return dict(config)
    process_message = getattr(container, "process_message", None)
    return {
        "quality_gate_enabled": bool(
            getattr(process_message, "_quality_gate_enabled", True)
        ),
        "native_tool_calling_enabled": bool(
            getattr(process_message, "_native_tool_calling_enabled", True)
        ),
        "quality_max_repairs": int(getattr(process_message, "_quality_max_repairs", 3)),
        "default_effort": "auto",
    }


@router.get("/capabilities")
async def ai_capabilities(
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Describe the runtime AI platform features enabled for this deployment."""
    policy = _get_policy(container)
    execution_config = _get_execution_config(container)
    process_message = getattr(container, "process_message", None)
    token_budget = int(getattr(process_message, "MEMORY_CONTEXT_TOKEN_BUDGET", 1200))
    max_context_items = int(getattr(process_message, "MEMORY_RECALL_LIMIT", 8))
    adaptive_routing = bool(
        getattr(container, "nim_provider", None) is not None
        and getattr(container, "llm", None) is getattr(container, "nim_provider", None)
    )
    return {
        "platform_version": "2026.1",
        "features": {
            "guardrails": {
                "enabled": policy.enabled,
                "stages": ["input", "output", "tool_observation"],
                "actions": ["allow", "redact", "flag", "block"],
                "redact_secrets": policy.redact_secrets,
                "redact_pii": policy.redact_pii,
                "block_secret_exfiltration": policy.block_secret_exfiltration,
                "block_tool_bypass": policy.block_tool_bypass,
                "safe_findings_only": True,
            },
            "hybrid_context": {
                "enabled": True,
                "fusion": "weighted_reciprocal_rank_fusion",
                "diversity": "maximal_marginal_relevance",
                "deduplication": ["memory_id", "normalized_text"],
                "token_budget": token_budget,
                "max_items": max_context_items,
                "sources": [
                    {"name": "semantic", "weight": 1.0},
                    {"name": "graph", "weight": 0.85},
                ],
                "citations": True,
                "provenance": True,
            },
            "execution_quality": {
                "enabled": bool(execution_config.get("quality_gate_enabled", True)),
                "efforts": ["auto", "fast", "balanced", "deep", "max"],
                "default_effort": execution_config.get("default_effort", "auto"),
                "adaptive_sampling": True,
                "adaptive_model_routing": adaptive_routing,
                "native_tool_calling": bool(
                    execution_config.get("native_tool_calling_enabled", True)
                ),
                "native_tool_calling_fallback": "text_react",
                "quality_gate": {
                    "bounded_repairs": True,
                    "max_repairs": int(execution_config.get("quality_max_repairs", 3)),
                    "checks": [
                        "workstream_coverage",
                        "tool_and_source_evidence",
                        "unsupported_completion_claims",
                        "tool_failure_contradictions",
                        "explicit_format_and_constraints",
                        "referenced_paths",
                        "calculation_result",
                        "verification_evidence",
                        "memory_citations",
                        "sensitive_domain_caveats",
                    ],
                },
                "response_metadata": ["execution", "quality", "coding"],
            },
            "coding_excellence": {
                "enabled": True,
                **coding_capability_catalog(),
                "project_checks": [
                    "frontend_quality",
                    "npm_typecheck",
                    "npm_build",
                    "c_syntax",
                    "cpp_syntax",
                    "cmake_build",
                    "cargo_check",
                    "cargo_clippy",
                    "cargo_test",
                    "python_pytest",
                    "php_lint",
                    "composer_test",
                    "xml_validate",
                    "ruby_syntax",
                    "ruby_test",
                ],
                "repository_templates": [
                    "frontend-design-system",
                    "html5-clean-ui",
                    "c-cmake",
                    "cpp-cmake",
                    "rust-cli",
                    "php-web",
                    "ruby-cli",
                    "xml-toolkit",
                ],
            },
            "feedback": {
                "enabled": getattr(container, "ai_feedback_store", None) is not None,
                "ratings": [-1, 1],
                "stars": {"min": 1, "max": 5},
                "categories": [category.value for category in FeedbackCategory],
                "idempotent_by_user_session_response": True,
                "tenant_scoped": True,
            },
            "observability": {
                "response_ids": True,
                "guardrail_metrics": [
                    "ai_guardrail_decisions_total",
                    "ai_guardrail_findings_total",
                ],
                "quality_metrics": [
                    "ai_quality_reports_total",
                    "ai_response_quality_score",
                    "ai_quality_repairs_total",
                    "ai_quality_issues_total",
                ],
                "feedback_metric": "ai_feedback_total",
            },
        },
    }


@router.post("/feedback", status_code=201)
async def submit_feedback(
    req: FeedbackRequest,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Create or update the caller's feedback for one chat response."""
    store = _get_store(container)
    policy = _get_policy(container)
    # Feedback is persisted, so it receives the same secret/PII scrub as a
    # model response.  This prevents a user from accidentally storing a token
    # in a quality comment.
    safe_comment = policy.evaluate_output(req.comment).text
    record = store.record(
        tenant_id=identity.tenant_id,
        user_id=identity.user_id,
        session_id=req.session_id,
        response_id=req.response_id,
        rating=req.rating,
        stars=req.stars,
        categories=tuple(category.value for category in req.categories),
        comment=safe_comment,
        model=req.model,
    )

    metrics = getattr(container, "metrics", None)
    if metrics is not None:
        metrics.counter(
            "ai_feedback_total",
            labels={
                "rating": "positive" if record.rating > 0 else "negative",
                "model": record.model or "unknown",
            },
        )
    return {"feedback": record.to_dict()}


@router.get("/feedback")
async def list_feedback(
    session_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """List only the authenticated caller's feedback records."""
    store = _get_store(container)
    records = store.list_feedback(
        tenant_id=identity.tenant_id,
        user_id=identity.user_id,
        session_id=session_id,
        limit=limit,
    )
    return {"feedback": [record.to_dict() for record in records], "count": len(records)}


@router.get("/feedback/summary")
async def my_feedback_summary(
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Return the caller's own response-quality summary."""
    store = _get_store(container)
    return {
        "scope": "user",
        "summary": store.summary(tenant_id=identity.tenant_id, user_id=identity.user_id),
    }


@router.get("/quality")
async def tenant_quality_summary(
    identity: Identity = Depends(require_admin),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Return aggregate tenant quality for operators (no comments or user IDs)."""
    store = _get_store(container)
    return {
        "scope": "tenant",
        "summary": store.summary(tenant_id=identity.tenant_id),
    }
