"""Pydantic request models for the cosmos backend routers."""

from typing import Any

from pydantic import BaseModel


class ModelSwitchRequest(BaseModel):
    provider: str
    model: str = ""
    api_key: str | None = None


class TrainingJudgeRequest(BaseModel):
    q: str
    a: str
    category: str = "custom"


class ReaAnalyzeRequest(BaseModel):
    tool: str
    path: str
    extra_args: dict[str, Any] = {}


class BlueprintSaveRequest(BaseModel):
    title: str
    goal: str = ""
    steps: list[str] = []
    files: list[str] = []
    verify: list[str] = []
    tools: list[str] = []
    tags: str = "rea"


class ResearchRequest(BaseModel):
    query: str


class ExtractExamplesRequest(BaseModel):
    note_path: str = ""


class WorkspaceRunRequest(BaseModel):
    prompt: str
    route: str = "deep_research"


class WorkspaceUpgradeRequest(BaseModel):
    plan: str = ""
