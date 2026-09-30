"""
Deployment port - infrastructure control for self-generated tools.

NEXUS can spin up its own services. This abstracts away the platform
(Local process, Railway, Vercel, AWS Lambda, Docker) so the brain doesn't
care where its tools run.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DeploymentRequest:
    """What the brain wants deployed."""

    tool_id: str
    name: str
    code: str
    requirements: list = field(default_factory=list)
    resources: dict = field(default_factory=dict)  # cpu, memory
    environment: dict[str, str] = field(default_factory=dict)
    auto_scale: bool = False
    max_instances: int = 1


@dataclass
class DeploymentInfo:
    """What the platform returned."""

    endpoint: str
    platform: str
    deployment_id: str
    status: str = "active"
    metadata: dict = field(default_factory=dict)


class DeploymentProvider(ABC):
    """Deploys generated tool code to an execution platform."""

    @abstractmethod
    async def deploy(self, request: DeploymentRequest) -> DeploymentInfo: ...

    @abstractmethod
    async def scale(self, deployment_id: str, instances: int) -> None: ...

    @abstractmethod
    async def undeploy(self, deployment_id: str) -> None: ...
