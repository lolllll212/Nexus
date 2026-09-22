"""Backup/DR contract - Qdrant snapshots + Neo4j JSONL dumps.

No Docker needed: inject fakes that mimic the HTTP/Driver surface we call.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from nexus.infrastructure.backup import BackupManager
from nexus.infrastructure.backup.neo4j_backup import Neo4jBackup
from nexus.infrastructure.backup.qdrant_backup import QdrantBackup

# ---------- Qdrant fakes ----------


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._payload


class FakeQdrantClient:
    """Minimal httpx-like client that records calls and serves canned snapshots."""

    def __init__(self):
        self.created: list[str] = []
        self.deleted: list[str] = []
        # pre-seeded snapshots for prune tests
        self._snapshots = [
            {"name": "snap-old-1", "creation_time": "2026-09-10T00:00:00", "size": 100},
            {"name": "snap-old-2", "creation_time": "2026-09-11T00:00:00", "size": 100},
            {"name": "snap-new-1", "creation_time": "2026-09-22T00:00:00", "size": 100},
        ]

    async def post(self, url):
        # create snapshot
        self.created.append(url)
        return _FakeResp(
            {"result": {"name": "snap-new-2", "creation_time": "2026-09-22T03:00:00", "size": 123}}
        )

    async def get(self, url):
        return _FakeResp({"result": list(self._snapshots)})

    async def delete(self, url):
        self.deleted.append(url)
        # drop from list so second prune is idempotent
        name = url.rsplit("/", 1)[-1]
        self._snapshots = [s for s in self._snapshots if s["name"] != name]
        return _FakeResp({"result": True})

    async def aclose(self):
        pass


async def test_qdrant_backup_create_and_prune():
    client = FakeQdrantClient()
    qb = QdrantBackup(host="fake", port=6333, client=client)

    snap = await qb.create_snapshot("nexus_memory")
    assert snap.name == "snap-new-2"

    # retain=2 should delete the oldest 1 (snap-old-1) when we have 3
    deleted = await qb.prune("nexus_memory", retain=2)
    assert deleted == ["snap-old-1"]
    assert any("snap-old-1" in u for u in client.deleted)

    # prune keeps newest 2 (snap-old-2, snap-new-1) -> nothing more to delete
    deleted2 = await qb.prune("nexus_memory", retain=2)
    assert deleted2 == []


async def test_qdrant_backup_list_snapshots():
    client = FakeQdrantClient()
    qb = QdrantBackup(host="fake", port=6333, client=client)
    snaps = await qb.list_snapshots("nexus_memory")
    assert len(snaps) == 3
    assert snaps[0].name == "snap-old-1"


# ---------- Neo4j fakes ----------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    async def data(self):
        return self._rows


class _FakeSession:
    def __init__(self, nodes, rels):
        self._nodes = nodes
        self._rels = rels
        self.runs: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def run(self, cypher, **params):
        self.runs.append((cypher, params))
        if "RETURN c" in cypher:
            return _FakeResult([{"c": n} for n in self._nodes])
        if "RETURN r" in cypher:
            return _FakeResult([{"r": r, "src": r["src"], "dst": r["dst"]} for r in self._rels])
        # import path MERGE
        return _FakeResult([])


class FakeNeo4jDriver:
    def __init__(self, nodes=None, rels=None):
        self._nodes = nodes or [
            {"id": "c1", "label": "Python", "type": "topic"},
            {"id": "c2", "label": "Rust", "type": "topic"},
        ]
        self._rels = rels or [{"src": "c1", "dst": "c2", "type": "semantic", "weight": 0.9}]
        self.sessions: list[_FakeSession] = []

    def session(self, database="neo4j"):
        s = _FakeSession(self._nodes, self._rels)
        self.sessions.append(s)
        return s

    async def close(self):
        pass


async def test_neo4j_export_import_roundtrip(tmp_path: pathlib.Path):
    driver = FakeNeo4jDriver()
    nb = Neo4jBackup(driver=driver)
    dest = tmp_path / "dump.jsonl"

    info = await nb.export(dest, tenant_id="default")
    assert info.nodes == 2
    assert info.relationships == 1
    assert dest.exists()
    lines = dest.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    kinds = [json.loads(l)["_kind"] for l in lines]
    assert kinds.count("node") == 2
    assert kinds.count("rel") == 1

    # Import into a fresh driver (captures MERGE runs)
    driver2 = FakeNeo4jDriver(nodes=[], rels=[])
    nb2 = Neo4jBackup(driver=driver2)
    info2 = await nb2.import_dump(dest, tenant_id="default")
    assert info2.nodes == 2
    assert info2.relationships == 1
    # last session should have recorded 3 MERGE runs
    assert len(driver2.sessions[0].runs) == 3  # 2 nodes + 1 rel


async def test_backup_manager_orchestrates_both(tmp_path: pathlib.Path):
    q_client = FakeQdrantClient()
    qb = QdrantBackup(host="fake", port=6333, client=q_client)
    driver = FakeNeo4jDriver()
    nb = Neo4jBackup(driver=driver)

    mgr = BackupManager(
        qdrant=qb, neo4j=nb, qdrant_collections=["nexus_memory"], retain_snapshots=10, dump_dir=tmp_path
    )
    result = await mgr.run(tenant_id="default")

    assert len(result.qdrant_snapshots) == 1
    assert result.neo4j is not None
    assert result.neo4j.nodes == 2
    assert result.errors == []
    # tenant-scoped collection name: default keeps base name, other tenants suffix
    mgr2 = BackupManager(
        qdrant=qb, neo4j=nb, qdrant_collections=["nexus_memory"], retain_snapshots=10, dump_dir=tmp_path
    )
    result2 = await mgr2.run(tenant_id="acme")
    # qdrant collection for acme is nexus_memory_acme -> post URL contains it
    assert any("nexus_memory_acme" in u for u in q_client.created)


async def test_backup_manager_records_errors(tmp_path: pathlib.Path):
    class BadQdrant:
        async def create_snapshot(self, collection):
            raise RuntimeError("qdrant down")

        async def prune(self, collection, retain=7):
            return []

    driver = FakeNeo4jDriver()
    nb = Neo4jBackup(driver=driver)
    mgr = BackupManager(qdrant=BadQdrant(), neo4j=nb, dump_dir=tmp_path)  # type: ignore[arg-type]
    result = await mgr.run()
    assert any("qdrant" in e for e in result.errors)
    assert result.neo4j is not None  # neo4j still succeeds
