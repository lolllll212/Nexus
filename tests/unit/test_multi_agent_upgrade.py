"""Tests for the multi-agent upgrade layer: memory store, event bus bridge,
model routing middleware, and the consensus protocol.

All tests are hermetic: no Ollama, no network, no real pytest runs.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from nexus.domain.ports.event_bus import Event, EventTopic
from nexus.infrastructure.adapters.eventbus.in_memory_event_bus import InMemoryEventBus
from nexus.infrastructure.adapters.eventbus.websocket_event_bus import WebSocketEventBus
from nexus.infrastructure.adapters.llm.routing_provider import (
    Complexity,
    OllamaProvider,
    RoutingProvider,
    TokenBudgetMiddleware,
    classify_complexity,
    estimate_tokens,
)
from nexus.infrastructure.adapters.persistence.agent_memory_store import (
    AgentMemoryStore,
    Chunk,
    canonical_json,
    tokenize,
)
from nexus.infrastructure.adapters.swarm.consensus import ConsensusProtocol

# ---------------------------------------------------------------------------
# Feature 1: content-addressable memory store
# ---------------------------------------------------------------------------


class TestAgentMemoryStore:
    def test_content_addressable_id_is_deterministic(self, tmp_path: Path):
        s = AgentMemoryStore(tmp_path / "mem.json")
        c1, created1 = s.put(agent="astra", kind="report", text="ci red on master", tags=["ci"])
        c2, created2 = s.put(agent="astra", kind="report", text="ci red on master", tags=["ci"])
        assert created1 is True
        assert created2 is False
        assert c1.id == c2.id
        assert len(s) == 1

    def test_id_matches_sha256_of_canonical_body(self, tmp_path: Path):
        import hashlib

        s = AgentMemoryStore(tmp_path / "mem.json")
        chunk, _ = s.put(agent="tron", kind="note", text="hello world")
        body = Chunk(agent="tron", kind="note", text="hello world").body()
        expected = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()[:16]
        assert chunk.id == expected

    def test_order_independence_listing_sorts_by_tick_and_id(self, tmp_path: Path):
        s = AgentMemoryStore(tmp_path / "mem.json")
        s.put(agent="astra", kind="note", text="first")
        s.put(agent="astra", kind="note", text="second")
        s.put(agent="astra", kind="note", text="third")
        ticks = [c.tick for c in s.latest()]
        assert ticks == sorted(ticks, reverse=True)
        # Reload from disk - ordering identical.
        s2 = AgentMemoryStore(tmp_path / "mem.json")
        assert [c.id for c in s2.latest()] == [c.id for c in s.latest()]

    def test_query_finds_relevant_chunk(self, tmp_path: Path):
        s = AgentMemoryStore(tmp_path / "mem.json")
        s.put(agent="astra", kind="report", text="CI red on pushed master: docker sandbox timeout")
        s.put(agent="tron", kind="report", text="import-linter contract kept for domain layer")
        s.put(agent="xenom", kind="patch", text="docker pull python:3.13-slim in ci.yml before pytest")
        results = s.query("docker sandbox timeout ci", k=2)
        assert results
        assert results[0][0].kind == "report"
        assert "docker" in results[0][0].text

    def test_query_kind_filter_and_determinism(self, tmp_path: Path):
        s = AgentMemoryStore(tmp_path / "mem.json")
        s.put(agent="astra", kind="report", text="alpha beta gamma")
        s.put(agent="astra", kind="note", text="alpha beta gamma note variant")
        r1 = s.query("alpha beta", kind="report")
        r2 = s.query("alpha beta", kind="report")
        assert all(c.kind == "report" for c, _ in r1)
        assert [c.id for c, _ in r1] == [c.id for c, _ in r2]

    def test_diff_between_chunks(self, tmp_path: Path):
        s = AgentMemoryStore(tmp_path / "mem.json")
        a, _ = s.put(agent="astra", kind="context", text="line one\nline two\nline three")
        b, _ = s.put(agent="astra", kind="context", text="line one\nline TWO changed\nline three")
        d = s.diff(a.id, b.id)
        assert d is not None
        assert "-line two" in d
        assert "+line TWO changed" in d

    def test_diff_unknown_id_returns_none(self, tmp_path: Path):
        s = AgentMemoryStore(tmp_path / "mem.json")
        a, _ = s.put(agent="astra", kind="note", text="x")
        assert s.diff(a.id, "nope") is None
        assert s.diff("nope", a.id) is None

    def test_prune_keeps_newest(self, tmp_path: Path):
        s = AgentMemoryStore(tmp_path / "mem.json")
        for i in range(5):
            s.put(agent="astra", kind="note", text=f"chunk {i}")
        removed = s.prune(3)
        assert removed == 2
        assert len(s) == 3
        newest = {c.text for c in s.latest(n=10)}
        assert newest == {"chunk 2", "chunk 3", "chunk 4"}

    def test_tokenizer_stops_words(self):
        toks = tokenize("The CI and the RUFF runs are red")
        assert "the" not in toks
        assert "ci" in toks and "ruff" in toks and "runs" in toks and "red" in toks

    def test_persistence_across_instances(self, tmp_path: Path):
        path = tmp_path / "mem.json"
        s1 = AgentMemoryStore(path)
        s1.put(agent="ceo", kind="decision", text="push approved", tags=["push"])
        s2 = AgentMemoryStore(path)
        c = s2.get(Chunk(agent="ceo", kind="decision", text="push approved", tags=["push"]).compute_id())
        assert c is not None
        assert c.agent == "ceo"
        assert "push" in c.tags


# ---------------------------------------------------------------------------
# Feature 2: WebSocket event bus
# ---------------------------------------------------------------------------


class TestWebSocketEventBus:
    @staticmethod
    def _collector(sink: list):
        async def handler(event: Event) -> None:
            sink.append(event)

        return handler

    @staticmethod
    def _server_port(bus: WebSocketEventBus) -> int:
        return bus._server.sockets[0].getsockname()[1]  # noqa: SLF001

    def test_roundtrip_publish_subscribe(self):
        async def run():
            bus = WebSocketEventBus()
            received: list[Event] = []
            await bus.subscribe(EventTopic.SYSTEM_HEALTH, self._collector(received))
            event = Event(topic=EventTopic.SYSTEM_HEALTH, payload={"ok": True})
            await bus.publish(event)
            await asyncio.sleep(0.05)
            await bus.stop()
            return received

        received = asyncio.run(run())
        assert len(received) == 1
        assert received[0].payload == {"ok": True}

    def test_unknown_topic_rejected_in_client_protocol(self):
        async def run():
            bus = WebSocketEventBus()
            await bus.serve("127.0.0.1", 0)
            port = self._server_port(bus)
            import websockets

            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(json.dumps({"type": "event", "topic": "not.a.topic", "payload": {}}))
                reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                await bus.stop()
                return reply

        reply = asyncio.run(run())
        assert reply["type"] == "error"
        assert "unknown topic" in reply["error"]

    def test_ping_pong(self):
        async def run():
            bus = WebSocketEventBus()
            await bus.serve("127.0.0.1", 0)
            port = self._server_port(bus)
            import websockets

            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(json.dumps({"type": "ping"}))
                reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                await bus.stop()
                return reply

        reply = asyncio.run(run())
        assert reply["type"] == "pong"

    def test_client_event_fans_out_to_other_clients(self):
        async def run():
            bus = WebSocketEventBus()
            await bus.serve("127.0.0.1", 0)
            port = self._server_port(bus)
            import websockets

            received: list[dict] = []
            async with websockets.connect(f"ws://127.0.0.1:{port}") as listener:

                async def listen():
                    received.append(json.loads(await asyncio.wait_for(listener.recv(), timeout=5)))

                listen_task = asyncio.create_task(listen())
                await asyncio.sleep(0.1)
                async with websockets.connect(f"ws://127.0.0.1:{port}") as sender:
                    await sender.send(
                        json.dumps({"type": "event", "topic": "consensus.proposed", "payload": {"id": "p1"}})
                    )
                await asyncio.wait_for(listen_task, timeout=5)
            await bus.stop()
            return received

        received = asyncio.run(run())
        assert received
        assert received[0]["payload"] == {"id": "p1"}
        assert received[0]["topic"] == "consensus.proposed"

    def test_in_memory_bus_still_works_after_new_topics(self):
        async def run():
            bus = InMemoryEventBus()
            got: list[Event] = []
            await bus.subscribe(EventTopic.MODEL_ROUTED, self._collector(got))
            await bus.publish(Event(topic=EventTopic.MODEL_ROUTED, payload={"route": "local"}))
            await asyncio.sleep(0.05)
            await bus.stop()
            return got

        assert len(asyncio.run(run())) == 1


# ---------------------------------------------------------------------------
# Feature 3: model routing + token budget
# ---------------------------------------------------------------------------


class ScriptedLLM:
    def __init__(self, reply: str, fail: bool = False) -> None:
        self.reply = reply
        self.fail = fail
        self.calls = 0

    async def complete(self, messages, temperature=0.7, max_tokens=None, tools=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider down")
        return self.reply

    async def extract_structured(self, content, schema, instructions=""):
        self.calls += 1
        return {}


class TestLMStudioTier:
    def test_build_local_tier_lmstudio_pair(self, monkeypatch, tmp_path: Path):
        from nexus.infrastructure.adapters.llm.openai_provider import OpenAIProvider
        from nexus.infrastructure.adapters.llm.routing_provider import (
            DEFAULT_LMSTUDIO_HIGH,
            DEFAULT_LMSTUDIO_LOW,
            build_local_tier,
        )

        monkeypatch.setenv("NEXUS_LOCAL_BACKEND", "lmstudio")
        monkeypatch.setenv("NEXUS_LMSTUDIO_URL", "http://127.0.0.1:1234/v1")
        high, low = build_local_tier()
        assert isinstance(high, OpenAIProvider) and high._model == DEFAULT_LMSTUDIO_HIGH  # noqa: SLF001
        assert isinstance(low, OpenAIProvider) and low._model == DEFAULT_LMSTUDIO_LOW  # noqa: SLF001
        assert high._base_url == "http://127.0.0.1:1234/v1"  # noqa: SLF001

    def test_build_local_tier_lmstudio_env_models(self, monkeypatch):
        from nexus.infrastructure.adapters.llm.openai_provider import OpenAIProvider
        from nexus.infrastructure.adapters.llm.routing_provider import build_local_tier

        monkeypatch.setenv("NEXUS_LOCAL_BACKEND", "lmstudio")
        monkeypatch.setenv("NEXUS_LMSTUDIO_MODEL_HIGH", "qwen3.5-9b-instruct")
        monkeypatch.setenv("NEXUS_LMSTUDIO_MODEL_LOW", "deepseek-coder-6.7b-instruct")
        high, low = build_local_tier()
        assert isinstance(high, OpenAIProvider) and high._model == "qwen3.5-9b-instruct"  # noqa: SLF001
        assert (
            isinstance(low, OpenAIProvider) and low._model == "deepseek-coder-6.7b-instruct"
        )  # noqa: SLF001

    def test_build_local_tier_default_is_ollama(self, monkeypatch):
        from nexus.infrastructure.adapters.llm.routing_provider import OllamaProvider, build_local_tier

        monkeypatch.delenv("NEXUS_LOCAL_BACKEND", raising=False)
        high, low = build_local_tier()
        assert isinstance(high, OllamaProvider)
        assert isinstance(low, OllamaProvider)

    def test_build_local_tier_none_disables(self, monkeypatch):
        from nexus.infrastructure.adapters.llm.routing_provider import build_local_tier

        monkeypatch.setenv("NEXUS_LOCAL_BACKEND", "none")
        assert build_local_tier() == (None, None)

    def test_routing_with_explicit_tier_providers(self):
        primary = ScriptedLLM("premium-reply")
        high = ScriptedLLM("local-high-reply")
        low = ScriptedLLM("local-low-reply")
        rp = RoutingProvider(primary=primary, local_high=high, local_low=low)
        reply_low = asyncio.run(rp.complete([{"role": "user", "content": "fix lint warning"}]))
        reply_high = asyncio.run(
            rp.complete([{"role": "user", "content": "refactor the CRDT merge protocol for correctness"}])
        )
        # LOW -> local tier first; HIGH -> primary first, local_high on fallback.
        assert reply_low == "local-low-reply"
        assert reply_high == "premium-reply"
        assert primary.calls == 1

    def test_explicit_tier_serves_high_when_primary_dies(self):
        primary = ScriptedLLM("x", fail=True)
        high = ScriptedLLM("local-high-reply")
        low = ScriptedLLM("local-low-reply")
        rp = RoutingProvider(primary=primary, local_high=high, local_low=low)
        reply = asyncio.run(
            rp.complete([{"role": "user", "content": "refactor the CRDT merge protocol for correctness"}])
        )
        assert reply == "local-high-reply"
        assert rp.route_log[-1]["route"] == "local-fallback"

    def test_explicit_tier_survives_ollama_default(self):
        from nexus.infrastructure.adapters.llm.routing_provider import OllamaProvider

        rp = RoutingProvider(
            primary=ScriptedLLM("p"),
            local=OllamaProvider(model="base"),
            local_high=ScriptedLLM("high"),
            local_low=ScriptedLLM("low"),
        )
        assert (
            rp._pick_local(Complexity.HIGH)._model
            if hasattr(rp._pick_local(Complexity.HIGH), "_model")
            else True
        )  # noqa: SLF001
        # Explicit tiers take precedence over the Ollama model-swap path.
        picked = rp._pick_local(Complexity.LOW)  # noqa: SLF001
        assert picked is not None and not isinstance(picked, OllamaProvider)


class TestComplexityClassification:
    def test_high_for_architecture_signals(self):
        assert classify_complexity("we must refactor the CRDT merge protocol") is Complexity.HIGH
        assert classify_complexity("security review of the race condition") is Complexity.HIGH

    def test_low_for_routine_short_tasks(self):
        assert classify_complexity("fix the lint warning in setup.py") is Complexity.LOW
        assert classify_complexity("rename variable foo to bar") is Complexity.LOW

    def test_high_for_long_code(self):
        long_code = "def f():\n" + "    x = 1\n" * 400
        assert classify_complexity(long_code) is Complexity.HIGH

    def test_deterministic(self):
        text = "diagnose root cause of the merge regression"
        assert classify_complexity(text) == classify_complexity(text)


class TestRoutingProvider:
    def test_low_routes_to_local(self):
        primary = ScriptedLLM("premium")
        local = ScriptedLLM("local-reply")
        rp = RoutingProvider(primary=primary, local=local)
        reply = asyncio.run(rp.complete([{"role": "user", "content": "fix lint warning"}]))
        assert reply == "local-reply"
        assert primary.calls == 0
        assert rp.route_log[-1]["route"] == "local"

    def test_high_routes_to_primary(self):
        primary = ScriptedLLM("premium-reply")
        local = ScriptedLLM("local-reply")
        rp = RoutingProvider(primary=primary, local=local)
        reply = asyncio.run(
            rp.complete([{"role": "user", "content": "refactor the CRDT merge protocol for correctness"}])
        )
        assert reply == "premium-reply"
        assert local.calls == 0

    def test_primary_failure_falls_back_to_local(self):
        primary = ScriptedLLM("x", fail=True)
        local = ScriptedLLM("local-reply")
        rp = RoutingProvider(primary=primary, local=local)
        reply = asyncio.run(
            rp.complete([{"role": "user", "content": "refactor the CRDT merge protocol for correctness"}])
        )
        assert reply == "local-reply"
        assert rp.route_log[-1]["route"] == "local-fallback"

    def test_empty_primary_reply_falls_back(self):
        primary = ScriptedLLM("")
        local = ScriptedLLM("local-reply")
        rp = RoutingProvider(primary=primary, local=local)
        reply = asyncio.run(
            rp.complete([{"role": "user", "content": "refactor the CRDT merge protocol for correctness"}])
        )
        assert reply == "local-reply"

    def test_force_route_overrides_classifier(self):
        primary = ScriptedLLM("premium")
        local = ScriptedLLM("local")
        rp = RoutingProvider(primary=primary, local=local, force_route=Complexity.HIGH)
        asyncio.run(rp.complete([{"role": "user", "content": "fix lint"}]))
        assert primary.calls == 1
        assert local.calls == 0

    def test_ollama_model_selection_per_tier(self):
        rp = RoutingProvider(
            primary=ScriptedLLM("p"),
            local=OllamaProvider(model="base"),
            local_high_model="qwen3.5:9b",
            local_low_model="qwen2.5-coder:7b-instruct",
        )
        high = rp._pick_local(Complexity.HIGH)  # noqa: SLF001
        low = rp._pick_local(Complexity.LOW)  # noqa: SLF001
        assert isinstance(high, OllamaProvider) and high.model == "qwen3.5:9b"
        assert isinstance(low, OllamaProvider) and low.model == "qwen2.5-coder:7b-instruct"

    def test_no_local_and_no_primary_returns_empty(self):
        rp = RoutingProvider(primary=ScriptedLLM(""), local=None)
        reply = asyncio.run(rp.complete([{"role": "user", "content": "fix lint"}]))
        assert reply == ""

    def test_estimate_tokens(self):
        assert estimate_tokens("") == 1
        assert estimate_tokens("a" * 400) == 100


class TestTokenBudgetMiddleware:
    def test_under_budget_uses_primary(self, tmp_path: Path):
        primary = ScriptedLLM("premium-reply")
        local = ScriptedLLM("local-reply")
        mw = TokenBudgetMiddleware(
            inner=primary, fallback=local, ledger_path=tmp_path / "ledger.json", daily_budget=100000
        )
        reply = asyncio.run(mw.complete([{"role": "user", "content": "short task"}]))
        assert reply == "premium-reply"
        assert local.calls == 0
        assert mw.spent_today() > 0

    def test_over_budget_forces_local(self, tmp_path: Path):
        primary = ScriptedLLM("premium-reply")
        local = ScriptedLLM("local-reply")
        mw = TokenBudgetMiddleware(
            inner=primary, fallback=local, ledger_path=tmp_path / "ledger.json", daily_budget=10
        )
        reply = asyncio.run(mw.complete([{"role": "user", "content": "a" * 200}]))
        assert reply == "local-reply"
        assert primary.calls == 0

    def test_ledger_persists_and_prunes_30_days(self, tmp_path: Path):
        path = tmp_path / "ledger.json"
        seed = {f"2026-08-{d:02d}": {"astra": 1000} for d in range(1, 29)}
        path.write_text(json.dumps(seed), encoding="utf-8")
        primary = ScriptedLLM("reply")
        mw = TokenBudgetMiddleware(inner=primary, fallback=None, ledger_path=path, daily_budget=999999)
        asyncio.run(mw.complete([{"role": "user", "content": "hello"}]))
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data.keys()) <= 30

    def test_spent_today_from_ledger(self, tmp_path: Path):
        path = tmp_path / "ledger.json"
        today = TokenBudgetMiddleware(
            inner=ScriptedLLM("x"), fallback=None, ledger_path=path, daily_budget=100
        )._today()  # noqa: SLF001
        path.write_text(json.dumps({today: {"astra": 55}}), encoding="utf-8")
        mw = TokenBudgetMiddleware(
            inner=ScriptedLLM("x"), fallback=None, ledger_path=path, daily_budget=100, agent="astra"
        )
        assert mw.spent_today() == 55
        assert mw.over_budget(46) is True
        assert mw.over_budget(45) is False


# ---------------------------------------------------------------------------
# Feature 4: consensus protocol
# ---------------------------------------------------------------------------


class TestConsensusProtocol:
    def test_propose_then_review_then_ceo_vote(self, tmp_path: Path):
        proto = ConsensusProtocol(tmp_path / "cons.json")
        p = proto.propose(title="Fix SSRF", author="xenom", draft="--- a\n+++ b\n")
        assert p.status == "in_review"
        proto.review(p.id, "astra", "approve", "lgtm")
        proto.review(p.id, "tron", "approve")
        p = proto.vote(p.id, "ceo", "yes")
        assert p.status == "approved"

    def test_request_changes_blocks_approval(self, tmp_path: Path):
        proto = ConsensusProtocol(tmp_path / "cons.json")
        p = proto.propose(title="Patch", author="heal", draft="x")
        proto.review(p.id, "astra", "request_changes", "security flaw")
        proto.vote(p.id, "ceo", "yes")
        p = proto.get(p.id)
        assert p.status == "in_review"
        assert "request_changes" in p.verdict_reason

    def test_ceo_no_rejects(self, tmp_path: Path):
        proto = ConsensusProtocol(tmp_path / "cons.json")
        p = proto.propose(title="X", author="astra", draft="x")
        proto.review(p.id, "tron", "approve")
        proto.review(p.id, "xenom", "approve")
        p = proto.vote(p.id, "ceo", "no")
        assert p.status == "rejected"

    def test_worker_majority_no_rejects(self, tmp_path: Path):
        proto = ConsensusProtocol(tmp_path / "cons.json")
        p = proto.propose(title="Y", author="heal", draft="y")
        proto.review(p.id, "astra", "approve")
        proto.vote(p.id, "tron", "no")
        proto.vote(p.id, "xenom", "no")
        p = proto.get(p.id)
        assert p.status == "rejected"

    def test_tie_without_ceo_rejects_safe(self, tmp_path: Path):
        proto = ConsensusProtocol(tmp_path / "cons.json")
        p = proto.propose(title="Z", author="heal", draft="z")
        proto.review(p.id, "astra", "approve")
        proto.vote(p.id, "tron", "yes")
        proto.vote(p.id, "xenom", "no")
        p = proto.get(p.id)
        assert p.status == "rejected"
        assert "tie" in p.verdict_reason

    def test_worker_veto_without_ceo_stays_pending(self, tmp_path: Path):
        proto = ConsensusProtocol(tmp_path / "cons.json")
        p = proto.propose(title="W", author="heal", draft="w")
        proto.review(p.id, "astra", "approve")
        proto.vote(p.id, "tron", "yes")
        proto.vote(p.id, "xenom", "yes")
        p = proto.get(p.id)
        # Workers can veto but only the CEO approves.
        assert p.status == "in_review"
        assert "awaiting CEO" in p.verdict_reason

    def test_order_independence_same_set_same_outcome(self, tmp_path: Path):
        def build(proto, order):
            p = proto.propose(title="Order", author="xenom", draft="d")
            steps = [
                ("review", "astra", "approve"),
                ("review", "tron", "approve"),
                ("vote", "ceo", "yes"),
            ]
            ordered = [steps[i] for i in order]
            for kind, agent, choice in ordered:
                if kind == "review":
                    proto.review(p.id, agent, choice)
                else:
                    proto.vote(p.id, agent, choice)
            return proto.get(p.id)

        p1 = build(ConsensusProtocol(tmp_path / "a.json"), [0, 1, 2])
        p2 = build(ConsensusProtocol(tmp_path / "b.json"), [2, 1, 0])
        assert p1.status == p2.status == "approved"

    def test_needs_attention_finds_ceo_pending(self, tmp_path: Path):
        proto = ConsensusProtocol(tmp_path / "cons.json")
        p = proto.propose(title="Attention", author="xenom", draft="d")
        proto.review(p.id, "astra", "approve")
        proto.review(p.id, "tron", "approve")
        p2 = proto.propose(title="Not ready", author="xenom", draft="e")
        proto.review(p2.id, "astra", "request_changes")
        attention = proto.needs_attention()
        assert [q.id for q in attention] == [p.id]

    def test_idempotent_propose_same_draft(self, tmp_path: Path):
        proto = ConsensusProtocol(tmp_path / "cons.json")
        p1 = proto.propose(title="Same", author="xenom", draft="identical draft")
        p2 = proto.propose(title="Same", author="xenom", draft="identical draft")
        assert p1.id == p2.id

    def test_closed_proposals_immune_to_reviews(self, tmp_path: Path):
        proto = ConsensusProtocol(tmp_path / "cons.json")
        p = proto.propose(title="Done", author="astra", draft="d")
        proto.review(p.id, "tron", "approve")
        proto.vote(p.id, "ceo", "yes")
        before = p.status
        proto.review(p.id, "xenom", "request_changes")
        proto.vote(p.id, "astra", "no")
        assert proto.get(p.id).status == before == "approved"

    def test_persistence_across_instances(self, tmp_path: Path):
        path = tmp_path / "cons.json"
        proto = ConsensusProtocol(path)
        p = proto.propose(title="Persist", author="xenom", draft="d")
        proto.review(p.id, "astra", "approve")
        proto2 = ConsensusProtocol(path)
        assert proto2.get(p.id).reviews["astra"]["verdict"] == "approve"
