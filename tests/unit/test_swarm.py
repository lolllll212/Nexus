"""
Swarm tests (Phase 4) - multi-agent orchestration.

Covers:
  - Agent / Swarm entities and repository tenancy
  - Agent + swarm use cases (register, list, get, create)
  - Coordinator: fan-out to workers, leader synthesis, max_workers cap,
    missing-worker placeholders, missing-leader failure
  - Per-agent system_prompt injection reaches the LLM
  - Per-agent tool allowlist enforced by SwarmAgentExecutor
  - API: /v1/agents + /v1/swarms CRUD and /v1/swarms/{id}/run with auth + tenancy
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fastapi.testclient import TestClient

from nexus.application.swarm.swarm import (
    CreateSwarmUseCase,
    GetAgentUseCase,
    RegisterAgentUseCase,
    SwarmCoordinatorUseCase,
)
from nexus.domain.entities.agent import Agent, AgentStatus
from nexus.domain.entities.swarm import Swarm, SwarmStatus
from nexus.domain.entities.tool import Tool
from nexus.domain.exceptions import AgentNotFoundError
from nexus.domain.value_objects.schema import JSONSchema
from nexus.infrastructure.adapters.swarm.executor import SwarmAgentExecutor
from nexus.infrastructure.adapters.swarm.repositories import (
    InMemoryAgentRepository,
    InMemorySwarmRepository,
)
from nexus.infrastructure.api.main import create_app

from tests.fakes.container import FakeContainer, TEST_API_KEY_1, TEST_API_KEY_2

AUTH = {"Authorization": f"Bearer {TEST_API_KEY_1}"}


class RecordingLLM:
    """Captures every complete() call; returns FINAL ANSWER so ReAct exits fast."""

    def __init__(self, response: str = "FINAL ANSWER: ok"):
        self.calls = []
        self._response = response

    async def complete(self, messages, temperature=0.7, max_tokens=4096, tools=None):
        self.calls.append(messages)
        return self._response

    async def extract_structured(self, content, schema, instructions=""):
        return {}


class ScriptedLLM:
    """Returns scripted responses in order, capturing calls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete(self, messages, temperature=0.7, max_tokens=4096, tools=None):
        self.calls.append(messages)
        return self.responses.pop(0) if self.responses else "FINAL ANSWER: done"

    async def extract_structured(self, content, schema, instructions=""):
        return {}


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


def _inject(client, app, llm=None):
    fake = FakeContainer()
    if llm is not None:
        fake.llm = llm
        fake.process_message._llm = llm
    app.state.container = fake
    client.app.state.container = fake
    return fake


def _system_messages(call):
    return [m["content"] for m in call if m.get("role") == "system"]


async def _register(fake, name="agent-a", tenant="t1", owner="u1", prompt="You are A.", role="worker", tools=None):
    return await RegisterAgentUseCase(fake.agent_repo).execute(
        name=name,
        tenant_id=tenant,
        owner_id=owner,
        system_prompt=prompt,
        role=role,
        tools=tools,
    )


# --------------------------------------------------------------------------- #
#  Entities + repositories
# --------------------------------------------------------------------------- #


def test_agent_entity_defaults():
    a = Agent(name="a", tenant_id="t1", owner_id="u1", system_prompt="p")
    assert a.role == "worker"
    assert a.tools == []
    assert a.status == AgentStatus.ACTIVE
    assert a.is_active


async def test_agent_repository_tenancy():
    repo = InMemoryAgentRepository()
    t1 = Agent(name="a1", tenant_id="t1", owner_id="u1", system_prompt="p", role="leader")
    t2 = Agent(name="a2", tenant_id="t2", owner_id="u2", system_prompt="p")
    t1b = Agent(name="a1b", tenant_id="t1", owner_id="u1", system_prompt="p")
    for a in (t1, t2, t1b):
        await repo.save(a, tenant_id=a.tenant_id)

    assert [a.id for a in await repo.list_all(tenant_id="t1")] == [t1.id, t1b.id]
    assert [a.id for a in await repo.list_all(tenant_id="t2")] == [t2.id]
    assert [a.id for a in await repo.list_by_role("leader", tenant_id="t1")] == [t1.id]
    assert await repo.get(t1.id, tenant_id="t2") is None
    assert (await repo.get(t1.id, tenant_id="t1")).id == t1.id

    await repo.delete(t1.id, tenant_id="t1")
    assert await repo.get(t1.id, tenant_id="t1") is None


async def test_swarm_repository_tenancy():
    repo = InMemorySwarmRepository()
    s1 = Swarm(name="s1", tenant_id="t1", owner_id="u1", leader_id="L")
    s2 = Swarm(name="s2", tenant_id="t2", owner_id="u2", leader_id="L")
    await repo.save(s1, tenant_id="t1")
    await repo.save(s2, tenant_id="t2")

    assert [s.id for s in await repo.list_all(tenant_id="t1")] == [s1.id]
    assert await repo.get(s1.id, tenant_id="t2") is None
    await repo.delete(s1.id, tenant_id="t1")
    assert await repo.get(s1.id, tenant_id="t1") is None


# --------------------------------------------------------------------------- #
#  Use cases
# --------------------------------------------------------------------------- #


async def test_register_and_list_agents_by_role():
    repo = InMemoryAgentRepository()
    uc = RegisterAgentUseCase(repo)
    leader = await uc.execute(name="lead", tenant_id="t1", owner_id="u1", system_prompt="Lead", role="leader")
    worker = await uc.execute(name="w", tenant_id="t1", owner_id="u1", system_prompt="W", tools=["calc"])
    await uc.execute(name="other", tenant_id="t2", owner_id="u2", system_prompt="O", role="leader")

    all_t1 = await repo.list_all(tenant_id="t1")
    assert {a.id for a in all_t1} == {leader.id, worker.id}
    assert [a.id for a in await repo.list_by_role("leader", tenant_id="t1")] == [leader.id]
    assert worker.tools == ["calc"]


async def test_get_agent_not_found():
    fake = FakeContainer()
    with pytest.raises(AgentNotFoundError):
        await GetAgentUseCase(fake.agent_repo).execute("nope", "t1")


async def test_create_swarm_requires_existing_agents():
    fake = FakeContainer()
    leader = await _register(fake, name="lead", role="leader", prompt="Lead")
    worker = await _register(fake, name="w", prompt="W")
    swarm = await CreateSwarmUseCase(fake.swarm_repo, fake.agent_repo).execute(
        name="team", tenant_id="t1", owner_id="u1", leader_id=leader.id, worker_ids=[worker.id]
    )
    assert swarm.leader_id == leader.id
    assert swarm.worker_ids == [worker.id]
    assert swarm.status == SwarmStatus.READY

    with pytest.raises(AgentNotFoundError):
        await CreateSwarmUseCase(fake.swarm_repo, fake.agent_repo).execute(
            name="bad", tenant_id="t1", owner_id="u1", leader_id="missing", worker_ids=[]
        )
    with pytest.raises(AgentNotFoundError):
        await CreateSwarmUseCase(fake.swarm_repo, fake.agent_repo).execute(
            name="bad2", tenant_id="t1", owner_id="u1", leader_id=leader.id, worker_ids=["missing"]
        )


# --------------------------------------------------------------------------- #
#  Coordinator
# --------------------------------------------------------------------------- #


async def _make_swarm(fake, n_workers=2, prompt_tpl="Worker {i}", leader_prompt="You are the leader."):
    leader = await _register(fake, name="lead", role="leader", prompt=leader_prompt)
    workers = [await _register(fake, name=f"w{i}", prompt=prompt_tpl.format(i=i)) for i in range(n_workers)]
    swarm = await CreateSwarmUseCase(fake.swarm_repo, fake.agent_repo).execute(
        name="team", tenant_id="t1", owner_id="u1", leader_id=leader.id, worker_ids=[w.id for w in workers]
    )
    return swarm, leader, workers


async def test_coordinator_fanout_and_synthesis():
    fake = FakeContainer()
    llm = RecordingLLM("FINAL ANSWER: synthesized")
    fake.llm = llm
    fake.process_message._llm = llm
    swarm, leader, workers = await _make_swarm(fake, n_workers=2)

    result = await fake.swarm_coordinator.run(swarm, "do a thing", "t1")

    assert result.session_id == f"swarm:{swarm.id}"
    assert set(result.worker_responses.keys()) == {w.id for w in workers}
    assert result.final_response == "synthesized"
    assert swarm.status == SwarmStatus.DONE
    # 2 workers + 1 leader = 3 LLM calls
    assert len(llm.calls) == 3


async def test_coordinator_injects_agent_system_prompts():
    fake = FakeContainer()
    llm = RecordingLLM("FINAL ANSWER: ok")
    fake.llm = llm
    fake.process_message._llm = llm
    swarm, leader, workers = await _make_swarm(fake, n_workers=2)

    await fake.swarm_coordinator.run(swarm, "task", "t1")

    leader_call = [c for c in llm.calls if leader.system_prompt in _system_messages(c)]
    worker_calls = [c for c in llm.calls if _system_messages(c) and "Worker" in _system_messages(c)[0]]
    assert len(leader_call) == 1
    assert len(worker_calls) == 2
    # Each agent's prompt is the top-most system message of its own run.
    prompts = [_system_messages(c)[0] for c in worker_calls]
    assert "Worker 0" in prompts and "Worker 1" in prompts


async def test_coordinator_leader_receives_worker_reports():
    fake = FakeContainer()
    llm = RecordingLLM("FINAL ANSWER: ok")
    fake.llm = llm
    fake.process_message._llm = llm
    swarm, leader, workers = await _make_swarm(fake, n_workers=2)

    await fake.swarm_coordinator.run(swarm, "the-task", "t1")

    leader_calls = [c for c in llm.calls if leader.system_prompt in _system_messages(c)]
    leader_user = " ".join(str(m["content"]) for m in leader_calls[0] if m.get("role") == "user")
    assert "the-task" in leader_user
    assert "Worker reports:" in leader_user


async def test_coordinator_respects_max_workers():
    fake = FakeContainer()
    llm = RecordingLLM("FINAL ANSWER: ok")
    fake.llm = llm
    fake.process_message._llm = llm
    swarm, leader, workers = await _make_swarm(fake, n_workers=5)

    coord = SwarmCoordinatorUseCase(fake.swarm_repo, fake.agent_repo, fake.swarm_agent_executor, max_workers=2)
    result = await coord.run(swarm, "task", "t1")

    assert len(result.worker_responses) == 2
    # 2 workers + 1 leader
    assert len(llm.calls) == 3


async def test_coordinator_marks_missing_worker_unavailable():
    fake = FakeContainer()
    llm = RecordingLLM("FINAL ANSWER: ok")
    fake.llm = llm
    fake.process_message._llm = llm
    swarm, leader, workers = await _make_swarm(fake, n_workers=2)

    ghost = "no-such-worker"
    swarm.worker_ids.append(ghost)

    result = await fake.swarm_coordinator.run(swarm, "task", "t1")
    assert result.worker_responses[ghost] == "(worker unavailable)"


async def test_coordinator_fails_when_leader_missing():
    fake = FakeContainer()
    llm = RecordingLLM("FINAL ANSWER: ok")
    fake.llm = llm
    fake.process_message._llm = llm
    swarm, leader, workers = await _make_swarm(fake)
    swarm.leader_id = "gone"

    with pytest.raises(AgentNotFoundError):
        await fake.swarm_coordinator.run(swarm, "task", "t1")
    assert swarm.status == SwarmStatus.FAILED


async def test_coordinator_skips_paused_workers():
    fake = FakeContainer()
    llm = RecordingLLM("FINAL ANSWER: ok")
    fake.llm = llm
    fake.process_message._llm = llm
    swarm, leader, workers = await _make_swarm(fake, n_workers=2)
    workers[0].status = AgentStatus.PAUSED

    result = await fake.swarm_coordinator.run(swarm, "task", "t1")
    assert result.worker_responses[workers[0].id] == "(worker unavailable)"
    assert workers[1].id in result.worker_responses


# --------------------------------------------------------------------------- #
#  Executor + tool allowlist
# --------------------------------------------------------------------------- #


def _tool(registry, name, tool_id=None):
    tool = Tool(
        name=name,
        description=name,
        input_schema=JSONSchema(type="object", properties={}),
        output_schema=JSONSchema(type="object", properties={}),
        id=tool_id or f"t-{name}",
    )
    registry.tools[tool.id] = tool
    return tool


async def test_executor_blocks_disallowed_tools():
    fake = FakeContainer()
    calc = _tool(fake.tool_registry, "calc")
    web = _tool(fake.tool_registry, "web")
    scripted = ScriptedLLM(
        [
            'TOOL_CALL: {"tool_id": "t-web", "params": {}}',
            'TOOL_CALL: {"tool_id": "t-calc", "params": {}}',
            "FINAL ANSWER: computed",
        ]
    )
    fake.llm = scripted
    fake.process_message._llm = scripted
    agent = Agent(name="w", tenant_id="t1", owner_id="u1", system_prompt="p", tools=["calc"])

    executor = SwarmAgentExecutor(fake.process_message, fake.tool_registry)
    out = await executor.run_agent(agent, "do math", "t1")

    assert out == "computed"
    # The disallowed tool was never executed; only calc ran.
    assert calc.id in fake.executor.executed
    assert web.id not in fake.executor.executed


async def test_executor_allows_all_when_no_allowlist():
    fake = FakeContainer()
    _tool(fake.tool_registry, "calc")
    web = _tool(fake.tool_registry, "web")
    scripted = ScriptedLLM(
        [
            'TOOL_CALL: {"tool_id": "t-web", "params": {}}',
            "FINAL ANSWER: fetched",
        ]
    )
    fake.llm = scripted
    fake.process_message._llm = scripted
    agent = Agent(name="w", tenant_id="t1", owner_id="u1", system_prompt="p", tools=[])

    executor = SwarmAgentExecutor(fake.process_message, fake.tool_registry)
    out = await executor.run_agent(agent, "fetch", "t1")

    assert out == "fetched"
    assert web.id in fake.executor.executed


# --------------------------------------------------------------------------- #
#  API
# --------------------------------------------------------------------------- #


def _register_via_api(client, **overrides):
    payload = {
        "name": "agent-a",
        "system_prompt": "You are agent A.",
        "role": "worker",
        "tools": ["calc"],
    }
    payload.update(overrides)
    resp = client.post("/v1/agents", json=payload, headers=AUTH)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_api_agents_crud():
    client = TestClient(create_app())
    app = client.app
    _inject(client, app, RecordingLLM())

    created = _register_via_api(client)
    assert created["role"] == "worker"
    assert created["tools"] == ["calc"]

    listing = client.get("/v1/agents", headers=AUTH)
    assert listing.status_code == 200
    assert [a["id"] for a in listing.json()] == [created["id"]]

    detail = client.get(f"/v1/agents/{created['id']}", headers=AUTH)
    assert detail.status_code == 200
    assert detail.json()["system_prompt"] == "You are agent A."

    missing = client.get("/v1/agents/does-not-exist", headers=AUTH)
    assert missing.status_code == 404


def test_api_agents_require_auth():
    client = TestClient(create_app())
    app = client.app
    _inject(client, app, RecordingLLM())

    assert client.post("/v1/agents", json={"name": "x", "system_prompt": "p"}).status_code == 401
    assert client.get("/v1/agents").status_code == 401


def test_api_agent_tenancy_isolation():
    client = TestClient(create_app())
    app = client.app
    _inject(client, app, RecordingLLM())

    a1 = _register_via_api(client, name="t1-agent")
    auth2 = {"Authorization": f"Bearer {TEST_API_KEY_2}"}
    client.post(
        "/v1/agents",
        json={"name": "t2-agent", "system_prompt": "p2", "role": "leader"},
        headers=auth2,
    )

    listing = client.get("/v1/agents", headers=auth2)
    ids = [a["id"] for a in listing.json()]
    assert a1["id"] not in ids
    assert client.get(f"/v1/agents/{a1['id']}", headers=auth2).status_code == 404


def test_api_swarm_create_list_run():
    client = TestClient(create_app())
    app = client.app
    _inject(client, app, RecordingLLM("FINAL ANSWER: team answer"))

    leader = _register_via_api(client, name="lead", role="leader", system_prompt="You lead.")
    w1 = _register_via_api(client, name="w1", system_prompt="You work.")
    w2 = _register_via_api(client, name="w2", system_prompt="You work too.")

    created = client.post(
        "/v1/swarms",
        json={"name": "team", "leader_id": leader["id"], "worker_ids": [w1["id"], w2["id"]]},
        headers=AUTH,
    )
    assert created.status_code == 201, created.text
    swarm = created.json()
    assert swarm["leader_id"] == leader["id"]

    listing = client.get("/v1/swarms", headers=AUTH)
    assert [s["id"] for s in listing.json()] == [swarm["id"]]

    run = client.post(f"/v1/swarms/{swarm['id']}/run", json={"task": "analyze"}, headers=AUTH)
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["final_response"] == "team answer"
    assert set(body["worker_responses"].keys()) == {w1["id"], w2["id"]}
    assert body["session_id"] == f"swarm:{swarm['id']}"

    missing = client.post("/v1/swarms/does-not-exist/run", json={"task": "x"}, headers=AUTH)
    assert missing.status_code == 404


def test_api_create_swarm_validates_members():
    client = TestClient(create_app())
    app = client.app
    _inject(client, app, RecordingLLM())

    resp = client.post(
        "/v1/swarms",
        json={"name": "bad", "leader_id": "missing", "worker_ids": []},
        headers=AUTH,
    )
    assert resp.status_code == 404
