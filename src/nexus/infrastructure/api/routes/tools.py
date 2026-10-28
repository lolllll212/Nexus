"""Tool routes - inspect, execute, and trigger self-evolution capabilities.

Listing tools requires identity. Direct execution is admin-only and still
passes through the registry executor's schema, sandbox, confinement, and
approval gates; generating a tool is additionally rate limited.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexus.application.tools.generate_tool import ToolSpecRequest
from nexus.domain.exceptions import ToolNotFoundError
from nexus.domain.value_objects.identity import Identity
from nexus.infrastructure.adapters.execution.extended_tools import set_execution_context
from nexus.infrastructure.api.dependencies import (
    get_container,
    require_admin,
    require_identity,
    require_quota,
    require_rate_limit,
)
from nexus.infrastructure.di.container import Container

router = APIRouter(prefix="/v1/tools", tags=["tools"], dependencies=[Depends(require_identity)])


APPROVAL_GATED_TOOLS = (
    "run_shell",
    "write_file",
    "edit_file",
    "delete_file",
    "create_directory",
    "create_repository",
    "write_files",
    "batch_edit_files",
    "move_path",
    "copy_path",
    "delete_directory",
)

_TOOL_CATEGORIES: dict[str, str] = {
    "read_file": "files",
    "write_file": "files",
    "edit_file": "files",
    "delete_file": "files",
    "create_directory": "files",
    "create_repository": "projects",
    "list_directory": "files",
    "project_scan": "projects",
    "find_files": "files",
    "directory_tree": "files",
    "read_files": "files",
    "file_outline": "code",
    "find_symbol": "code",
    "code_diagnostics": "code",
    "git_diff": "code",
    "project_checks": "code",
    "secret_scan": "code",
    "release_readiness": "projects",
    "changelog_draft": "projects",
    "write_files": "files",
    "batch_edit_files": "files",
    "move_path": "files",
    "copy_path": "files",
    "delete_directory": "files",
    "grep": "code",
    "run_python": "code",
    "run_shell": "code",
    "pytest_runner": "code",
    "code_search_semantic": "code",
    "dependency_audit": "code",
    "git_info": "code",
    "diff_text": "code",
    "regex_extract": "code",
    "web_search": "web",
    "web_fetch": "web",
    "http_request": "web",
    "json_query": "data",
    "json_transform": "data",
    "csv_query": "data",
    "find_databases": "data",
    "query_database": "data",
    "calculator": "utilities",
    "current_datetime": "utilities",
    "hash_text": "utilities",
    "base64_encode": "utilities",
    "system_info": "system",
    "memory_graph_query": "memory",
    "process_multimodal_media": "multimodal",
}


def _schema_dict(schema: Any) -> dict[str, Any]:
    if schema is None:
        return {}
    if is_dataclass(schema):
        return asdict(schema)
    if isinstance(schema, dict):
        return schema
    return {
        "type": getattr(schema, "type", "object"),
        "properties": getattr(schema, "properties", {}),
        "required": getattr(schema, "required", []),
        "description": getattr(schema, "description", ""),
    }


class ToolOut(BaseModel):
    id: str
    name: str
    description: str
    status: str
    use_count: int
    success_rate: float
    is_self_generated: bool
    endpoint: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    category: str = "general"


class ToolExecuteRequest(BaseModel):
    tool_id: str = Field(..., min_length=1, max_length=200)
    params: dict[str, Any] = Field(default_factory=dict)


class ToolExecuteResponse(BaseModel):
    tool_id: str
    result: dict[str, Any]


class ToolApprovalOut(BaseModel):
    tool_id: str
    action: str
    approved: bool


class GrantToolApprovalsRequest(BaseModel):
    tool_ids: list[str] = Field(..., min_length=1, max_length=len(APPROVAL_GATED_TOOLS))


class GenerateRequest(BaseModel):
    name: str
    description: str = ""
    problem_statement: str = Field(..., min_length=10)
    requirements: list[str] = Field(default_factory=list)
    input_examples: list[dict] = Field(default_factory=list)
    expected_outputs: list[dict] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    tool_id: str
    name: str
    tests_passed: int
    endpoint: str | None = None


@router.get("", response_model=list[ToolOut])
async def list_tools(container: Container = Depends(get_container)):
    tools = await container.tool_registry.list_all()
    return [
        ToolOut(
            id=t.id,
            name=t.name,
            description=t.description,
            status=t.status.value,
            use_count=t.use_count,
            success_rate=t.success_rate,
            is_self_generated=t.is_self_generated,
            endpoint=t.endpoint,
            input_schema=_schema_dict(getattr(t, "input_schema", None)),
            output_schema=_schema_dict(getattr(t, "output_schema", None)),
            requires_approval=t.id in APPROVAL_GATED_TOOLS,
            category=_TOOL_CATEGORIES.get(t.id, "general"),
        )
        for t in tools
    ]


@router.get("/approvals", response_model=list[ToolApprovalOut])
async def list_tool_approvals(
    identity: Identity = Depends(require_admin),
    container: Container = Depends(get_container),
) -> list[ToolApprovalOut]:
    """Report whether each approval-gated tool is enabled for this tenant."""
    policy = getattr(container, "autonomy_policy", None)
    approvals: list[ToolApprovalOut] = []
    for tool_id in APPROVAL_GATED_TOOLS:
        action = f"tool:{tool_id}"
        approved = False
        if policy is not None:
            approved = await policy.require_approval(
                action, actor=identity.user_id, tenant_id=identity.tenant_id
            )
        approvals.append(ToolApprovalOut(tool_id=tool_id, action=action, approved=bool(approved)))
    return approvals


@router.post("/approvals/grant", response_model=list[ToolApprovalOut])
async def grant_tool_approvals(
    req: GrantToolApprovalsRequest,
    identity: Identity = Depends(require_admin),
    container: Container = Depends(get_container),
) -> list[ToolApprovalOut]:
    """Grant a tenant-wide approval for selected mutating tools (admin only)."""
    unknown = [tool_id for tool_id in req.tool_ids if tool_id not in APPROVAL_GATED_TOOLS]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Tools are not approval-gated or do not exist: {', '.join(sorted(set(unknown)))}",
        )
    policy = getattr(container, "autonomy_policy", None)
    if policy is None:
        raise HTTPException(status_code=503, detail="Autonomy policy is not configured")

    granted: list[ToolApprovalOut] = []
    for tool_id in dict.fromkeys(req.tool_ids):
        action = f"tool:{tool_id}"
        await policy.grant_approval(action, approver=identity.user_id, tenant_id=identity.tenant_id)
        granted.append(ToolApprovalOut(tool_id=tool_id, action=action, approved=True))
    return granted


@router.post("/execute", response_model=ToolExecuteResponse)
async def execute_tool(
    req: ToolExecuteRequest,
    identity: Identity = Depends(require_admin),
    container: Container = Depends(get_container),
) -> ToolExecuteResponse:
    """Execute one registered tool for the chat workspace's Tools panel.

    Admin-only at the HTTP boundary; the executor still validates schemas and
    enforces per-tool approval, workspace confinement, and sandbox rules.
    """
    role = getattr(identity.role, "value", identity.role)
    set_execution_context(
        {"tenant_id": identity.tenant_id, "actor": identity.user_id, "role": str(role)}
    )
    try:
        result = await container.executor.execute(req.tool_id, req.params)
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Tool not found: {req.tool_id}") from exc
    except Exception as exc:  # Defensive boundary: report, don't 500 the tool panel.
        raise HTTPException(status_code=502, detail=f"Tool execution failed: {exc}") from exc
    finally:
        set_execution_context(None)
    if not isinstance(result, dict):
        result = {"result": result}
    return ToolExecuteResponse(tool_id=req.tool_id, result=result)


@router.post(
    "/generate",
    response_model=GenerateResponse,
    dependencies=[
        Depends(require_admin),
        Depends(require_rate_limit("tool_gen")),
        Depends(require_quota("tool_gen")),
    ],
)
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
    return GenerateResponse(
        tool_id=result.tool.id,
        name=result.tool.name,
        tests_passed=result.tests_passed,
        endpoint=result.endpoint,
    )
