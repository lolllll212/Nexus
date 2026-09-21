"""
ProcessMessageUseCase - the primary conscious-loop use case.

Flow (exactly as specified in the blueprint):
    Receive message
      -> add to working context
      -> dispatch event to subconscious (NON-BLOCKING)
      -> retrieve relevant memories (vector + graph)
      -> run ReAct reasoning loop
      -> persist interaction as episodic memory
      -> return response

Dependency Rule: this module depends ONLY on domain ports and entities.
It has no idea Redis, Neo4j, OpenAI, or FastAPI exist.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from nexus.domain.entities.conversation import Conversation, MessageRole
from nexus.domain.entities.memory import Memory, MemoryType, EmotionalWeight
from nexus.domain.entities.thought import Thought, ThoughtType
from nexus.domain.ports.event_bus import Event, EventBus, EventTopic, EventPriority
from nexus.domain.ports.llm_provider import LLMProvider
from nexus.domain.ports.observability import Metrics, NoopMetrics, NoopTracer, Tracer

if TYPE_CHECKING:
    from nexus.application.cortex.session_manager import SessionManager
from nexus.domain.ports.memory_repository import ConceptRepository, MemoryRepository, ShortTermMemory
from nexus.domain.ports.execution import ToolExecutor
from nexus.domain.ports.tool_registry import ToolRegistry
from nexus.domain.exceptions import InvalidToolCallError, LLMUnavailableError
from nexus.application.cortex.react_prompt import REACT_SYSTEM_PROMPT


@dataclass
class MessageResult:
    """The result of processing a user message."""
    response: str
    session_id: str
    thoughts: List[Thought]
    tools_used: List[str]
    memories_recalled: int


class ProcessMessageUseCase:
    """
    Orchestrates the conscious loop for a single user message.
    All dependencies are injected ports - swap any adapter freely.
    """

    MAX_REACT_ITERATIONS = 15
    MEMORY_RECALL_LIMIT = 8
    MAX_CONTEXT_TOKENS = 12000  # Budget for context window
    SUMMARY_TRIGGER_TOKENS = 10000  # When to start trimming old observations

    def __init__(
        self,
        llm: LLMProvider,
        memory_repo: MemoryRepository,
        concept_repo: ConceptRepository,
        working_memory: ShortTermMemory,
        tools: ToolRegistry,
        executor: ToolExecutor,
        event_bus: EventBus,
        session_manager: "SessionManager",
        tracer: Tracer | None = None,
        metrics: Metrics | None = None,
    ) -> None:
        self._llm = llm
        self._memory_repo = memory_repo
        self._concept_repo = concept_repo
        self._working_memory = working_memory
        self._tools = tools
        self._executor = executor
        self._event_bus = event_bus
        self._sessions = session_manager
        self._tracer = tracer or NoopTracer()
        self._metrics = metrics or NoopMetrics()

    async def execute(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None,
        stream: bool = False,
        tenant_id: str = "default",
        image_urls: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
    ) -> MessageResult:
        started = time.perf_counter()
        async with self._tracer.span("process_message", {"user_id": user_id, "tenant_id": tenant_id}):
            conversation = await self._sessions.get_or_create(session_id, user_id, tenant_id)
            conversation.add_message(MessageRole.USER, message)
            conversation.observe_message(MessageRole.USER, message)

            # --- 1. Dispatch to subconscious. Fire and forget - NEVER blocks the user. ---
            await self._dispatch_to_subconscious(conversation, message)

            # --- 2. Recall relevant memories (graph + vector hybrid). ---
            memories = await self._recall(message, conversation)

            # --- 3. Run the ReAct loop (optionally multimodal / persona'd). ---
            thoughts: List[Thought] = []
            tools_used: List[str] = []
            response = await self._react_loop(conversation, memories, thoughts, tools_used, image_urls, system_prompt)

            # --- 4. Persist as episodic memory. ---
            await self._encode_episodic(conversation, response)

            conversation.add_message(MessageRole.NEXUS, response)

            # --- 5. Async: update short-term working memory. ---
            asyncio.get_running_loop().create_task(
                self._working_memory.set(
                    f"session:{conversation.tenant_id}:{conversation.session_id}",
                    {
                        "recent": conversation.to_llm_context(),
                        "emotional_state": conversation.emotional_state.__dict__,
                    },
                    ttl_seconds=3600,
                )
            )

            self._metrics.counter("chat_messages_total", labels={"tenant_id": tenant_id})
            self._metrics.histogram(
                "chat_processing_duration_seconds",
                time.perf_counter() - started,
                labels={"tenant_id": tenant_id},
            )

            return MessageResult(
                response=response,
                session_id=conversation.session_id,
                thoughts=thoughts,
                tools_used=tools_used,
                memories_recalled=len(memories),
            )

    # ------------------------------------------------------------------ #
    #  Internal orchestration steps
    # ------------------------------------------------------------------ #

    async def _dispatch_to_subconscious(self, conversation: Conversation, message: str) -> None:
        """Publish the user message to the event bus. Non-blocking for the cortex."""
        await self._event_bus.publish(
            Event(
                topic=EventTopic.USER_MESSAGE,
                payload={
                    "session_id": conversation.session_id,
                    "user_id": conversation.user_id,
                    "tenant_id": conversation.tenant_id,
                    "message": message,
                    "active_concepts": conversation.active_concepts,
                    "emotional_state": conversation.emotional_state.__dict__,
                },
                priority=EventPriority.HIGH,
            )
        )

    async def _recall(self, query: str, conversation: Conversation) -> List[Memory]:
        """Hybrid recall: vector similarity + graph traversal on active concepts."""
        tenant = conversation.tenant_id
        # Vector recall (semantic similarity)
        try:
            semantic = await self._memory_repo.retrieve(query, limit=self.MEMORY_RECALL_LIMIT, tenant_id=tenant)
        except Exception:
            semantic = []

        # Graph recall (concepts connected to currently active ones)
        graph_recalled: List[Memory] = []
        for concept_id in conversation.active_concepts[:5]:
            try:
                for conn in await self._concept_repo.get_connections(concept_id, tenant_id=tenant):
                    if len(graph_recalled) >= 3:
                        break
                    # Each connection implies a related memory; recall strengthens the synapse
                    related = await self._concept_repo.get(conn.target_id, tenant_id=tenant)
                    if related:
                        await self._concept_repo.upsert_connection(conn.reinforce(), tenant_id=tenant)
            except Exception:
                continue

        # Merge, de-duplicate by id, record accesses
        seen = set()
        merged: List[Memory] = []
        for m in [*semantic, *graph_recalled]:
            if m.id not in seen:
                seen.add(m.id)
                m.accessed()
                try:
                    await self._memory_repo.record_access(m.id, tenant_id=tenant)
                except Exception:
                    pass
                merged.append(m)
        return merged[: self.MEMORY_RECALL_LIMIT]

    async def _react_loop(
        self,
        conversation: Conversation,
        memories: List[Memory],
        thoughts: List[Thought],
        tools_used: List[str],
        image_urls: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Autonomous ReAct: Think -> Act -> Observe -> Repeat until final answer."""
        context = self._build_context(conversation, memories, image_urls, system_prompt)
        iteration = 0
        seen_tools: List[str] = []
        total_tokens = self._estimate_tokens(context)

        while iteration < self.MAX_REACT_ITERATIONS:
            iteration += 1

            # Token budget: trim old observations if over budget
            if total_tokens > self.SUMMARY_TRIGGER_TOKENS:
                context = self._trim_context(context)
                total_tokens = self._estimate_tokens(context)

            try:
                reasoning = await self._llm.complete(context)
            except LLMUnavailableError:
                return "My conscious engine is briefly unavailable. Please try again."

            thoughts.append(Thought(content=reasoning, thought_type=ThoughtType.REASONING))
            total_tokens += self._estimate_tokens([{"role": "assistant", "content": reasoning}])

            if self._is_final_answer(reasoning):
                return self._extract_answer(reasoning)

            tool_call = self._parse_tool_call(reasoning)
            if tool_call is None:
                # Model was still thinking — feed reasoning back and nudge it to act
                context.append({"role": "assistant", "content": reasoning})
                context.append({
                    "role": "system",
                    "content": (
                        "You are reasoning. Now either call a tool using TOOL_CALL format "
                        "or give FINAL ANSWER if you have enough information."
                    ),
                })
                total_tokens += 50
                continue

            tool_name = tool_call.get("tool_id", "unknown")

            # Prevent loops — if same tool called 3x in a row, force final answer
            seen_tools.append(tool_name)
            if len(seen_tools) >= 3 and seen_tools[-3:] == [tool_name] * 3:
                context.append({
                    "role": "system",
                    "content": f"You've called {tool_name} three times in a row. You have enough information. Give FINAL ANSWER now.",
                })
                continue

            # ACT
            tool = await self._tools.get(tool_name)
            if tool is None:
                context.append({
                    "role": "system",
                    "content": f"Tool '{tool_name}' does not exist. Available tools: read_file, list_directory, grep, run_python, calculator, diff_text, web_fetch, git_info. Pick one of these.",
                })
                continue

            tools_used.append(tool.name)
            succeeded = False
            try:
                result = await self._executor.execute(tool.id, tool_call.get("params", {}))
                succeeded = True
                observation = f"[OBSERVATION] {tool.name} returned:\n{result}"
            except Exception as exc:
                observation = f"[OBSERVATION] {tool.name} failed: {exc}. Try a different approach."
            tool.record_use(succeeded)

            thoughts.append(Thought(content=observation, thought_type=ThoughtType.OBSERVATION))
            context.append({"role": "system", "content": observation})

        # Final fallback — synthesize what we have
        return "I've reached my reasoning limit. Here's my best synthesis: " + self._extract_last_content(context)

    async def _encode_episodic(self, conversation: Conversation, response: str) -> None:
        """Persist the raw exchange as episodic memory for tonight's dreaming."""
        last_user = conversation.recent(1)[0].content if conversation.messages else ""
        state = conversation.emotional_state
        memory = Memory(
            content=f"USER: {last_user}\nNEXUS: {response}",
            memory_type=MemoryType.EPISODIC,
            concepts=list(conversation.active_concepts),
            metadata={
                "session_id": conversation.session_id,
                "user_id": conversation.user_id,
                "tenant_id": conversation.tenant_id,
            },
            context_state={
                "emotional": state.__dict__,
                "task": conversation.current_task,
            },
            emotional_weight=(
                EmotionalWeight(valence=state.valence, arousal=state.arousal, context=state.dominant_emotion)
                if state.intensity > 0.0
                else None
            ),
        )
        await self._memory_repo.store(memory, tenant_id=conversation.tenant_id)
        # Notify the nervous system
        await self._event_bus.publish(
            Event(topic=EventTopic.MEMORY_STORED, payload={"memory_id": memory.id, "concepts": memory.concepts})
        )

    # ------------------------------------------------------------------ #
    #  Pure helpers (no I/O) - trivially unit-testable
    # ------------------------------------------------------------------ #

    def _build_context(
        self,
        conversation: Conversation,
        memories: List[Memory],
        image_urls: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
    ) -> List[dict]:
        ctx = conversation.to_llm_context()

        # Build system messages in order of priority
        sys_msgs: List[dict] = []

        # 1. Agent/persona prompt — primary directive, always first
        if system_prompt:
            sys_msgs.append({"role": "system", "content": system_prompt})

        # 2. Tone from emotional state
        tone = conversation.emotional_state.tone_directive()
        if tone:
            sys_msgs.append({"role": "system", "content": tone})

        # 3. Recalled memories
        if memories:
            memory_block = "Relevant memories from past interactions:\n" + "\n".join(f"- {m.content}" for m in memories)
            sys_msgs.append({"role": "system", "content": memory_block})

        # 4. ReAct framework prompt — reasoning rules, goes last among system msgs
        sys_msgs.append({"role": "system", "content": REACT_SYSTEM_PROMPT})

        # Insert all system messages before the conversation
        for i, msg in enumerate(sys_msgs):
            ctx.insert(i, msg)

        if image_urls:
            ctx = self._attach_images(ctx, image_urls)
        return ctx

    def _attach_images(self, context: List[dict], image_urls: List[str]) -> List[dict]:
        """Convert the most recent user message into OpenAI content blocks with images.

        `content` becomes a list of {type: text|image_url} parts - the OpenAI
        chat-completions wire format. Text-only providers (and fakes) simply
        ignore the shape and return scripted output.
        """
        for idx in range(len(context) - 1, -1, -1):
            if context[idx].get("role") == "user" and isinstance(context[idx].get("content"), str):
                blocks: list = [{"type": "text", "text": context[idx]["content"]}]
                blocks.extend({"type": "image_url", "image_url": {"url": url}} for url in image_urls)
                context[idx] = {"role": "user", "content": blocks}
                break
        return context

    def _format_memories(self, memories: List[Memory]) -> str:
        """Legacy method — memories now injected in _build_context."""
        return "Relevant memories:\n" + "\n".join(f"- {m.content}" for m in memories)

    def _estimate_tokens(self, messages: List[dict]) -> int:
        """Rough token estimate: ~4 chars per token for English text."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content) // 4 + 4  # +4 for message overhead
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += len(part["text"]) // 4 + 4
        return total

    def _trim_context(self, context: List[dict]) -> List[dict]:
        """Trim old observations to stay within token budget.

        Strategy:
        1. Always keep system messages (first position = persona/ReAct prompt)
        2. Always keep the last 4 messages (recent reasoning + observations)
        3. Summarize middle observations into a single condensed message
        """
        if len(context) <= 6:
            return context

        # Separate system messages from conversation
        system_msgs = [m for m in context if m.get("role") == "system"]
        conv_msgs = [m for m in context if m.get("role") != "system"]

        if len(conv_msgs) <= 4:
            return context

        # Keep first system msg (persona) + last 4 conv messages
        kept_system = system_msgs[:1] if system_msgs else []
        kept_conv = conv_msgs[-4:]

        # Summarize what was dropped
        dropped = conv_msgs[:-4]
        observation_count = sum(1 for m in dropped if m.get("role") == "system")
        if observation_count > 0:
            summary = {
                "role": "system",
                "content": f"[Context trimmed: {observation_count} earlier observations summarized to save tokens. Recent context preserved.]",
            }
            return kept_system + [summary] + kept_conv

        return kept_system + kept_conv

    def _is_final_answer(self, reasoning: str) -> bool:
        upper = reasoning.upper()
        return "FINAL ANSWER:" in upper or "\nANSWER:" in upper or "ANSWER:" in upper

    def _extract_answer(self, reasoning: str) -> str:
        for marker in ["FINAL ANSWER:", "ANSWER:", "\nANSWER:"]:
            upper = reasoning.upper()
            marker_upper = marker.upper()
            if marker_upper in upper:
                idx = upper.index(marker_upper)
                return reasoning[idx + len(marker):].strip()
        return reasoning.strip()

    def _extract_last_content(self, context: List[dict]) -> str:
        """Get the last meaningful content from context."""
        for msg in reversed(context):
            content = msg.get("content", "")
            if content and msg.get("role") != "system":
                return content
        return context[-1]["content"] if context else ""

    def _parse_tool_call(self, reasoning: str):
        """
        Parse a tool invocation. Handles multiple formats:
            TOOL_CALL: {"tool_id": "...", "params": {...}}
            TOOL_CALL: {"tool": "...", "args": {...}}
        """
        import json

        # Find TOOL_CALL: marker (case-insensitive)
        marker = "TOOL_CALL:"
        upper = reasoning.upper()
        marker_idx = upper.find(marker)
        if marker_idx == -1:
            return None

        # Extract the JSON blob — find matching closing brace
        start = marker_idx + len(marker)
        snippet = reasoning[start:].strip()

        # Find the end of the JSON object
        depth = 0
        end = 0
        for i, ch in enumerate(snippet):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        if end == 0:
            return None

        json_str = snippet[:end]
        try:
            parsed = json.loads(json_str)
            # Normalize: accept "tool" or "tool_id", "args" or "params"
            tool_id = parsed.get("tool_id") or parsed.get("tool") or ""
            params = parsed.get("params") or parsed.get("args") or {}
            return {"tool_id": tool_id, "params": params}
        except json.JSONDecodeError:
            raise InvalidToolCallError(f"Malformed tool call: {json_str[:100]}")
