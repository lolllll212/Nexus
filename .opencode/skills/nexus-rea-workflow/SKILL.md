---
name: nexus-rea-workflow
description: Run REA reverse-engineering investigations in NEXUS the standard way - health check first, analyze with evidence, always save a blueprint when done. Use when asked to use REA, or when inspecting/decompiling binaries, packages, Electron apps, APKs, firmware, or browser pages inside the Nexus repo.
---

# REA Workflow in NEXUS

The vendored REA server (`rea`, 207 tools, MCP) is the reverse-engineering
engine. This skill is the operating discipline around it; the
`reverse-engineer-anything` skill covers REA's own tool semantics.

## 1. Health check (before the first REA task in a session)

```bash
python -m pytest tests/unit/test_rea_agent_tools.py -q   # handshake + tools + real analysis
python scripts/rea_mcp.py --doctor                        # node + entry + dist status
```

If the tests skip with "REA not built", run `python scripts/setup_rea.py` and
retry. If REA tools are already available in-session and working, skip the
check and go straight to the target.

## 2. Investigate with evidence

Use the REA MCP tools directly (`open_binary` → analyze → `close_binary`).
Keep every evidence id (`ev_...`) in your notes; findings without evidence ids
are opinions. See the `reverse-engineer-anything` skill for tool selection and
the connection-and-recovery reference when a provider is missing.

## 3. Always finish with a blueprint

When the investigation or build completes, save the recipe:

```
blueprint_save {
  "agent_id": "<you>",
  "title": "<what was done>",
  "goal": "<the analyst question answered>",
  "steps": ["...concrete redo steps..."],
  "files": ["...touched/created..."],
  "verify": ["python -m pytest tests/unit/test_rea_agent_tools.py -q"],
  "tools": ["rea:open_binary", "rea:inspect_pe_resources"],
  "tags": "rea,<domain>,<topic>"
}
```

`<domain>` is one of `native`, `managed`, `javascript`, `android`, `firmware`,
`browser`, `runtime`. This is what makes the next similar request a five-minute
job instead of an hour: `blueprint_query` returns your steps, files, and verify
commands ready to replay.

## 4. Then close out

- Export needed evidence (`export_evidence_bundle`) if the findings must outlive
  the session, then `close_binary`.
- If the work came from a swarm task, `resolve_task` with the evidence — the
  auto-blueprint hook records it too, but your rich blueprint from step 3 is
  the one that gets replayed.

## Quick reference

| Need | Tool |
| --- | --- |
| Is REA alive? | `pytest tests/unit/test_rea_agent_tools.py -q` |
| Similar past work? | `blueprint_query` |
| Record the recipe | `blueprint_save` |
| Browse recipes | `blueprint_latest` |
| REA tool semantics | `reverse-engineer-anything` skill |
