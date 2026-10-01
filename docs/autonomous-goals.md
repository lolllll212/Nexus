# Autonomous Goals - Self-Directed Work with Guardrails

## The Idea

A goal is a piece of work the user states once and the system drives to
completion on its own, within an explicit budget. This is the difference
between "answer this question" and "go fix the failing deploy tests."

```
POST /v1/goals  {statement, budget_units, requires_approval}
        │
        ▼
   PROPOSED ──approve──► ACTIVE ──AutonomyLoopUseCase──► COMPLETED
        │                    │                              ▲
        │                    └──authorize_step denied──► BLOCKED
        │                                     │
        └──────────────── cancel ◄────────────┘
              CANCELLED
```

## Entities

`domain/entities/goal.py`:

| Enum | Values |
|---|---|
| `GoalStatus` | `proposed`, `active`, `blocked`, `completed`, `failed`, `cancelled` |
| `GoalPriority` | `low`, `normal`, `high`, `critical` |
| `StepStatus` | `pending`, `in_progress`, `done`, `failed`, `skipped` |

`Goal` carries `statement`, `tenant_id`, `owner_id`, `budget_units`,
`budget_spent`, `requires_approval`, `approved_by`, `priority`, a `plan:
list[GoalStep]`, and `events: list[GoalEvent]`. State transitions live on the
entity as methods - `mark_active`, `mark_blocked`, `mark_completed`,
`mark_failed`, `cancel` - and each one appends a `GoalEvent`. Nothing writes
`goal.status` directly.

`GoalStep(description, status, output)` is one bounded unit of work.
`GoalEvent(kind, detail, actor)` is the audit record.

## Lifecycle

`application/autonomy/goals.py`:

| Use case | Behaviour |
|---|---|
| `CreateGoalUseCase` | `requires_approval=True` -> `PROPOSED`; `False` -> `ACTIVE` immediately. Rejects `budget_units < 1` with `ValueError`. |
| `ApproveGoalUseCase` | `PROPOSED` -> `ACTIVE`, records `approved_by`. Any other status raises `GoalStatusError`. |
| `CancelGoalUseCase` | Cancels an unfinished goal; `Goal.cancel` raises `ValueError` if the goal is already terminal, surfaced as `GoalStatusError`. |
| `ListGoalsUseCase` | `execute()` -> active goals (or filtered by status); `list_all()` -> everything. |
| `GetGoalUseCase` | Full goal including plan and event history. |
| `AutonomyLoopUseCase` | Drives one goal, or `run_all_active()` for up to 10. |

## The Loop

`AutonomyLoopUseCase.run_goal()` is a `while` loop with two exit conditions:
the goal must be `ACTIVE` and `has_budget`.

```
while goal.has_budget and goal.status == ACTIVE:
    decision = policy.authorize_step(goal, tenant_id)     # <- the guardrail
    if decision.denied:
        goal.mark_blocked(decision.reason); break
    step = GoalStep("autonomous work iteration {budget_spent + 1}")
    goal.plan.append(step)
    outcome = executor.run_step(goal, step, tenant_id)    # CortexStepExecutor
    policy.spend(goal, tenant_id)
    if outcome.completed:
        step.output = outcome.summary; goal.mark_completed(outcome.summary)
    else:
        step.output = outcome.summary                     # keep going, budget permitting
```

Two things to notice. `authorize_step` is called **before** every step, not once
at the start, so a goal can be stopped mid-flight by budget exhaustion. And
`spend()` is called after the step regardless of outcome - a failed step still
cost budget. A step that returns `completed=False` does not advance the goal
toward `COMPLETED`, but it does not burn the loop either; the goal retries
until the budget runs out, at which point `authorize_step` returns denied and
the goal lands in `BLOCKED` with a reason.

`StepExecutor` is a `Protocol`, so `CortexStepExecutor` (which routes the step
through the cortex) is a container decision, not an application-layer one.

## The AutonomyPolicy Port

`domain/ports/autonomy.py` is the single guardrail contract. It is deliberately
shared between explicit goals *and* implicit self-modification, so tool
regeneration, deployment, and code changes are all bounded by the same budget
and the same audit trail.

| Method | Used by |
|---|---|
| `authorize_action(tenant_id, units)` | self-modification (e.g. self-heal) |
| `authorize_step(goal, tenant_id)` | the autonomy loop - checks step budget **and** the shared hourly budget |
| `spend(goal, tenant_id, units)` | decrement the goal's step budget |
| `require_approval(action, actor, tenant_id)` | "is this action pre-approved?" |
| `grant_approval(action, approver, tenant_id)` | human grants one |
| `audit(event, tenant_id)` | append to the tenant's log |
| `pending_approvals(tenant_id, limit)` | UI for the approvals queue |
| `audit_log(tenant_id, limit)` | UI for the audit trail |

`AutonomyDecision` returns `allowed`, `reason`, `remaining_budget`, and a
`denied` convenience property.

`DefaultAutonomyPolicy`
(`infrastructure/adapters/autonomy/policy.py`) implements the hourly budget by
borrowing the `RateLimiter` port under the key
`f"autonomy_hourly:{tenant_id}"` with a `HOURLY_WINDOW_SECONDS = 3600` window.
The approval store and audit log are plain in-process dicts. That is the one
part of the autonomy system that does **not** survive a restart - if you need
durable approvals, that is the adapter to replace.

`AllowAllAutonomyPolicy` is a test/opt-out subclass that approves everything
and still audits. It is what `FakeContainer` wires.

## Configuration

| Var | Default | Effect |
|---|---|---|
| `NEXUS_GOALS_MAX_ACTIVE` | `10` | Per-tenant ceiling on concurrently active goals. `0` = unlimited. |
| `NEXUS_AUTONOMY_HOURLY_BUDGET` | `0` | Shared per-tenant autonomous actions per hour. `0` = unlimited. |
| `NEXUS_AUTONOMY_DEFAULT_BUDGET` | `20` | Default `budget_units` for a new goal. |
| `NEXUS_AUTONOMY_ALLOWLIST` | `tool_selfheal` | Comma-separated actions pre-approved per tenant. |

`NEXUS_GOALS_MAX_ACTIVE` is enforced in `CreateGoalUseCase` **only for
unapproved goals**. An approved goal is already an explicit human decision, so
it is not subject to the ceiling - otherwise approving your tenth goal would
fail and you would be stuck with a `PROPOSED` goal you cannot start. Hitting the
ceiling raises `QuotaExceededError`.

## Multi-tenancy

Every `GoalRepository` call is tenant-scoped, and `list_active`,
`list_by_status`, and `list_all` are all filtered by `tenant_id`. The autonomy
budget key is namespaced by tenant. The audit log is keyed by tenant. There is
no cross-tenant goal execution.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/goals` | create (201) |
| `GET` | `/v1/goals` | list active, or filter by `status` |
| `GET` | `/v1/goals/{id}` | detail with plan + history |
| `POST` | `/v1/goals/{id}/approve` | `PROPOSED` -> `ACTIVE` |
| `POST` | `/v1/goals/{id}/cancel` | cancel |
| `POST` | `/v1/goals/{id}/run` | drive it now |
| `GET` | `/v1/goals/audit` | tenant audit log |
| `POST` | `/v1/goals/approvals/grant` | grant an action approval |

`/v1/goals/audit` must be matched before `/v1/goals/{goal_id}` or `audit` is
parsed as a goal id.

## Example

```bash
curl -X POST http://localhost:8000/v1/goals -H "Content-Type: application/json" \
  -d '{"statement":"Get tests/unit/test_swarm.py green",
       "tenant_id":"t1","owner_id":"u1","budget_units":5,
       "priority":"high","requires_approval":true}'

curl -X POST http://localhost:8000/v1/goals/<goal_id>/approve \
  -H "Content-Type: application/json" -d '{"approver":"u1"}'

curl -X POST http://localhost:8000/v1/goals/<goal_id>/run -d '{}' -H "Content-Type: application/json"
```

## See also

- [Self-Evolution](self-evolution.md) - self-healing shares this policy
- [Architecture Map](architecture-map.md) - the `AutonomyPolicy` binding
- [Multi-Agent Swarm](swarm.md) - a different kind of delegated work
