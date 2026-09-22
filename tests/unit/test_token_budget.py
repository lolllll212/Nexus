"""
ReAct token-budget tests - verify observation capping, summarization, and
the hard-context behavior of the conscious loop.
"""

from __future__ import annotations

from tests.fakes.container import FakeContainer


class ScriptedLLM:
    """Replays a script of responses; records every call made."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = []
        self.prompt_texts = []

    async def complete(self, messages, temperature=0.7, max_tokens=4096, tools=None):
        self.calls.append(messages)
        user_text = " ".join(str(m.get("content", "")) for m in messages)
        self.prompt_texts.append(user_text)
        return self._script.pop(0) if self._script else "FINAL ANSWER: done"


async def test_large_observation_is_truncated():
    """Tool results longer than MAX_OBSERVATION_CHARS are capped in context."""
    fake = FakeContainer()

    class HugeExecutor:
        async def execute(self, tool_id, params):
            return {"data": "x" * 100_000}

    fake.executor = HugeExecutor()
    fake.process_message._executor = HugeExecutor()

    llm = ScriptedLLM(
        [
            'TOOL_CALL: {"tool_id": "read_file", "params": {"path": "p.py"}}',
            "FINAL ANSWER: done",
        ]
    )
    fake.llm = llm
    fake.process_message._llm = llm


    uc = fake.process_message
    uc.MAX_OBSERVATION_CHARS = 100  # force truncation hard

    result = await fake.process_message.execute(user_id="u", message="read the file", tenant_id="default")

    # The second LLM call (after the tool call) sees the context. The huge
    # result must be truncated, not embedded at full length.
    assert len(llm.calls) >= 2
    full_context = " ".join(str(m.get("content", "")) for m in llm.calls[1] if isinstance(m, dict))
    assert "x" * 1000 not in full_context
    assert result.response == "done"


async def test_summarize_context_preserves_system_and_recent():
    """Compaction keeps all system messages + last N conv messages."""
    from nexus.application.cortex.process_message import ProcessMessageUseCase

    uc = ProcessMessageUseCase.__new__(ProcessMessageUseCase)
    uc.SUMMARIZE_KEEP_MESSAGES = 6

    class StaticLLM:
        async def complete(self, messages, temperature=0.0, max_tokens=200):
            return "COMPACTED SUMMARY"

    uc._llm = StaticLLM()

    context = [
        {"role": "system", "content": "REACT_RULES"},
        {"role": "user", "content": "hi"},
    ]
    context.extend({"role": "user", "content": f"[OBSERVATION] tool returned data {i}"} for i in range(20))

    out = await uc._summarize_context(context, tools=None)
    system_msgs = [m for m in out if m.get("role") == "system"]
    # REACT_RULES preserved + one compaction summary = 2 system msgs
    assert any("REACT_RULES" in m["content"] for m in system_msgs)
    assert any("COMPACTED SUMMARY" in m["content"] for m in system_msgs)
    # Recent conversation preserved
    assert len([m for m in out if m.get("role") != "system"]) <= uc.SUMMARIZE_KEEP_MESSAGES


async def test_summarize_context_falls_back_when_llm_fails():
    """If the LLM summarization throws, a static note is used."""
    from nexus.application.cortex.process_message import ProcessMessageUseCase

    uc = ProcessMessageUseCase.__new__(ProcessMessageUseCase)
    uc.SUMMARIZE_KEEP_MESSAGES = 4

    class BrokenLLM:
        async def complete(self, messages, temperature=0.0, max_tokens=200):
            raise RuntimeError("model down")

    uc._llm = BrokenLLM()

    context = [
        {"role": "system", "content": "RULES"},
        {"role": "user", "content": "q"},
        {"role": "user", "content": "[OBSERVATION] a"},
        {"role": "user", "content": "[OBSERVATION] b"},
        {"role": "user", "content": "[OBSERVATION] c"},
        {"role": "user", "content": "[OBSERVATION] d"},
        {"role": "user", "content": "[OBSERVATION] e"},
    ]
    out = await uc._summarize_context(context, tools=None)
    contents = " ".join(str(m.get("content", "")) for m in out)
    assert "Context compacted" in contents
    assert "RULES" in contents


async def test_hard_budget_returns_synthesized_answer():
    """When compaction still exceeds MAX_CONTEXT_TOKENS, the loop stops early."""
    fake = FakeContainer()
    fake.process_message._llm = fake.llm

    from nexus.domain.entities.memory import Memory, MemoryType
    from nexus.domain.entities.conversation import Conversation

    uc = fake.process_message
    uc.SUMMARY_TRIGGER_TOKENS = 0  # always compact on first iteration
    uc.MAX_CONTEXT_TOKENS = 50  # tiny hard budget
    uc.SUMMARIZE_KEEP_MESSAGES = 2

    memory = Memory(content="a prefix fact", memory_type=MemoryType.SEMANTIC)
    from nexus.domain.entities.conversation import MessageRole

    conv = Conversation(session_id="s1", user_id="u1", tenant_id="default")
    conv.add_message(MessageRole.USER, "question")

    result = await uc._react_loop(conv, [memory], [], [])
    assert "FINAL ANSWER" in result.upper() or "synthesis" in result.lower()
