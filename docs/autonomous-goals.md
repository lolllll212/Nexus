# Autonomous Goals — P2 Design

> **Status: implemented.** All items in Rollout Order are complete; 118 tests
> green (including P1's 96). See the design below for the architecture, and
> `tests/unit/test_autonomy_goals.py` for coverage.

## The Capability

Today NEXUS only reacts: it answers messages and runs a scheduled dream cycle.
P2 lets the brain **pursue objectives on its own** — set a goal, plan a route,
execute bounded steps, adapt when a step fails, and report back — while a
budget, an approval gate, and an audit log keep that autonomy safe.

Two kinds of autonomy are covered by the same guardrail model:

1. **User-assigned goals** (explicit): a user creates a `Goal`, the autonomy
   loop drives it to completion.
2. **Self-initiated improvements** (implicit): the existing `SelfHealUseCase`
   regeneration of failing tools, plus any future self-modification, goes
   through the same budget/approval/audit gates.

## Domain Model

### `Goal` entity — `src/nexus/domain/entities/goal.py`

```python
class GoalStatus(Enum):
    PROPOSED = "proposed"    # awaiting approval (if approval required)
    ACTIVE   = "active"      # loop is working it
    BLOCKED  = "blocked"     # needs human input / budget exhausted
    COMPLETED= "completed"
    FAILED   = "failed"
    CANCELLED= "cancelled"

class GoalPriority(Enum):
    LOW, NORMAL, HIGH, CRITICAL

@dataclass
class Goal:
    id: str
    tenant_id: str
    owner_id: str                       # who created it
    statement: str                      # natural-language objective
    status: GoalStatus = GoalStatus.PROPOSED
    priority: GoalPriority = GoalPriority.NORMAL
    budget_units: int                   # max autonomous steps
    budget_spent: int = 0
    max_cost_per_step: float            # estimated LLM/exec cost ceiling
    created_at: datetime
    updated_at: datetime
    deadline: Optional[datetime]
    requires_approval: bool = True
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    plan: List[GoalStep] = field(default_factory=list)
    result: Optional[str] = None        # final summary on completion
    # lifecycle ledger (append-only)
    history: List[GoalEvent] = field(default_factory=list)
```

### `GoalStep`

```python
@dataclass
class GoalStep:
    description: str
    status: str = "pending"             # pending|in_progress|done|failed|skipped
    tool: Optional[str] = None          # tool name used to execute
    output: Optional[str] = None
    error: Optional[str] = None
```

### `GoalEvent` (audit)

```python
@dataclass
class GoalEvent:
    ts: datetime
    kind: str        # step_started|step_completed|step_failed|budget_decremented|approved|rejected|cancelled|regenerated_tool
    actor: str       # "user:u1" | "system"
    detail: str
```

### `Tool` becomes audit-trailed

Add `tool.id` to `GoalEvent.detail` whenever `SelfHealUseCase` regenerates a
tool so the audit log covers existing autonomy too.

## Ports

### `GoalRepository` — `src/nexus/domain/ports/goal_repository.py`

```python
class GoalRepository(Protocol):
    async def save(self, goal: Goal, tenant_id: str = "default") -> None
    async def get(self, goal_id: str, tenant_id: str = "default") -> Optional[Goal]
    async def list_by_status(self, status: GoalStatus, tenant_id: str = "default", limit: int = 50) -> List[Goal]
    async def find_stale_active(self, max_active: int, tenant_id: str = "default") -> List[Goal]
    async def delete(self, goal_id: str, tenant_id: str = "default") -> None
```

Implementation note: persist as JSON documents in the same store as
short-term/episodic memory, keyed `goal:{tenant_id}:{goal_id}` with an index
`goal:{tenant_id}:active`. Neo4j/Qdrant stay for their current roles.

### `AutonomyPolicy` — `src/nexus/domain/ports/autonomy.py`

Central guardrail contract shared by the goal loop **and** `SelfHealUseCase`.

```python
@dataclass
class AutonomyDecision:
    allowed: bool
    reason: str
    remaining_budget: int

class AutonomyPolicy(Protocol):
    async def authorize_step(self, goal: Goal, tenant_id: str) -> AutonomyDecision
    async def spend(self, goal: Goal, tenant_id: str, units: int = 1) -> AutonomyDecision
    async def require_approval(self, action: str, actor: str, tenant_id: str) -> bool
    async def audit(self, event: GoalEvent, tenant_id: str) -> None
```

Rules enforced in `authorize_step` / `spend`:

- `goal.budget_spent + units <= goal.budget_units` — hard step budget.
- Cumulative per-tenant hourly autonomy budget (`NEXUS_AUTONOMY_HOURLY_BUDGET`,
  default 0 = unlimited) tracked in the rate-limit store.
- No step while `goal.status == BLOCKED` or `FAILED`.
- Steps that **self-modify** (regenerate a tool, change own code, deploy)
  always require approval unless the action is in the tenant allowlist
  (`NEXUS_AUTONOMY_ALLOWLIST`, e.g. `tool_selfheal`).

### `ApprovalStore` (may fold into `AutonomyPolicy`)

Pending approvals persisted as `approval:{tenant_id}:{goal_id}`; surfaced via a
`/v1/goals/approvals` endpoint. `require_approval` resolves against the same
store.

## Application Layer

### `GoalUseCases` — `src/nexus/application/autonomy/goals.py`

- `CreateGoalUseCase` — validate statement, compute budget, persist as
  `PROPOSED` (approval) or `ACTIVE` (if owner is admin or approval waived).
- `ApproveGoalUseCase` — flips to `ACTIVE`, records `approved_by/approved_at`.
- `CancelGoalUseCase` — owner/admin only; ledger entry.
- `ListGoalsUseCase` / `GetGoalUseCase` — tenant-scoped reads.
- `AutonomyLoopUseCase` — the driver:

```
AutonomyLoopUseCase.run()
  for goal in repo.list_by_status(ACTIVE):
      while goal.budget_spent < goal.budget_units:
          decision = policy.authorize_step(goal)
          if not decision.allowed: mark BLOCKED; break
          step = current pending step
          execute via ReAct loop (existing cortex pipeline, tenant-scoped)
          policy.spend(goal); policy.audit(...)
          update step status, goal.updated_at
          if done: goal.status = COMPLETED; record result
```

Executes as a Celery task (`tasks.autonomy_loop`) on the beat schedule and can
be triggered on-demand via the API. All memory/tool work is tenant-scoped the
same way P1 threaded `tenant_id`.

### Gating existing `SelfHealUseCase`

`self_heal.py` currently regenerates freely at 03:30. Change:

- Accept `policy: AutonomyPolicy` + `tenant_id`.
- Before regenerating a failing tool, call
  `policy.authorize_step(...)` and `policy.require_approval("tool_selfheal", "system", tenant)`.
  Unapproved actions leave the tool `DEPRECATED` but do **not** regenerate.
- Every regeneration appends a `GoalEvent(kind="regenerated_tool", actor="system")`.

This keeps the SelfHeal path working by default (add `tool_selfheal` to the
allowlist) while making it auditable and budgeted.

## API Surface — `src/nexus/infrastructure/api/routes/goals.py`

All behind `require_identity` + tenant scoping; rate-limited like chat.

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/v1/goals` | `{statement, priority, budget_units, requires_approval}` | creates goal |
| GET | `/v1/goals` | — | list tenant goals |
| GET | `/v1/goals/{goal_id}` | — | detail incl. plan + history |
| POST | `/v1/goals/{goal_id}/approve` | — | admin/user approval |
| POST | `/v1/goals/{goal_id}/cancel` | — | owner/admin |
| POST | `/v1/goals/{goal_id}/run` | — | trigger loop now (admin) |
| GET | `/v1/goals/audit` | — | audit log for tenant |

## Config

- `NEXUS_AUTONOMY_HOURLY_BUDGET` (default `0` = unlimited)
- `NEXUS_AUTONOMY_DEFAULT_BUDGET` (default `20` steps)
- `NEXUS_AUTONOMY_ALLOWLIST` (comma-separated actions exempt from approval)
- `NEXUS_GOALS_MAX_ACTIVE` (default `10` — `find_stale_active` ceiling)

## Guardrail Summary

| Risk | Mitigation |
|---|---|
| Unbounded autonomous work | step budget, hourly per-tenant budget, `MAX_ACTIVE` |
| Self-modification without consent | approval gate for non-allowlisted actions |
| Unreviewable behavior | append-only `GoalEvent` audit log per tenant |
| Cross-tenant leakage | every repo/step call passes `tenant_id` (P1) |
| Infinite loop on failing goal | step failure marks `BLOCKED`, loop breaks on budget |

## Rollout Order

1. `Goal` entity + `GoalRepository` + `AutonomyPolicy` + fakes.
2. `SelfHealUseCase` gating + audit (fastest, secures existing autonomy).
3. Goal use cases + autonomy loop task.
4. API routes + config + `.env.example`/docker-compose updates.
5. Tests: entity, policy budget/approval, loop lifecycle, self-heal gating,
   API tenant isolation. No external infra needed (fakes only).
