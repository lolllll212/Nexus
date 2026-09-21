"""Swarm API - agent management and swarm orchestration."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexus.domain.exceptions import AgentNotFoundError, SwarmNotFoundError
from nexus.domain.value_objects.identity import Identity
from nexus.infrastructure.api.dependencies import get_container, require_identity, require_rate_limit
from nexus.infrastructure.di.container import Container

router = APIRouter(
    prefix="/v1",
    tags=["swarm"],
    dependencies=[Depends(require_identity), Depends(require_rate_limit("chat"))],
)


class AgentIn(BaseModel):
    name: str = Field(..., min_length=1)
    role: str = "worker"
    system_prompt: str = Field(..., min_length=1)
    tools: Optional[List[str]] = None


class AgentOut(BaseModel):
    id: str
    name: str
    role: str
    system_prompt: str
    tools: list
    status: str


class SwarmIn(BaseModel):
    name: str = Field(..., min_length=1)
    leader_id: str
    worker_ids: List[str] = Field(default_factory=list)


class SwarmOut(BaseModel):
    id: str
    name: str
    leader_id: str
    worker_ids: list
    status: str


class SwarmRunRequest(BaseModel):
    task: str = Field(..., min_length=1)


class SwarmRunOut(BaseModel):
    final_response: str
    worker_responses: dict
    session_id: str


def _agent_out(a) -> AgentOut:
    return AgentOut(
        id=a.id,
        name=a.name,
        role=a.role,
        system_prompt=a.system_prompt,
        tools=list(a.tools),
        status=a.status.value,
    )


def _swarm_out(s) -> SwarmOut:
    return SwarmOut(
        id=s.id, name=s.name, leader_id=s.leader_id, worker_ids=list(s.worker_ids), status=s.status.value
    )


@router.post("/agents", response_model=AgentOut, status_code=201)
async def register_agent(
    req: AgentIn,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> AgentOut:
    agent = await container.register_agent.execute(
        name=req.name,
        tenant_id=identity.tenant_id,
        owner_id=identity.user_id,
        system_prompt=req.system_prompt,
        role=req.role,
        tools=req.tools,
    )
    return _agent_out(agent)


@router.get("/agents", response_model=List[AgentOut])
async def list_agents(
    role: Optional[str] = None,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> List[AgentOut]:
    agents = await container.list_agents.execute(tenant_id=identity.tenant_id, role=role)
    return [_agent_out(a) for a in agents]


@router.get("/agents/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: str,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> AgentOut:
    try:
        agent = await container.get_agent.execute(agent_id=agent_id, tenant_id=identity.tenant_id)
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return _agent_out(agent)


@router.post("/swarms", response_model=SwarmOut, status_code=201)
async def create_swarm(
    req: SwarmIn,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> SwarmOut:
    try:
        swarm = await container.create_swarm.execute(
            name=req.name,
            tenant_id=identity.tenant_id,
            owner_id=identity.user_id,
            leader_id=req.leader_id,
            worker_ids=req.worker_ids,
        )
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _swarm_out(swarm)


@router.get("/swarms", response_model=List[SwarmOut])
async def list_swarms(
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> List[SwarmOut]:
    swarms = await container.list_swarms.execute(tenant_id=identity.tenant_id)
    return [_swarm_out(s) for s in swarms]


@router.post("/swarms/{swarm_id}/run", response_model=SwarmRunOut)
async def run_swarm(
    swarm_id: str,
    req: SwarmRunRequest,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> SwarmRunOut:
    try:
        swarm = await container.get_swarm.execute(swarm_id=swarm_id, tenant_id=identity.tenant_id)
    except SwarmNotFoundError:
        raise HTTPException(status_code=404, detail=f"Swarm not found: {swarm_id}")
    result = await container.swarm_coordinator.run(swarm, req.task, identity.tenant_id)
    return SwarmRunOut(
        final_response=result.final_response,
        worker_responses=result.worker_responses,
        session_id=result.session_id,
    )
