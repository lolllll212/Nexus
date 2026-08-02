"""Swarm application layer - agent management and the leader/worker coordinator."""

from __future__ import annotations

from typing import Dict, List, Optional, Protocol

from nexus.domain.entities.agent import Agent
from nexus.domain.entities.swarm import Swarm, SwarmResult, SwarmStatus
from nexus.domain.exceptions import AgentNotFoundError, SwarmNotFoundError
from nexus.domain.ports.swarm import AgentRepository, SwarmRepository


class AgentRunner(Protocol):
    """Executes a single agent on a task."""

    async def run_agent(self, agent: Agent, task: str, tenant_id: str) -> str: ...


class RegisterAgentUseCase:
    """Persist a new swarm agent (tenant-scoped)."""

    def __init__(self, repo: AgentRepository) -> None:
        self._repo = repo

    async def execute(
        self,
        name: str,
        tenant_id: str,
        owner_id: str,
        system_prompt: str,
        role: str = "worker",
        tools: Optional[List[str]] = None,
    ) -> Agent:
        agent = Agent(
            name=name,
            tenant_id=tenant_id,
            owner_id=owner_id,
            system_prompt=system_prompt,
            role=role,
            tools=list(tools or []),
        )
        await self._repo.save(agent, tenant_id=tenant_id)
        return agent


class ListAgentsUseCase:
    """Tenant-scoped agent listing, optionally filtered by role."""

    def __init__(self, repo: AgentRepository) -> None:
        self._repo = repo

    async def execute(self, tenant_id: str, role: Optional[str] = None, limit: int = 100) -> List[Agent]:
        if role is not None:
            return await self._repo.list_by_role(role, tenant_id=tenant_id, limit=limit)
        return await self._repo.list_all(tenant_id=tenant_id, limit=limit)


class GetAgentUseCase:
    """Tenant-scoped agent detail."""

    def __init__(self, repo: AgentRepository) -> None:
        self._repo = repo

    async def execute(self, agent_id: str, tenant_id: str) -> Agent:
        agent = await self._repo.get(agent_id, tenant_id=tenant_id)
        if agent is None:
            raise AgentNotFoundError(agent_id)
        return agent


class CreateSwarmUseCase:
    """Create a swarm: a leader + worker agents, all in one tenant."""

    def __init__(self, swarm_repo: SwarmRepository, agent_repo: AgentRepository) -> None:
        self._swarm_repo = swarm_repo
        self._agent_repo = agent_repo

    async def execute(
        self,
        name: str,
        tenant_id: str,
        owner_id: str,
        leader_id: str,
        worker_ids: List[str],
    ) -> Swarm:
        if await self._agent_repo.get(leader_id, tenant_id=tenant_id) is None:
            raise AgentNotFoundError(leader_id)
        for wid in worker_ids:
            if await self._agent_repo.get(wid, tenant_id=tenant_id) is None:
                raise AgentNotFoundError(wid)
        swarm = Swarm(
            name=name,
            tenant_id=tenant_id,
            owner_id=owner_id,
            leader_id=leader_id,
            worker_ids=list(worker_ids),
        )
        await self._swarm_repo.save(swarm, tenant_id=tenant_id)
        return swarm


class ListSwarmsUseCase:
    """Tenant-scoped swarm listing."""

    def __init__(self, swarm_repo: SwarmRepository) -> None:
        self._swarm_repo = swarm_repo

    async def execute(self, tenant_id: str, limit: int = 100) -> List[Swarm]:
        return await self._swarm_repo.list_all(tenant_id=tenant_id, limit=limit)


class GetSwarmUseCase:
    """Tenant-scoped swarm detail."""

    def __init__(self, swarm_repo: SwarmRepository) -> None:
        self._swarm_repo = swarm_repo

    async def execute(self, swarm_id: str, tenant_id: str) -> Swarm:
        swarm = await self._swarm_repo.get(swarm_id, tenant_id=tenant_id)
        if swarm is None:
            raise SwarmNotFoundError(swarm_id)
        return swarm


class SwarmCoordinatorUseCase:
    """Fan out a task to workers, then synthesize a final answer via the leader."""

    def __init__(
        self,
        swarm_repo: SwarmRepository,
        agent_repo: AgentRepository,
        runner: AgentRunner,
        max_workers: int = 5,
    ) -> None:
        self._swarm_repo = swarm_repo
        self._agent_repo = agent_repo
        self._runner = runner
        self._max_workers = max_workers

    async def run(self, swarm: Swarm, task: str, tenant_id: str) -> SwarmResult:
        swarm.status = SwarmStatus.RUNNING
        await self._swarm_repo.save(swarm, tenant_id=tenant_id)

        leader = await self._agent_repo.get(swarm.leader_id, tenant_id=tenant_id)
        if leader is None or not leader.is_active:
            swarm.status = SwarmStatus.FAILED
            await self._swarm_repo.save(swarm, tenant_id=tenant_id)
            raise AgentNotFoundError(swarm.leader_id)

        # Phase 1: fan out to active workers (bounded).
        worker_responses: Dict[str, str] = {}
        worker_ids = swarm.worker_ids[: self._max_workers]
        for worker_id in worker_ids:
            worker = await self._agent_repo.get(worker_id, tenant_id=tenant_id)
            if worker is None or not worker.is_active:
                worker_responses[worker_id] = "(worker unavailable)"
                continue
            worker_responses[worker.id] = await self._runner.run_agent(worker, task, tenant_id)

        # Phase 2: leader synthesizes the final answer from worker outputs.
        brief = task
        if worker_responses:
            summary = "\n".join(f"{name}: {out}" for name, out in worker_responses.items())
            brief = f"{task}\n\nWorker reports:\n{summary}"

        final = await self._runner.run_agent(leader, brief, tenant_id)
        session_id = f"swarm:{swarm.id}"

        swarm.status = SwarmStatus.DONE
        await self._swarm_repo.save(swarm, tenant_id=tenant_id)
        return SwarmResult(final_response=final, worker_responses=worker_responses, session_id=session_id)
