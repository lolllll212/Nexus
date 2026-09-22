"""BackupManager - orchestrate Qdrant + Neo4j backups with retention."""

from __future__ import annotations

import datetime
import pathlib
from dataclasses import dataclass, field

from nexus.infrastructure.backup.neo4j_backup import Neo4jBackup, Neo4jDumpInfo
from nexus.infrastructure.backup.qdrant_backup import QdrantBackup, SnapshotInfo


@dataclass
class BackupResult:
    timestamp: str
    qdrant_snapshots: list[SnapshotInfo] = field(default_factory=list)
    qdrant_pruned: list[str] = field(default_factory=list)
    neo4j: Neo4jDumpInfo | None = None
    errors: list[str] = field(default_factory=list)


class BackupManager:
    """Run collection snapshots + graph dump, prune old snapshots."""

    def __init__(
        self,
        qdrant: QdrantBackup | None = None,
        neo4j: Neo4jBackup | None = None,
        qdrant_collections: list[str] | None = None,
        retain_snapshots: int = 7,
        dump_dir: str | pathlib.Path = "backups",
    ) -> None:
        self._qdrant = qdrant
        self._neo4j = neo4j
        self._collections = qdrant_collections or ["nexus_memory"]
        self._retain = retain_snapshots
        self._dump_dir = pathlib.Path(dump_dir)

    async def run(self, tenant_id: str = "default") -> BackupResult:
        ts = datetime.datetime.utcnow().isoformat()
        result = BackupResult(timestamp=ts)
        # Qdrant per-collection snapshots
        if self._qdrant is not None:
            for coll in self._collections:
                # Per-tenant collection name mirrors QdrantMemoryRepository
                name = coll if tenant_id == "default" else f"{coll}_{tenant_id}"
                try:
                    snap = await self._qdrant.create_snapshot(name)
                    result.qdrant_snapshots.append(snap)
                    pruned = await self._qdrant.prune(name, retain=self._retain)
                    result.qdrant_pruned.extend(pruned)
                except Exception as exc:
                    result.errors.append(f"qdrant:{name}:{exc}")
        # Neo4j dump
        if self._neo4j is not None:
            try:
                self._dump_dir.mkdir(parents=True, exist_ok=True)
                dest = self._dump_dir / f"neo4j-{tenant_id}-{ts.replace(':','-')}.jsonl"
                info = await self._neo4j.export(dest, tenant_id=tenant_id)
                result.neo4j = info
            except Exception as exc:
                result.errors.append(f"neo4j:{exc}")
        return result
