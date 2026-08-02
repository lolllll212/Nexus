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
from dataclasses import dataclass
from typing import List, Optional

from nexus.domain.entities.conversation import Conversation, MessageRole, Session
from nexus.domain.entities.memory import Memory, MemoryType
from nexus.domain.entities.thought import Thought, ThoughtType
from nexus.domain.entities.tool import Tool
from nexus.domain.ports.event_bus import Event, EventBus, EventTopic, EventPriority
from nexus.domain.ports.llm_provider import LLMProvider
from nexus.domain.ports.memory_repository import ConceptRepository, MemoryRepository, ShortTermMemory
from nexus.domain.ports.tool_registry import ToolRegistry, ToolExecutor
from nexus.domain.exceptions import InvalidToolCallError, LLMUnavailableError


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

    MAX_REACT_ITERATIONS = 5
    MEMORY_RECALL_LIMIT = 8

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
    ) -> None:
        self._llm = llm
        self._memory_repo = memory_repo
        self._concept_repo = concept_repo
        self._working_memory = working_memory
        self._tools = tools
        self._executor = executor
        self._event_bus = event_bus
        self._sessions = session_manager

    async def execute(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None,
        stream: bool = False,
    ) -> MessageResult:
        conversation = await self._sessions.get_or_create(session_id, user_id)
        conversation.add_message(MessageRole.USER, message)

        # --- 1. Dispatch to subconscious. Fire and forget - NEVER blocks the user. ---
        await self._dispatch_to_subconscious(conversation, message)

        # --- 2. Recall relevant memories (graph + vector hybrid). ---
        memories = await self._recall(message, conversation)

        # --- 3. Run the ReAct loop. ---
        thoughts: List[Thought] = []
        tools_used: List[str] = []
        response = await self._react_loop(conversation, memories, thoughts, tools_used)

        # --- 4. Persist as episodic memory. ---
        await self._encode_episodic(conversation, response)

        conversation.add_message(MessageRole.NEXUS, response)

        # --- 5. Async: update short-term working memory. ---
        asyncio.get_running_loop().create_task(
            self._working_memory.set(
                f"session:{conversation.session_id}",
                {"recent": conversation.to_llm_context()},
                ttl_seconds=3600,
            )
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
                    "message": message,
                    "active_concepts": conversation.active_concepts,
                    "emotional_state": conversation.emotional_state.__dict__,
                },
                priority=EventPriority.HIGH,
            )
        )

    async def _recall(self, query: str, conversation: Conversation) -> List[Memory]:
        """Hybrid recall: vector similarity + graph traversal on active concepts."""
        # Vector recall (semantic similarity)
        try:
            semantic = await self._memory_repo.retrieve(query, limit=self.MEMORY_RECALL_LIMIT)
        except Exception:
            semantic = []

        # Graph recall (concepts connected to currently active ones)
        graph_recalled: List[Memory] = []
        for concept_id in conversation.active_concepts[:5]:
            try:
                for conn in await self._concept_repo.get_connections(concept_id):
                    if len(graph_recalled) >= 3:
                        break
                    # Each connection implies a related memory; recall strengthens the synapse
                    related = await self._concept_repo.get(conn.target_id)
                    if related:
                        await self._concept_repo.upsert_connection(conn.reinforce())
            except Exception:
                continue

        # Merge, de-duplicate by id, record accesses
        seen = set()
        merged: List[Memory] = []
        for m in [*semantic, *graph_recalled]:
            if m.id not in seen:
                seen.add(m.id)
                m.accessed()
                merged.append(m)
        return merged[: self.MEMORY_RECALL_LIMIT]

    async def _react_loop(
        self,
        conversation: Conversation,
        memories: List[Memory],
        thoughts: List[Thought],
        tools_used: List[str],
    ) -> str:
        """Reason -> Act -> Observe -> Repeat, until a final answer is reached."""
        context = self._build_context(conversation, memories)
        iteration = 0

        while iteration < self.MAX_REACT_ITERATIONS:
            iteration += 1

            try:
                reasoning = await self._llm.complete(context)
            except LLMUnavailableError:
                return "My conscious engine is briefly unavailable. Please try again."

            thoughts.append(Thought(content=reasoning, thought_type=ThoughtType.REASONING))

            if self._is_final_answer(reasoning):
                return self._extract_answer(reasoning)

            tool_call = self._parse_tool_call(reasoning)
            if tool_call is None:
                # Model was still thinking - feed reasoning back and continue
                context.append({"role": "assistant", "content": reasoning})
                continue

            # ACT
            tool = await self._tools.get(tool_call["tool_id"])
            if tool is None:
                context.append({"role": "system", "content": f"Tool '{tool_call['tool_id']}' does not exist."})
                continue

            tools_used.append(tool.name)
            succeeded = False
            try:
                # OBSERVE
                result = await self._executor.execute(tool.id, tool_call["params"])
                succeeded = True
                observation = f"Tool {tool.name} returned: {result}"
            except Exception as exc:
                observation = f"Tool {tool.name} failed: {exc}"
            tool.record_use(succeeded)

            thoughts.append(Thought(content=observation, thought_type=ThoughtType.OBSERVATION))
            context.append({"role": "system", "content": observation})

        return "I've reached my reasoning limit. Here's my best synthesis: " + context[-1]["content"]

    async def _encode_episodic(self, conversation: Conversation, response: str) -> None:
        """Persist the raw exchange as episodic memory for tonight's dreaming."""
        last_user = conversation.recent(1)[0].content if conversation.messages else ""
        memory = Memory(
            content=f"USER: {last_user}\nNEXUS: {response}",
            memory_type=MemoryType.EPISODIC,
            concepts=list(conversation.active_concepts),
            metadata={"session_id": conversation.session_id, "user_id": conversation.user_id},
            context_state={
                "emotional": conversation.emotional_state.__dict__,
                "task": conversation.current_task,
            },
        )
        await self._memory_repo.store(memory)
        # Notify the nervous system
        await self._event_bus.publish(
            Event(topic=EventTopic.MEMORY_STORED, payload={"memory_id": memory.id, "concepts": memory.concepts})
        )

    # ------------------------------------------------------------------ #
    #  Pure helpers (no I/O) - trivially unit-testable
    # ------------------------------------------------------------------ #

    def _build_context(self, conversation: Conversation, memories: List[Memory]) -> List[dict]:
        ctx = conversation.to_llm_context()
        if memories:
            ctx.insert(0, {"role": "system", "content": self._format_memories(memories)})
        return ctx

    def _format_memories(self, memories: List[Memory]) -> str:
        return "Relevant memories:\n" + "\n".join(f"- {m.content}" for m in memories)

    def _is_final_answer(self, reasoning: str) -> bool:
        return "FINAL ANSWER:" in reasoning.upper() or "\nANSWER:" in reasoning.upper()

    def _extract_answer(self, reasoning: str) -> str:
        marker = "FINAL ANSWER:"
        if marker in reasoning.upper():
            idx = reasoning.upper().index(marker)
            return reasoning[idx + len(marker):].strip()
        marker = "\nANSWER:"
        if marker.upper() in reasoning.upper():
            idx = reasoning.upper().index(marker.upper())
            return reasoning[idx + len(marker):].strip()
        return reasoning.strip()

    def _parse_tool_call(self, reasoning: str):
        """
        Parse a tool invocation. Expects a JSON block in the reasoning:
            TOOL_CALL: {"tool_id": "...", "params": {...}}
        """
        marker = "TOOL_CALL:"
        if marker not in reasoning.upper():
            return None
        import json

        idx = reasoning.upper().index(marker)
        snippet = reasoning[idx + len(marker):].strip()
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            raise InvalidToolCallError(f"Malformed tool call: {snippet[:100]}")
