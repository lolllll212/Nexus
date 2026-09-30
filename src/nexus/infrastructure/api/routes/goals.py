"""Goals API - autonomous objective lifecycle + audit readback."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexus.domain.entities.goal import GoalPriority, GoalStatus
from nexus.domain.exceptions import GoalNotFoundError, GoalStatusError
from nexus.domain.value_objects.identity import Identity
from nexus.infrastructure.api.dependencies import get_container, require_admin, require_identity
from nexus.infrastructure.di.container import Container

router = APIRouter(
    prefix="/v1/goals",
    tags=["goals"],
    dependencies=[Depends(require_identity)],
)

autonomy_router = APIRouter(
    prefix="/api/autonomy",
    tags=["autonomy"],
    dependencies=[Depends(require_identity)],
)


class GrantApprovalRequest(BaseModel):
    action: str
    tenant_id: str | None = None


class CreateGoalRequest(BaseModel):
    statement: str = Field(..., min_length=3)
    priority: GoalPriority = GoalPriority.NORMAL
    budget_units: int | None = None
    requires_approval: bool = True


class GoalOut(BaseModel):
    id: str
    statement: str
    status: str
    priority: str
    budget_units: int
    budget_spent: int
    budget_remaining: int
    owner_id: str
    requires_approval: bool
    approved_by: str | None
    created_at: str
    updated_at: str
    plan: list
    history: list
    result: str | None


class ApproveGoalRequest(BaseModel):
    action: str = "goal"


class AuditEntry(BaseModel):
    kind: str
    detail: str
    actor: str
    ts: str


def _to_out(goal) -> GoalOut:
    return GoalOut(
        id=goal.id,
        statement=goal.statement,
        status=goal.status.value,
        priority=goal.priority.value,
        budget_units=goal.budget_units,
        budget_spent=goal.budget_spent,
        budget_remaining=goal.budget_remaining,
        owner_id=goal.owner_id,
        requires_approval=goal.requires_approval,
        approved_by=goal.approved_by,
        created_at=goal.created_at.isoformat(),
        updated_at=goal.updated_at.isoformat(),
        plan=[
            {
                "description": s.description,
                "status": s.status.value,
                "tool": s.tool,
                "output": s.output,
                "error": s.error,
            }
            for s in goal.plan
        ],
        history=[
            {"kind": e.kind, "detail": e.detail, "actor": e.actor, "ts": e.ts.isoformat()}
            for e in goal.history
        ],
        result=goal.result,
    )


@router.post("", response_model=GoalOut, status_code=201)
async def create_goal(
    req: CreateGoalRequest,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> GoalOut:
    budget = req.budget_units or container.config.autonomy_default_budget
    goal = await container.create_goal.execute(
        statement=req.statement,
        tenant_id=identity.tenant_id,
        owner_id=identity.user_id,
        budget_units=budget,
        priority=req.priority,
        requires_approval=req.requires_approval,
    )
    return _to_out(goal)


@router.get("", response_model=list[GoalOut])
async def list_goals(
    status: GoalStatus | None = None,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> list[GoalOut]:
    goals = await container.list_goals.execute(tenant_id=identity.tenant_id, status=status)
    return [_to_out(g) for g in goals]


@router.get("/audit", response_model=list[AuditEntry])
async def audit_log(
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> list[AuditEntry]:
    from nexus.domain.entities.goal import GoalEvent

    events: list[GoalEvent] = []
    for goal in await container.list_goals.list_all(identity.tenant_id):
        events.extend(goal.history)
    events.extend(await container.autonomy_policy.audit_log(identity.tenant_id))
    events.sort(key=lambda e: e.ts)
    return [AuditEntry(kind=e.kind, detail=e.detail, actor=e.actor, ts=e.ts.isoformat()) for e in events]


@router.get("/{goal_id}", response_model=GoalOut)
async def get_goal(
    goal_id: str,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> GoalOut:
    try:
        goal = await container.get_goal.execute(goal_id=goal_id, tenant_id=identity.tenant_id)
    except GoalNotFoundError:
        raise HTTPException(status_code=404, detail=f"Goal not found: {goal_id}")
    return _to_out(goal)


@router.post("/{goal_id}/approve", response_model=GoalOut)
async def approve_goal(
    goal_id: str,
    req: ApproveGoalRequest,
    identity: Identity = Depends(require_admin),
    container: Container = Depends(get_container),
) -> GoalOut:
    try:
        goal = await container.approve_goal.execute(
            goal_id=goal_id, tenant_id=identity.tenant_id, approver=identity.user_id
        )
    except GoalNotFoundError:
        raise HTTPException(status_code=404, detail=f"Goal not found: {goal_id}")
    except GoalStatusError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await container.autonomy_policy.grant_approval(req.action, identity.user_id, identity.tenant_id)
    return _to_out(goal)


@router.post("/approvals/grant")
@autonomy_router.post("/approvals/grant")
async def grant_action_approval(
    req: GrantApprovalRequest,
    identity: Identity = Depends(require_admin),
    container: Container = Depends(get_container),
) -> dict:
    """Grant approval for a sensitive autonomous action (Admin only)."""
    target_tenant = req.tenant_id or identity.tenant_id
    policy = container.autonomy_policy
    if policy:
        await policy.grant_approval(req.action, approver=identity.user_id, tenant_id=target_tenant)
    return {"status": "approved", "action": req.action, "approver": identity.user_id}


@router.post("/{goal_id}/cancel", response_model=GoalOut)
async def cancel_goal(
    goal_id: str,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> GoalOut:
    try:
        goal = await container.cancel_goal.execute(
            goal_id=goal_id, tenant_id=identity.tenant_id, actor=identity.user_id
        )
    except GoalNotFoundError:
        raise HTTPException(status_code=404, detail=f"Goal not found: {goal_id}")
    except GoalStatusError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _to_out(goal)


@router.post("/{goal_id}/run", response_model=GoalOut)
async def run_goal(
    goal_id: str,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> GoalOut:
    try:
        goal = await container.get_goal.execute(goal_id=goal_id, tenant_id=identity.tenant_id)
    except GoalNotFoundError:
        raise HTTPException(status_code=404, detail=f"Goal not found: {goal_id}")
    if goal.status == GoalStatus.PROPOSED:
        raise HTTPException(status_code=409, detail="Goal must be approved before it can run")
    goal = await container.autonomy_loop.run_goal(goal, identity.tenant_id)
    return _to_out(goal)
