# Multi-Agent Swarm

## Overview

Sometimes one mind is not enough. A **swarm** is a leader agent plus a set of
worker agents. The leader has no special powers in the code - it is just another
agent - but by convention it is given the synthesis role.

```
        ┌───────────────────────────────┐
        │      SwarmCoordinatorUseCase   │
        │        (application layer)      │
        └───────────────┬───────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
  PHASE 1: fan out              PHASE 2: synthesize
  bounded to max_workers        leader sees every
  sequential per worker         worker report
        │                               │
  ┌─────┼─────┬─────┐                 │
  ▼     ▼     ▼     ▼                 ▼
worker worker worker worker        leader
  └─────┴─────┴─────┘                 │
        │                               │
  SwarmResult(final_response,
              worker_responses, session_id)
```

## Port

```python
class AgentRepository(Protocol): ...   # tenant-scoped agent persistence
class SwarmRepository(Protocol): ...   # tenant-scoped swarm persistence

class AgentRunner(Protocol):
    async def run_agent(self, agent: Agent, task: str, tenant_id: str) -> str: ...
```

`SwarmCoordinatorUseCase` depends on the `AgentRunner` **protocol**, not on
`ProcessMessageUseCase`. That is the only seam that matters: the concrete
runner is chosen in `infrastructure/di/container.py`, and tests substitute a
scripted fake. The application layer never learns that an "agent" is a ReAct
loop.

## The Two Phases

`application/swarm/swarm.py::SwarmCoordinatorUseCase.run()`:

1. **Fan out.** Workers are taken in declared order and truncated to
   `max_workers` (default 5). A worker that is missing or `is_active == False`
   contributes the literal string `"(worker unavailable)"` rather than aborting
   the run - a partially-degraded swarm still produces an answer. An inactive
   or missing **leader** is fatal: the swarm is marked `FAILED` and
   `AgentNotFoundError` is raised, because phase 2 has no meaning without it.
2. **Synthesize.** The leader is re-run with the task plus a `Worker reports:`
   block of `agent_id: output` lines. Its reply becomes
   `SwarmResult.final_response`. `session_id` is `f"swarm:{swarm.id}"`.

Worker calls are **sequential**, not gathered. That is deliberate: the workers
are LLM calls with real token cost and a shared rate limiter, so an unbounded
fan-out is how you get a 429 storm. `max_workers` is the bound.

## Tool Scoping

`Agent.tools` is an allowlist of tool **names**. When it is non-empty,
`SwarmAgentExecutor` wraps the real registry in `_FilteredToolRegistry`, a
`ToolRegistry` view that:

- returns `None` from `get()` for a non-allowlisted tool,
- filters `search()` (over-fetching `limit * 4` before filtering, so a small
  allowlist does not starve results),
- filters `list_all()`,
- passes `register()` / `update()` straight through.

An empty `tools` list means **all tools** - there is no way to express "no
tools" except by registering a swarm agent with `tools: []` and relying on the
prompt to stop it. That is a known sharp edge, not a design decision.

Critically, the wrapper is passed *per call* to
`ProcessMessageUseCase.execute(tools=...)`. It used to be installed by mutating
the container's shared `self._tools` and restoring it afterwards, which meant
two concurrent agents silently ran with each other's tool access. See "Critical
Bugs Fixed" in `AGENTS.md`.

## Multi-tenancy

Every repository call is tenant-scoped: `save(agent, tenant_id=...)`,
`get(agent_id, tenant_id=...)`, `list_all(tenant_id=...)`. `CreateSwarmUseCase`
verifies that the leader **and every worker id** resolves within the same tenant
before writing the swarm, so a swarm cannot be assembled across tenants by
guessing UUIDs.

## Entities

`Agent` (`domain/entities/agent.py`): `name`, `tenant_id`, `owner_id`,
`system_prompt`, `role` (`"leader" | "worker"`, informational only), `tools`,
`status: AgentStatus`, `metadata`, and `is_active`.

`Swarm` (`domain/entities/swarm.py`): `name`, `tenant_id`, `owner_id`,
`leader_id`, `worker_ids`, `status: SwarmStatus` (`ready` / `running` /
`done` / `failed`), `metadata`.

`SwarmResult`: `final_response`, `worker_responses: dict[str, str]`,
`session_id`.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/swarm/agents` | register an agent |
| `GET` | `/v1/swarm/agents` | list (optional `role` filter) |
| `GET` | `/v1/swarm/agents/{id}` | agent detail |
| `POST` | `/v1/swarm/swarms` | create a swarm |
| `GET` | `/v1/swarm/swarms` | list |
| `POST` | `/v1/swarm/swarms/{id}/run` | run it |
| `GET` | `/v1/swarm/swarms/runs` | run history |
| `GET` | `/v1/swarm/swarms/{id}/run-history` | per-swarm run history |

Run history is persisted separately from the swarm entity, so
`Swarm.metadata` does not grow without bound across runs.

## Example

```bash
curl -X POST http://localhost:8000/v1/swarm/agents -H "Content-Type: application/json" \
  -d '{"name":"security-reviewer","tenant_id":"t1","owner_id":"u1",
       "system_prompt":"You audit dependencies for known CVEs.",
       "role":"worker","tools":["grep","read_file"]}'

curl -X POST http://localhost:8000/v1/swarm/swarms -H "Content-Type: application/json" \
  -d '{"name":"audit","tenant_id":"t1","owner_id":"u1",
       "leader_id":"<leader>","worker_ids":["<security-reviewer>"]}'

curl -X POST http://localhost:8000/v1/swarm/swarms/<swarm_id>/run \
  -H "Content-Type: application/json" -d '{"task":"Audit our requirements for CVEs."}'
```

## See also

- [Architecture Map](architecture-map.md) - the `AgentRepository` / `SwarmRepository` bindings
- [Dual-Loop Architecture](dual-loop.md) - each agent run is a full cortex ReAct loop
- [Agent Onboarding](agent-onboarding.md)
