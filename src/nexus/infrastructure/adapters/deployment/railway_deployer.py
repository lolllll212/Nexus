"""Railway DeploymentProvider adapter - deploy generated tools to Railway.

Railway exposes a GraphQL API. Scaling is managed by Railway's autoscaling,
so `scale` is a no-op; `undeploy` removes the service.
"""

from __future__ import annotations

import httpx

from nexus.domain.exceptions import DeploymentError
from nexus.domain.ports.deployment import DeploymentInfo, DeploymentProvider, DeploymentRequest

_GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"

_MUTATIONS = {
    "create_service": """mutation CreateService($projectId: String!, $name: String!) {
        serviceCreate(input: {projectId: $projectId, name: $name}) { id }
    }""",
    "delete_service": """mutation DeleteService($id: String!) {
        serviceDelete(id: $id)
    }""",
}


class RailwayDeployer(DeploymentProvider):
    """Deploys a tool as a Railway service."""

    def __init__(
        self,
        token: str,
        project_id: str = "",
        base_url: str = _GRAPHQL_URL,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not token:
            raise ValueError("RailwayDeployer requires a RAILWAY_TOKEN")
        self._token = token
        self._project_id = project_id
        self._base_url = base_url
        self._client = http_client or httpx.AsyncClient()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    async def _graphql(self, mutation: str, variables: dict) -> dict:
        resp = await self._client.post(
            self._base_url,
            json={"query": mutation, "variables": variables},
            headers=self._headers(),
        )
        if resp.status_code != 200:
            raise DeploymentError(f"Railway API error {resp.status_code}: {resp.text[:200]}")
        body = resp.json()
        if body.get("errors"):
            raise DeploymentError(f"Railway rejected request: {body['errors']}")
        return body.get("data", {})

    async def deploy(self, request: DeploymentRequest) -> DeploymentInfo:
        data = await self._graphql(
            _MUTATIONS["create_service"],
            {"projectId": self._project_id, "name": request.name},
        )
        service_id = (data.get("serviceCreate") or {}).get("id")
        if not service_id:
            raise DeploymentError("Railway returned no service id")
        return DeploymentInfo(
            endpoint=f"https://{request.name}.up.railway.app",
            platform="railway",
            deployment_id=service_id,
            metadata={"service_name": request.name},
        )

    async def scale(self, deployment_id: str, instances: int) -> None:
        # Railway autoscale manages instances; nothing to do here.
        return None

    async def undeploy(self, deployment_id: str) -> None:
        await self._graphql(_MUTATIONS["delete_service"], {"id": deployment_id})
