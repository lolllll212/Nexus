---
name: nexus-blueprints
description: Save and recall NEXUS blueprints (reusable work recipes) through the nexus MCP server. Use when completing any task or REA investigation (save a blueprint), when the user says blueprint/recipe/past project/again/last time, or before starting work that resembles something done before (query first to replay it fast).
---

# NEXUS Blueprints

A blueprint is a structured recipe — goal, steps, files, verify commands, tools —
stored in the shared content-addressable memory (`kind=blueprint`) so that any
NEXUS agent can replay similar work quickly instead of re-deriving the approach.

## Core loop

**Before starting work that resembles a past project — query first:**

- `blueprint_query` with topic keywords, e.g. `{"query": "rea native pe inspect", "k": 5}`.
  Hits come back ranked with their full recipe text (STEPS / FILES / VERIFY / TOOLS).
- If a hit matches, **adapt and replay it** — reuse its steps, files, and verify
  commands, changing only what differs. This is the fast path for "make it like
  last time" requests.

**After completing work — save what you learned:**

- `blueprint_save` with:
  - `title`: short name ("Vendor an MCP tool", "Inspect a native DLL")
  - `goal`: what the work achieved
  - `steps`: ordered, concrete steps (what you would tell a teammate to redo it)
  - `files`: files created/touched
  - `verify`: the exact commands that prove it works (tests, doctor, build)
  - `tools`: tools used, prefixed (`rea:open_binary`, `rea:inspect_pe_resources`)
  - `tags`: lowercase topic keys (`rea,native,mcp,vendor`) — these drive recall
  - `task_id`: originating task, if any
- `blueprint_latest` lists recent blueprints when you want to browse.

## Automatic saving

Every `resolve_task` already auto-saves a minimal blueprint (goal + evidence,
tagged `auto`). That is the safety net — but it is thin. **Write a rich
`blueprint_save` yourself** for anything you would want replayed well,
especially REA investigations (see the `nexus-rea-workflow` skill) and
multi-step builds.

## Behavior notes

- Content-addressed: re-saving identical content returns "already stored" — no
  duplicates accumulate.
- Blueprints are recipes, not reports: keep `steps` actionable and `verify`
  executable. If you cannot write a verify command, the work is not done yet.
- To recall everything about a domain, `blueprint_query` with the domain's tag
  words (e.g. `mcp vendor`, `rea javascript`).
