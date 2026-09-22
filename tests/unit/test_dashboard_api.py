"""
Dashboard & streaming tests (Tier 1) - prove the product-facing surfaces.

Covers:
  - /v1/memory/graph  - concept graph surfaced for the dashboard, tenant-scoped
  - /v1/system/dreams - recent dream log from the activity feed
  - /v1/swarms/runs   - recent swarm runs from the activity feed
  - /v1/swarms/{id}/run-history - per-swarm history
  - /v1/chat/stream   - true SSE: thought/tool_call/observation/answer/done frames
  - ActivityFeed      - bounded feed keeps only recent entries
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import json

from fastapi.testclient import TestClient

from nexus.domain.entities.tool import Tool
from nexus.domain.value_objects.schema import JSONSchema
from nexus.infrastructure.api.main import create_app

from tests.fakes.container import FakeContainer, TEST_API_KEY_1, TEST_API_KEY_2

AUTH = {"Authorization": f"Bearer {TEST_API_KEY_1}"}
AUTH2 = {"Authorization": f"Bearer {TEST_API_KEY_2}"}


def _inject(client, app, llm=None):
    fake = FakeContainer()
    if llm is not None:
        fake.llm = llm
        fake.process_message._llm = llm
    app.state.container = fake
    client.app.state.container = fake
    return fake


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


# --------------------------------------------------------------------------- #
#  Activity feed
# --------------------------------------------------------------------------- #


def test_activity_feed_is_bounded_and_recent_first():
    from nexus.infrastructure.adapters.observability.activity_feed import InMemoryActivityFeed

    feed = InMemoryActivityFeed(max_entries=3)
    for i in range(5):
        feed.record("dream", {"session_id": f"s{i}", "tenant_id": "t1"})

    recent = feed.recent("dream")
    assert len(recent) == 3
    assert [r["session_id"] for r in recent] == ["s4", "s3", "s2"]
    assert feed.recent("swarm_run") == []


# --------------------------------------------------------------------------- #
#  /v1/memory/graph
# --------------------------------------------------------------------------- #


def test_graph_returns_nodes_and_edges():
    client = TestClient(create_app())
    app = client.app
    fake = _inject(client, app)

    from nexus.domain.entities.concept import Concept

    a = Concept(label="alphago", concept_type="AI")
    b = Concept(label="neural-net", concept_type="ML")
    fake.concept_repo.concepts[a.id] = a
    fake.concept_repo.concepts[b.id] = b
    fake.concept_repo._tenant_concepts[a.id] = "t1"
    fake.concept_repo._tenant_concepts[b.id] = "t1"
    import asyncio

    asyncio.run(fake.concept_repo.connect(a.id, b.id, tenant_id="t1"))

    r = client.get("/v1/memory/graph", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert {n["label"] for n in body["nodes"]} == {"alphago", "neural-net"}
    assert body["edges"][0]["source"] == a.id
    assert body["edges"][0]["target"] == b.id
    assert body["edges"][0]["weight"] > 0


def test_graph_is_tenant_scoped():
    client = TestClient(create_app())
    app = client.app
    fake = _inject(client, app)

    from nexus.domain.entities.concept import Concept

    other = Concept(label="alien-concept", concept_type="X")
    fake.concept_repo.concepts[other.id] = other
    fake.concept_repo._tenant_concepts[other.id] = "t2"

    r = client.get("/v1/memory/graph", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["nodes"] == []


# --------------------------------------------------------------------------- #
#  /v1/system/dreams
# --------------------------------------------------------------------------- #


def test_dreams_route_empty_then_recorded():
    client = TestClient(create_app())
    app = client.app
    fake = _inject(client, app)

    assert client.get("/v1/system/dreams", headers=AUTH).json() == []

    fake.activity_feed.record("dream", {"session_id": "dream-123", "tenant_id": "t1", "compression": True})
    r = client.get("/v1/system/dreams", headers=AUTH)
    assert r.status_code == 200
    entry = r.json()[0]
    assert entry["session_id"] == "dream-123"
    assert entry["tenant_id"] == "t1"


# --------------------------------------------------------------------------- #
#  /v1/swarms/runs + run-history
# --------------------------------------------------------------------------- #


def _run_swarm_via_api(client, llm=None):
    resp = client.post(
        "/v1/agents",
        json={"name": "lead", "system_prompt": "You lead.", "role": "leader"},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    leader = resp.json()
    resp = client.post(
        "/v1/agents",
        json={"name": "w1", "system_prompt": "You work."},
        headers=AUTH,
    )
    w1 = resp.json()
    created = client.post(
        "/v1/swarms",
        json={"name": "team", "leader_id": leader["id"], "worker_ids": [w1["id"]]},
        headers=AUTH,
    )
    assert created.status_code == 201, created.text
    swarm = created.json()

    run = client.post(f"/v1/swarms/{swarm['id']}/run", json={"task": "analyze"}, headers=AUTH)
    assert run.status_code == 200, run.text
    return swarm


def test_recent_swarm_runs_records_runs():
    client = TestClient(create_app())
    app = client.app
    _inject(client, app, ScriptedLLM(["FINAL ANSWER: team answer"]))

    swarm = _run_swarm_via_api(client)

    r = client.get("/v1/swarms/runs", headers=AUTH)
    assert r.status_code == 200
    runs = r.json()
    assert len(runs) == 1
    assert runs[0]["swarm_id"] == swarm["id"]
    assert runs[0]["swarm_name"] == "team"
    assert runs[0]["task"] == "analyze"
    assert runs[0]["worker_count"] >= 1


def test_run_history_filters_by_swarm_and_tenant():
    client = TestClient(create_app())
    app = client.app
    _inject(client, app, ScriptedLLM(["FINAL ANSWER: team answer"]))

    swarm_a = _run_swarm_via_api(client)
    _run_swarm_via_api(client)

    history = client.get(f"/v1/swarms/{swarm_a['id']}/run-history", headers=AUTH)
    assert history.status_code == 200
    assert all(r["swarm_id"] == swarm_a["id"] for r in history.json())

    # Tenant t2 never sees t1 runs.
    other = client.get("/v1/swarms/runs", headers=AUTH2)
    assert other.status_code == 200
    assert other.json() == []


# --------------------------------------------------------------------------- #
#  /v1/chat/stream
# --------------------------------------------------------------------------- #


def _add_calc_tool(fake):
    tool = Tool(
        name="calc",
        description="calculator",
        input_schema=JSONSchema(type="object", properties={}),
        output_schema=JSONSchema(type="object", properties={}),
        id="t-calc",
    )
    fake.tool_registry.tools[tool.id] = tool
    return tool


def test_stream_emits_thought_tool_observation_answer_done():
    client = TestClient(create_app())
    app = client.app
    fake = _inject(
        client,
        app,
        ScriptedLLM(
            [
                'TOOL_CALL: {"tool_id": "t-calc", "params": {"expression": "2+2"}}',
                "FINAL ANSWER: four",
            ]
        ),
    )
    _add_calc_tool(fake)

    with client.stream(
        "POST",
        "/v1/chat/stream",
        json={"message": "what is 2+2?", "session_id": "st1"},
        headers=AUTH,
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        events = []
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            events.append(json.loads(line[len("data: ") :]))

    types = [e["type"] for e in events]
    assert types[0] == "start"
    assert "thought" in types
    assert "tool_call" in types
    assert "observation" in types
    assert "answer" in types
    assert types[-1] == "done"

    tool_call = next(e for e in events if e["type"] == "tool_call")
    assert tool_call["tool_id"] == "t-calc"
    answer = next(e for e in events if e["type"] == "answer")
    assert answer["content"] == "four"


def test_stream_answer_only_path_has_done():
    client = TestClient(create_app())
    app = client.app
    _inject(client, app, ScriptedLLM(["FINAL ANSWER: directly"]))

    with client.stream(
        "POST",
        "/v1/chat/stream",
        json={"message": "hi"},
        headers=AUTH,
    ) as resp:
        events = [
            json.loads(line[len("data: ") :])
            for line in resp.iter_lines()
            if line and line.startswith("data: ")
        ]

    types = [e["type"] for e in events]
    assert types[0] == "start"
    assert types[-1] == "done"
    answer = next(e for e in events if e["type"] == "answer")
    assert answer["content"] == "directly"


def test_stream_requires_auth():
    client = TestClient(create_app())
    _inject(client, client.app)
    r = client.post("/v1/chat/stream", json={"message": "hi"})
    assert r.status_code == 401
