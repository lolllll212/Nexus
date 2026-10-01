# Backup & Disaster Recovery

## What Actually Needs Backing Up

NEXUS has four pieces of state. Only two of them are irreplaceable.

| State | Store | In `memory` mode | Backup story |
|---|---|---|---|
| **Memories (vectors)** | Qdrant collection `nexus_memory` | in-process dict | Qdrant collection snapshots |
| **Concept graph** | Neo4j `:Concept` / `:CONNECTS` | in-process dict | portable Cypher JSONL dump |
| **Short-term memory** | Redis | in-process dict | disposable, TTL-based |
| **Rate limits / autonomy budget** | Redis | in-process dict | disposable, resets on restart |

Short-term memory and rate limits are caches with a TTL. Losing them costs you
a warm cache, not data, so they are deliberately not backed up. Redis
persistence (AOF/RDB) is still worth having in production, but it is not a
DR concern.

Under `NEXUS_INFRA_BACKEND=memory` there is nothing to back up at all - the
process is the database. See [architecture-map.md](architecture-map.md).

## Tenant Isolation

Qdrant collections are **per tenant**: `nexus_memory` for `default`,
`nexus_memory_{tenant_id}` otherwise. The backup command mirrors the same
naming rule, so backing up tenant `acme` snapshots `nexus_memory_acme` and dumps
only `:Concept {tenant: 'acme'}`.

Every `Concept` node carries a `tenant` property and every `CONNECTS`
relationship carries one too. That is not decoration - a dump that filtered
only on nodes would happily re-link two tenants' concepts on restore.

## `nexus backup`

```bash
nexus backup [--output-dir backups] [--retain 7] [--tenant t1,t2]
```

| Flag | Default | Meaning |
|---|---|---|
| `--output-dir` | `backups` | Where the Neo4j JSONL dumps land. |
| `--retain` | `7` | Keep the newest N Qdrant snapshots per collection; delete the rest. |
| `--tenant` | `default` | Comma-separated tenants. One pass per tenant. |

It prints a JSON summary to stdout and **exits 1 only if everything failed** -
partial success (e.g. Qdrant up, Neo4j down) still exits 0, with the failures
listed in `errors`. That is deliberate: a monitoring check that alarms on every
partial backup trains you to ignore it.

```json
{
  "timestamp": "2026-10-01T03:00:00+00:00",
  "qdrant_snapshots": [{"name": "snap-...", "creation_time": "...", "size": 1048576}],
  "qdrant_pruned": ["snap-old-1"],
  "neo4j": {"path": "backups/neo4j-acme-2026-10-01T03-00-00+00-00.jsonl",
            "nodes": 412, "relationships": 1287},
  "errors": []
}
```

In `memory` mode the command wires no Qdrant and no Neo4j client, so it exits 0
with empty results. Useful as a smoke test, useless as a backup - it is not
trying to mislead you, it just has nothing to copy.

## The Pieces

`infrastructure/backup/`:

| Module | Class | Responsibility |
|---|---|---|
| `qdrant_backup.py` | `QdrantBackup` | `create_snapshot`, `list_snapshots`, `delete_snapshot`, `prune` |
| `neo4j_backup.py` | `Neo4jBackup` | `export` (Cypher -> JSONL), `import_dump` (JSONL -> Cypher `MERGE`) |
| `manager.py` | `BackupManager` | orchestrates both, applies retention, returns `BackupResult` |

`BackupResult` is a dataclass of `timestamp`, `qdrant_snapshots`,
`qdrant_pruned`, `neo4j`, `errors`. The manager **collects errors instead of
raising**: one dead store must not prevent the other from being backed up. Every
store is individually `try`/`except`-wrapped.

Both adapters take an injectable client / driver, which is how the DR path is
tested without a live Qdrant or Neo4j.

### Qdrant: snapshots, not dumps

`QdrantBackup` is a thin wrapper over the Qdrant HTTP snapshot API rather than a
volume copy, so it works against a managed cluster with no filesystem access:

```
POST   /collections/{name}/snapshots          create
GET    /collections/{name}/snapshots          list
DELETE /collections/{name}/snapshots/{snap}   delete
POST   /collections/{name}/snapshots/recover  restore
```

`prune(collection, retain)` sorts by `creation_time` ascending and deletes
everything before the newest `retain`. Retention is applied immediately after
each snapshot, so an unattended nightly run cannot fill the disk.

### Neo4j: a portable JSONL dump

The module docstring is explicit about why: production Neo4j should really use
`neo4j-admin database dump` (or `backup` for an online database) on the volume,
which needs shell access the app does not have. `Neo4jBackup.export` is the
portable alternative - pure Cypher over the driver - which is enough to verify
DR in tests and offline, and to get the data *out* when the volume is already
gone. Do not treat it as a substitute for a volume-level dump at scale.

Format: one JSON object per line, discriminated by `_kind`.

```json
{"_kind": "node","id":"c-1","label":"Deploy pipeline","type":"topic"}
{"_kind": "rel","src":"c-1","dst":"c-2","type":"semantic","weight":2.5}
```

`import_dump` replays it with `MERGE` on `(id, tenant)`, so a restore is
idempotent - running it twice does not duplicate the graph. Relationship
`weight` and `type` are `SET` on match, so a restore also repairs a graph whose
edges drifted.

Dump filenames are `neo4j-{tenant}-{timestamp}.jsonl` with `:` replaced by `-`,
so they are safe on Windows and sort chronologically.

## Suggested Schedule

```bash
# nightly, 03:15 - after the 03:00 dream cycle settles
15 3 * * *  cd /srv/nexus && nexus backup --retain 7 >> /var/log/nexus/backup.log 2>&1

# copy the Neo4j JSONL + Qdrant volume off-host; snapshots are not offsite
0 4 * * *  rclone sync /srv/nexus/backups s3:nexus-dr/
```

Off-host copy is a separate step on purpose. Qdrant snapshots live in the
cluster's storage, so a snapshot that saves you from a bad `prune` will not save
you from losing the node. Verify the off-host copy, not the snapshot's existence.

## Restore Runbook

1. **Stop writes.** Bring the API and workers down so nothing writes mid-restore.
2. **Restore the graph first**, then the vectors: concepts are the index, memories
   are the payload, and re-embedding is expensive enough that you want it once.
   ```python
   await Neo4jBackup(uri=..., user=..., password=...).import_dump(
       "backups/neo4j-acme-<ts>.jsonl", tenant_id="acme"
   )
   ```
   Confirm `nodes` / `relationships` match the `neo4j` block of the backup JSON.
3. **Restore vectors.**
   ```
   POST /collections/nexus_memory_acme/snapshots/recover  {"snapshot": "<name>"}
   ```
4. **Bring the API up**, then the workers. Check `GET /v1/system/dreams` and one
   real chat turn before declaring victory - an empty graph will answer fine and
   remember nothing, which is the failure mode you will not catch with a health
   check.
5. **Record the drill.** A backup you have never restored is a hypothesis.

## Testing the Backup Path

The adapters take an injected HTTP client / Neo4j driver, so the DR path is
covered without live infrastructure:

```bash
pytest tests/unit -k backup -q
```

Verify a restore by round-tripping a dump: export, wipe, import, and assert the
node and relationship counts match the export.

## See also

- [Architecture Map](architecture-map.md) - which adapters are live per `NEXUS_INFRA_BACKEND`
- [Memory System](memory.md) - what is actually in those two stores
- [Dual-Loop Architecture](dual-loop.md) - the 3 AM dream cycle that runs just before backup
