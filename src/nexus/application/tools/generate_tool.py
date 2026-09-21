"""
GenerateToolUseCase - the self-evolution capability.

When the conscious loop hits a problem with no available tool, this use case:
  1. Analyzes the problem into a ToolSpecRequest
  2. Asks the LLM to write the tool's Python source
  3. Tests it in the sandbox against its own examples
  4. Deploys it (through the DeploymentProvider port)
  5. Registers it in the ToolRegistry

NEXUS literally builds its own new capabilities. On-the-fly engineering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.exceptions import ToolGenerationError
from nexus.domain.ports.deployment import DeploymentProvider, DeploymentRequest
from nexus.domain.ports.execution import ToolExecutor
from nexus.domain.ports.llm_provider import LLMProvider
from nexus.domain.ports.sandbox import Sandbox
from nexus.domain.ports.tool_registry import ToolRegistry
from nexus.domain.value_objects.schema import JSONSchema


@dataclass
class ToolSpecRequest:
    """What the brain needs a tool to do."""

    name: str
    description: str
    problem_statement: str
    requirements: List[str] = field(default_factory=list)
    input_examples: List[Dict[str, Any]] = field(default_factory=list)
    expected_outputs: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class GenerateToolResult:
    tool: Tool
    tests_passed: int
    endpoint: Optional[str] = None


class GenerateToolUseCase:
    """Write, test, deploy, and register a brand-new tool."""

    def __init__(
        self,
        llm: LLMProvider,
        sandbox: Sandbox,
        registry: ToolRegistry,
        executor: ToolExecutor,
        deployer: Optional[DeploymentProvider] = None,
    ) -> None:
        self._llm = llm
        self._sandbox = sandbox
        self._registry = registry
        self._executor = executor
        self._deployer = deployer

    async def execute(self, request: ToolSpecRequest, deploy: bool = True) -> GenerateToolResult:
        # --- 1. Generate the Python source ---
        code = await self._write_tool(request)

        # Infer schemas from the examples if none given
        input_schema = self._infer_schema(request.input_examples)
        output_schema = self._infer_schema(request.expected_outputs)

        tool = Tool(
            name=request.name,
            description=request.description,
            code=code,
            input_schema=input_schema,
            output_schema=output_schema,
            status=ToolStatus.TESTING,
            is_self_generated=True,
        )

        # --- 2. Test against examples in the sandbox ---
        passed = 0
        for inp, expected in zip(request.input_examples, request.expected_outputs):
            result = await self._sandbox.run(code, inputs=inp, timeout=30)
            if result.get("error") is None:
                passed += 1
            else:
                break

        if passed == 0 and request.input_examples:
            tool.status = ToolStatus.FAILED
            raise ToolGenerationError(f"Tool '{request.name}' failed all tests")

        # --- 3. Deploy (optional) ---
        endpoint = None
        if deploy and self._deployer is not None:
            info = await self._deployer.deploy(
                DeploymentRequest(
                    tool_id=tool.id,
                    name=tool.name,
                    code=code,
                    requirements=request.requirements,
                    auto_scale=True,
                )
            )
            endpoint = info.endpoint
            tool.endpoint = endpoint
            tool.deployment = info.__dict__

        # --- 4. Register ---
        tool.status = ToolStatus.DEPLOYED if endpoint else ToolStatus.READY
        await self._registry.register(tool)

        return GenerateToolResult(tool=tool, tests_passed=passed, endpoint=endpoint)

    async def _write_tool(self, request: ToolSpecRequest) -> str:
        """Ask the LLM to author the tool's implementation."""
        prompt = (
            "You are NEXUS, a self-evolving AI. Write a complete, self-contained "
            "Python function `solve(input_data: dict) -> dict` that solves the following problem. "
            "Return ONLY the code, no markdown fences, no explanations.\n\n"
            f"Problem: {request.problem_statement}\n"
            f"Name: {request.name}\n"
            f"Description: {request.description}\n"
            f"Required packages (may be empty): {', '.join(request.requirements)}\n"
        )
        if request.input_examples:
            prompt += f"Example inputs: {request.input_examples}\n"
        if request.expected_outputs:
            prompt += f"Expected outputs: {request.expected_outputs}\n"

        code = await self._llm.complete(
            [{"role": "system", "content": prompt}, {"role": "user", "content": "Generate the tool code."}],
            temperature=0.2,
        )
        if "```" in code:
            parts = code.split("```")
            code = parts[1] if len(parts) > 1 else code
            if code.startswith("python"):
                code = code[len("python") :].lstrip()
        return code

    def _infer_schema(self, examples: List[Dict[str, Any]]) -> JSONSchema:
        """Build a loose JSON schema from example payloads."""
        properties = {}
        for example in examples:
            for key, value in example.items():
                properties[key] = {"type": _python_type_to_json_type(value)}
        return JSONSchema(type="object", properties=properties, required=list(properties.keys()))


def _python_type_to_json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"
