"""Vercel DeploymentProvider adapter - deploy generated tools to Vercel.

Vercel runs serverless functions; the generated Python solve() logic is
packaged as an api/ handler and uploaded through the REST Deployments API.
"""

from __future__ import annotations

import httpx

from nexus.domain.exceptions import DeploymentError
from nexus.domain.ports.deployment import DeploymentInfo, DeploymentProvider, DeploymentRequest

_API_BASE = "https://api.vercel.com/v13/deployments"


class VercelDeployer(DeploymentProvider):
    """Deploys a tool as a Vercel serverless function."""

    def __init__(
        self,
        token: str,
        team_id: str | None = None,
        api_base: str = _API_BASE,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not token:
            raise ValueError("VercelDeployer requires a VERCEL_TOKEN")
        self._token = token
        self._team_id = team_id
        self._api_base = api_base
        self._client = http_client or httpx.AsyncClient()

    def _headers(self) -> dict:
        headers = {"Authorization": f"Bearer {self._token}"}
        if self._team_id:
            headers["x-vercel-team"] = self._team_id
        return headers

    def _build_files(self, request: DeploymentRequest) -> list:
        entry = (
            "import json\n"
            "from http.server import BaseHTTPRequestHandler\n"
            "\n"
            "class handler(BaseHTTPRequestHandler):\n"
            "    def do_POST(self):\n"
            "        length = int(self.headers.get('Content-Length', 0))\n"
            "        payload = json.loads(self.rfile.read(length) or b'{}') if length else {}\n"
            "        from logic import solve\n"
            "        body = json.dumps({'ok': True, 'result': solve(payload)})\n"
            "        self.send_response(200)\n"
            "        self.send_header('Content-Type', 'application/json')\n"
            "        self.end_headers()\n"
            "        self.wfile.write(body.encode())\n"
        )
        return [
            {"file": "api/index.py", "data": entry},
            {"file": "api/logic.py", "data": request.code},
            {"file": "requirements.txt", "data": "\n".join(request.requirements or [])},
        ]

    async def deploy(self, request: DeploymentRequest) -> DeploymentInfo:
        payload = {
            "name": request.name,
            "files": self._build_files(request),
            "projectSettings": {"framework": None},
        }
        resp = await self._client.post(self._api_base, json=payload, headers=self._headers())
        if resp.status_code not in (200, 201):
            raise DeploymentError(f"Vercel API error {resp.status_code}: {resp.text[:200]}")
        body = resp.json()
        deployment_id = body.get("id")
        if not deployment_id:
            raise DeploymentError("Vercel returned no deployment id")
        url = body.get("url")
        endpoint = f"https://{url}" if url else f"https://{request.name}.vercel.app"
        return DeploymentInfo(
            endpoint=endpoint,
            platform="vercel",
            deployment_id=deployment_id,
            metadata={"deployment_url": endpoint},
        )

    async def scale(self, deployment_id: str, instances: int) -> None:
        # Serverless functions scale implicitly; nothing to do here.
        return None

    async def undeploy(self, deployment_id: str) -> None:
        resp = await self._client.delete(
            f"{self._api_base}/{deployment_id}", headers=self._headers()
        )
        if resp.status_code >= 400:
            raise DeploymentError(f"Vercel delete error {resp.status_code}: {resp.text[:200]}")
