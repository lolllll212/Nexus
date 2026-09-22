# Backup & Disaster Recovery — NEXUS

Memories are the product. If Qdrant or Neo4j is lost, the brain is lobotomised.
This doc is the runbook.

## What is backed up

| Store | What | How | Frequency |
|-------|------|-----|-----------|
| **Qdrant** (vector memory) | Per-collection snapshots (`nexus_memory`, `nexus_memory_{tenant}`) | `POST /collections/{name}/snapshots` via `QdrantBackup` | Nightly (after `dream`) + on demand |
| **Neo4j** (concept graph) | Concept nodes + `CONNECTS` edges | Cypher export to JSONL via `Neo4jBackup.export()` | Nightly (after `dream`) + on demand |
| Retention | Old Qdrant snapshots pruned | `BackupManager(…, retain_snapshots=7)` keeps newest 7 | Automatic |

In `memory` backend (`NEXUS_INFRA_BACKEND=memory`) there is nothing to snapshot;
`BackupManager` no-ops when no adapters are injected.

## Running a backup

```bash
# Live infra (reads NEXUS_* env / .env for Qdrant/Neo4j hosts)
python -m nexus backup
python -m nexus backup --output-dir /data/backups --retain 14 --tenant acme

# Or via the installed console script
nexus backup --output-dir backups --retain 7
```

Output `backups/`:

```
backups/
  neo4j-default-2026-09-22T03-10-00.jsonl   # one JSON object per line (_kind=node|rel)
  # Qdrant snapshots live inside Qdrant; BackupManager only records their names.
```

`nexus backup` prints JSON to stdout:

```json
{
  "timestamp": "2026-09-22T03:10:00.123456",
  "qdrant_snapshots": [{"name": "snap-...", "creation_time": "..."}],
  "qdrant_pruned": ["snap-old-..."],
  "neo4j": {"path": "backups/neo4j-default-....jsonl", "nodes": 142, "relationships": 89},
  "errors": []
}
```

Non-zero exit if `errors` is non-empty and no snapshot/dump was produced.

## Docker / cron

`docker-compose.yml` runs a `nexus-worker` (Celery beat schedules `dream` at 03:00).
Add a sibling service or host cron:

```yaml
  nexus-backup:
    build: .
    entrypoint: ["python", "-m", "nexus", "backup", "--output-dir", "/backups"]
    volumes: ["/data/backups:/backups:rw"]
    environment: *nexus-env
```

Or host cron:

```
0 3 * * *  cd /opt/nexus && NEXUS_INFRA_BACKEND=external python -m nexus backup --output-dir /data/backups >>/var/log/nexus-backup.log 2>&1
```

## Restore (DR)

### Qdrant — point-in-time

```bash
# list snapshots for a collection
curl http://qdrant:6333/collections/nexus_memory/snapshots | jq .

# download one (D — needs Qdrant snapshot recovery API)
curl -o /tmp/snap.snapshot http://qdrant:6333/collections/nexus_memory/snapshots/<name>

# recover into a fresh Qdrant (or same host after wipe)
curl -X POST http://qdrant:6333/collections/nexus_memory/snapshots/recover \
  -H 'Content-Type: application/json' \
  -d '{"location": "http://backup-host/snap.snapshot"}'

# Via Python (uses Qdrant HTTP client in future — today restore is manual via HTTP)
```

For per-tenant collections repeat for `nexus_memory_{tenant}`.

Verification:

```bash
curl http://qdrant:6333/collections/nexus_memory | jq .result.points_count
```

### Neo4j — graph

```bash
# JSONL dump produced by BackupManager; replay with the same tool
python - << 'PY'
import asyncio
from nexus.infrastructure.backup import Neo4jBackup
async def main():
    nb = Neo4jBackup(uri="bolt://neo4j:7687", user="neo4j", password="secret")
    info = await nb.import_dump("backups/neo4j-default-2026-09-22T03-10-00.jsonl", tenant_id="default")
    print(info)
asyncio.run(main())
PY
```

For a hard disaster (volume lost), start a fresh Neo4j, then `import_dump` the latest
`backups/neo4j-*.jsonl`. For online hot backups prefer `neo4j-admin database backup`
on the volume; the JSONL export is the portable/app-level fallback and is exercised
by `tests/unit/test_backup.py`.

Verification:

```cypher
MATCH (c:Concept {tenant:"default"}) RETURN count(c);
MATCH (:Concept {tenant:"default"})-[r:CONNECTS {tenant:"default"}]->(:Concept) RETURN count(r);
```

## RPO / RTO targets

* **RPO** ≤ 24h (nightly snapshots). Reduce to 6h by scheduling `nexus backup` every 6h.
* **RTO** ≤ 1h (Qdrant snapshot recover ~ minutes; Neo4j JSONL replay ~ minutes for
  <100k concepts). Large graphs — use `neo4j-admin` volume snapshots instead.

## Retention & pruning

`BackupManager.prune()` sorts by `creation_time` and deletes the oldest beyond `retain`.
Qdrant deletes are `DELETE /collections/{name}/snapshots/{snap}`. Local JSONL files
are not auto-pruned — rotate `backups/*.jsonl` with `logrotate` or S3 lifecycle.

## Env

| Var | Default | Meaning |
|-----|---------|---------|
| `QDRANT_HOST` / `QDRANT_PORT` | `localhost:6333` | Qdrant for snapshots |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | `bolt://localhost:7687` | Neo4j for graph dump |
| `NEXUS_TENANTS` | `` | Tenants to back up (comma-separated) |

## Testing DR without prod

```bash
NEXUS_INFRA_BACKEND=memory python -m pytest tests/unit/test_backup.py -v
# Uses FakeQdrantClient + FakeNeo4jDriver — no Docker needed
python -m nexus backup --output-dir /tmp/bkp  # exercises the same path with live infra
```

See `src/nexus/infrastructure/backup/` (`QdrantBackup`, `Neo4jBackup`, `BackupManager`)
and `tests/unit/test_backup.py` for the contract.
