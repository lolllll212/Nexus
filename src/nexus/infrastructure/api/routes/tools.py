"""Tool routes - inspect and trigger the self-evolution capability.

Listing tools requires identity; generating a tool is additionally rate
limited (self-evolution is expensive and a prime abuse target).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import List

from nexus.application.tools.generate_tool import ToolSpecRequest
from nexus.infrastructure.api.dependencies import get_container, require_identity, require_rate_limit
from nexus.infrastructure.di.container import Container

router = APIRouter(prefix="/v1/tools", tags=["tools"], dependencies=[Depends(require_identity)])


class ToolOut(BaseModel):
    id: str
    name: str
    description: str
    status: str
    use_count: int
    success_rate: float
    is_self_generated: bool
    endpoint: str | None = None


class GenerateRequest(BaseModel):
    name: str
    description: str = ""
    problem_statement: str = Field(..., min_length=10)
    requirements: List[str] = Field(default_factory=list)
    input_examples: List[dict] = Field(default_factory=list)
    expected_outputs: List[dict] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    tool_id: str
    name: str
    tests_passed: int
    endpoint: str | None = None


@router.get("", response_model=List[ToolOut])
async def list_tools(container: Container = Depends(get_container)):
    tools = await container.tool_registry.list_all()
    return [
        ToolOut(
            id=t.id, name=t.name, description=t.description, status=t.status.value,
            use_count=t.use_count, success_rate=t.success_rate,
            is_self_generated=t.is_self_generated, endpoint=t.endpoint,
        )
        for t in tools
    ]


@router.post("/generate", response_model=GenerateResponse, dependencies=[Depends(require_rate_limit("tool_gen"))])
async def generate_tool(req: GenerateRequest, container: Container = Depends(get_container)):
    result = await container.tool_generator.execute(
        ToolSpecRequest(
            name=req.name,
            description=req.description,
            problem_statement=req.problem_statement,
            requirements=req.requirements,
            input_examples=req.input_examples,
            expected_outputs=req.expected_outputs,
        ),
        deploy=True,
    )
    return GenerateResponse(tool_id=result.tool.id, name=result.tool.name, tests_passed=result.tests_passed, endpoint=result.endpoint)
