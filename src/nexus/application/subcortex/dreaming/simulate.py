"""
DreamPhase 3: Simulation - solving tomorrow's problems tonight.

The brain reviews today's unresolved problems and spins up isolated
sandboxes to test candidate solutions overnight. When the user wakes up,
the answer is already waiting in their working memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from nexus.domain.entities.memory import Memory, MemoryType
from nexus.domain.entities.tool import Tool
from nexus.domain.ports.execution import ToolExecutor
from nexus.domain.ports.llm_provider import LLMProvider
from nexus.domain.ports.memory_repository import MemoryRepository, ShortTermMemory
from nexus.domain.ports.sandbox import Sandbox
from nexus.domain.value_objects.schema import JSONSchema


@dataclass
class SimulatedSolution:
    problem: str
    hypothesis: str
    verified: bool
    notes: str = ""


@dataclass
class SimulationResult:
    problems_identified: int
    solutions_tested: int = 0
    solutions_verified: List[SimulatedSolution] = field(default_factory=list)


_PROBLEM_SCHEMA = JSONSchema(
    type="object",
    properties={
        "problems": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "problem": {"type": "string"},
                    "context": {"type": "string"},
                },
                "required": ["problem"],
            },
        }
    },
    required=["problems"],
)


class SimulationUseCase:
    """Overnight future-simulation engine."""

    def __init__(
        self,
        llm: LLMProvider,
        sandbox: Sandbox,
        executor: ToolExecutor,
        memory_repo: MemoryRepository,
        working_memory: ShortTermMemory,
    ) -> None:
        self._llm = llm
        self._sandbox = sandbox
        self._executor = executor
        self._memory_repo = memory_repo
        self._working_memory = working_memory

    async def run(self, unresolved_memories: List[Memory], max_sandboxes: int = 5) -> SimulationResult:
        result = SimulationResult(problems_identified=len(unresolved_memories))

        problems = await self._extract_problems(unresolved_memories)
        for problem in problems[:max_sandboxes]:
            solution = await self._test_solution(problem)
            result.solutions_tested += 1
            if solution.verified:
                result.solutions_verified.append(solution)
                # Persist the verified solution as procedural memory
                await self._memory_repo.store(
                    Memory(
                        content=f"PROBLEM: {solution.problem}\nSOLUTION: {solution.hypothesis}",
                        memory_type=MemoryType.PROCEDURAL,
                        metadata={"origin": "dream_simulation"},
                    )
                )

        # Deliver findings to working memory so the cortex "already knows" at dawn.
        if result.solutions_verified:
            await self._working_memory.set(
                "dream:findings",
                {
                    "solutions": [
                        {"problem": s.problem, "solution": s.hypothesis, "notes": s.notes}
                        for s in result.solutions_verified
                    ],
                    "generated_at": __import__("datetime").datetime.utcnow().isoformat(),
                },
                ttl_seconds=86400,
            )

        return result

    async def _extract_problems(self, memories: List[Memory]) -> List[str]:
        if not memories:
            return []
        try:
            structured = await self._llm.extract_structured(
                "\n---\n".join(m.content for m in memories),
                schema=_PROBLEM_SCHEMA,
                instructions=(
                    "Identify concrete, unresolved problems the user is facing. "
                    "Focus on actionable technical/work problems that could be solved with code."
                ),
            )
            return [p["problem"] for p in structured.get("problems", [])]
        except Exception:
            return []

    async def _test_solution(self, problem: str) -> SimulatedSolution:
        """Generate a candidate solution and verify it in the sandbox."""
        try:
            code = await self._llm.complete(
                [
                    {
                        "role": "system",
                        "content": "Write a single self-contained Python function that solves this problem. "
                        "Return ONLY code, no explanations.",
                    },
                    {"role": "user", "content": problem},
                ]
            )
        except Exception as exc:
            return SimulatedSolution(problem=problem, hypothesis="", verified=False, notes=str(exc))

        # Strip markdown fences if present
        if "```" in code:
            code = code.split("```")[1]
            if code.startswith("python"):
                code = code[len("python"):]

        try:
            sandbox_result = await self._sandbox.run(code, timeout=60)
            verified = not sandbox_result.get("error")
            return SimulatedSolution(
                problem=problem,
                hypothesis=code,
                verified=verified,
                notes=sandbox_result.get("error") or f"Ran in {sandbox_result.get('duration_ms', '?')}ms",
            )
        except Exception as exc:
            return SimulatedSolution(problem=problem, hypothesis=code, verified=False, notes=str(exc))
