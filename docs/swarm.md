# Swarm — P4 Design

## The Capability

A **swarm** is a team of specialized agents that cooperates on a task. A
**leader** agent decomposes the objective, fans it out to **worker** agents,
collects their answers, and synthesizes a final response.

P4 reuses the P1 tenancy/auth machinery: every agent belongs to exactly one
tenant, all agent operations are identity-gated, and swarm runs go through the
existing chat rate limiter. Each agent has its own system prompt and tool
access, so a swarm is effectively a set of "personalities" over the same
brain.

## Domain Model

### `Agent` — `src/nexus/domain/entities/agent.py`

```python
class AgentStatus(Enum):
    ACTIVE, PAUSED, RETIRED

@dataclass
class Agent:
    id: str
    tenant_id: str
    owner_id: str                 # who registered it
    name: str
    role: str                     # "leader" | "worker" (informational)
    system_prompt: str            # personality / constraints injected as system message
    tools: List[str]              # allowlisted tool names (empty = all built-ins)
    status: AgentStatus = AgentStatus.ACTIVE
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, object]
```

### `Swarm` — `src/nexus/domain/entities/swarm.py`

```python
@dataclass
class Swarm:
    id: str
    tenant_id: str
    owner_id: str
    name: str
    leader_id: str                # agent that decomposes + synthesizes
    worker_ids: List[str]         # agents that execute subtasks
    created_at: datetime
    status: str = "ready"         # ready | running | done | failed
```

### `SwarmResult`

```python
@dataclass
class SwarmResult:
    final_response: str
    worker_responses: Dict[str, str]   # agent_id -> output
    session_id: str
```

## Ports

### `AgentRepository` — `src/nexus/domain/ports/agent_repository.py`

```python
class AgentRepository(ABC):
    async def save(self, agent: Agent, tenant_id: str = "default") -> None
    async def get(self, agent_id: str, tenant_id: str = "default") -> Optional[Agent]
    async def list_by_role(self, role: str, tenant_id: str = "default", limit: int = 100) -> List[Agent]
    async def delete(self, agent_id: str, tenant_id: str = "default") -> None
```

### `SwarmRepository` — same shape, persisted as `swarm:{tenant_id}:{id}`.

No new external infra: both persist as JSON documents in the existing
short-term store, exactly like P2 goals.

## Application Layer — `src/nexus/application/swarm/`

### `AgentUseCases`
- `RegisterAgentUseCase` — validate name/prompt/tools, persist, tenant-scoped.
- `ListAgentsUseCase` / `GetAgentUseCase` — tenant-scoped reads.

### `SwarmCoordinatorUseCase` — the orchestrator

```
SwarmCoordinatorUseCase.run(swarm, task, tenant_id):
    workers = [await agent_repo.get(wid, tenant) for wid in swarm.worker_ids if ACTIVE]
    # phase 1: fan out
    for worker in workers:
        response = await executor.run_agent(worker, task, tenant_id)   # worker system_prompt + tools
        worker_responses[worker.id] = response
    # phase 2: synthesize
    leader = await agent_repo.get(swarm.leader_id, tenant)
    brief = task + "\n".join(f"{name}: {resp}" for worker_responses)
    final = await executor.run_agent(leader, brief, tenant_id, include_worker_context=True)
    return SwarmResult(final, worker_responses)
```

### `AgentExecutor` (infra) — `infrastructure/adapters/swarm/executor.py`

Wraps `ProcessMessageUseCase` with an optional `system_prompt` override and a
tool allowlist filter:

```python
class SwarmAgentExecutor:
    async def run_agent(self, agent, task, tenant_id) -> str:
        return await self._process_message.execute(
            user_id=agent.owner_id,
            message=task,
            session_id=f"agent:{agent.id}",
            tenant_id=tenant_id,
            system_prompt=agent.system_prompt,   # new optional param (below)
        )
```

### `ProcessMessageUseCase` change (small)

Add `system_prompt: Optional[str] = None` to `execute()`; `_build_context`
inserts it as the top system message (above tone/memories). Default `None`
keeps existing behavior byte-for-byte.

## API Surface — `src/nexus/infrastructure/api/routes/swarm.py`

All behind `require_identity`, tenant-scoped, chat-rate-limited.

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/agents` | register agent `{name, role, system_prompt, tools}` |
| GET | `/v1/agents` | list tenant agents |
| GET | `/v1/agents/{id}` | detail |
| POST | `/v1/swarms` | create `{name, leader_id, worker_ids}` |
| GET | `/v1/swarms` | list |
| POST | `/v1/swarms/{id}/run` | body `{task}` → aggregated `SwarmResult` |

## Security (reuse from P1)

- Every agent/swarm query and mutation passes `tenant_id`; `get()` returns
  `None` for cross-tenant ids (404).
- Swarm runs use `require_rate_limit("chat")` like `/v1/chat`.
- Worker agents can only use their allowlisted `tools`; a worker's executor
  restricts the tool registry to `agent.tools` before each run.
- `NEXUS_SWARM_MAX_WORKERS` (default 5) caps fan-out per swarm.

## Guardrail Summary

| Risk | Mitigation |
|---|---|
| Cross-tenant agent access | tenant-scoped repo + identity (P1) |
| Unbounded fan-out | `NEXUS_SWARM_MAX_WORKERS` |
| Agent runs tools it shouldn't | per-agent tool allowlist enforced at execution |
| Noisy/looping workers | chat rate limit on runs; per-agent session keys |
| Prompt injection from worker output | leader gets worker output as data, leader's own prompt defines trust |

## Rollout Order

1. `Agent`/`Swarm` entities + `AgentRepository`/`SwarmRepository` + fakes.
2. `ProcessMessageUseCase.system_prompt` optional param.
3. Agent use cases + `SwarmCoordinatorUseCase` + `SwarmAgentExecutor`.
4. API routes + config (`NEXUS_SWARM_MAX_WORKERS`) + env/compose updates.
5. Tests: entity, repo tenancy, coordinator fan-out/synthesis, system-prompt
   injection, API isolation. Fakes only — no external infra.
