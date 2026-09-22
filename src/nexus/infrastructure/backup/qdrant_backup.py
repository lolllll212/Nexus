"""Qdrant snapshot backup - thin wrapper over the Qdrant HTTP snapshot API.

Qdrant exposes snapshots per collection:
  POST   /collections/{name}/snapshots          -> create
  GET    /collections/{name}/snapshots          -> list
  GET    /collections/{name}/snapshots/{snap}   -> download
  DELETE /collections/{name}/snapshots/{snap}   -> delete
  POST   /collections/{name}/snapshots/recover  -> restore

This module only needs create/list/delete for backups; download/recover are
used for DR restores.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any


@dataclass
class SnapshotInfo:
    name: str
    creation_time: str
    size: int | None = None


class QdrantBackup:
    """Create/list/delete Qdrant collection snapshots via HTTP."""

    def __init__(self, host: str = "localhost", port: int = 6333, client: Any | None = None) -> None:
        self._host = host
        self._port = port
        self._client = client  # injectable httpx.AsyncClient for tests

    def _base(self) -> str:
        return f"http://{self._host}:{self._port}"

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is not None:
            return self._client
        import httpx

        return httpx.AsyncClient(timeout=30.0)

    async def create_snapshot(self, collection: str) -> SnapshotInfo:
        url = f"{self._base()}/collections/{collection}/snapshots"
        client = self._get_client()
        close = self._client is None
        try:
            resp = await client.post(url)
            resp.raise_for_status()
            data = resp.json()
            result = data.get("result") or {}
            name = result.get("name") or f"snap-{datetime.datetime.utcnow().isoformat()}"
            creation = result.get("creation_time") or datetime.datetime.utcnow().isoformat()
            size = result.get("size")
            return SnapshotInfo(name=name, creation_time=creation, size=size)
        finally:
            if close:
                await client.aclose()

    async def list_snapshots(self, collection: str) -> list[SnapshotInfo]:
        url = f"{self._base()}/collections/{collection}/snapshots"
        client = self._get_client()
        close = self._client is None
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("result") or []
            out: list[SnapshotInfo] = []
            for item in raw:
                out.append(
                    SnapshotInfo(
                        name=item.get("name", ""),
                        creation_time=item.get("creation_time", ""),
                        size=item.get("size"),
                    )
                )
            return out
        finally:
            if close:
                await client.aclose()

    async def delete_snapshot(self, collection: str, name: str) -> None:
        url = f"{self._base()}/collections/{collection}/snapshots/{name}"
        client = self._get_client()
        close = self._client is None
        try:
            resp = await client.delete(url)
            resp.raise_for_status()
        finally:
            if close:
                await client.aclose()

    async def prune(self, collection: str, retain: int = 7) -> list[str]:
        """Keep the newest `retain` snapshots, delete the rest. Returns deleted names."""
        snapshots = await self.list_snapshots(collection)
        if len(snapshots) <= retain:
            return []
        # Sort by creation_time ascending (oldest first)
        snapshots.sort(key=lambda s: s.creation_time)
        to_delete = snapshots[: len(snapshots) - retain]
        deleted: list[str] = []
        for snap in to_delete:
            await self.delete_snapshot(collection, snap.name)
            deleted.append(snap.name)
        return deleted
