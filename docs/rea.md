# REA (Reverse Engineer Anything)

NEXUS ships a **vendored, source-only copy of REA** under `vendor/rea/` and
exposes it as a second MCP server so any connected agent (opencode, GitHub
Copilot, Antigravity) gains reverse-engineering tools: inspect native binaries,
Electron/JavaScript apps, .NET assemblies, Android APKs, firmware, websites,
network captures, and more — with evidence attached to each finding.

REA is upstream `rea-agents` v6.5.0 (MIT). See `vendor/rea/README.vendor.md` for
provenance and what is / is not committed (`node_modules` and `dist` are build
outputs and are git-ignored).

## Why vendored (not `npx`)

The tool lives *inside the repo*, so a checkout is self-contained and offline
after a one-time build. `vendor/rea/` is kept out of `src/nexus` so the hexagonal
dependency rule is untouched.

## Build it (required once)

REA is a Node.js project and its MCP entrypoint loads compiled code from
`dist/`, so it must be built before first use:

```powershell
python scripts/setup_rea.py           # npm ci + npm run compile
python scripts/setup_rea.py --doctor  # report node/npm/dist readiness only
```

Requirements: **Node.js `^22.19.0 || ^24.11.0 || >=26.0.0`** and npm. REA ships
`engine-strict=true`, so Node 23.x/25.x will refuse to install. `setup_rea.py`
locates a compatible runtime automatically — even when `node` is not on `PATH`
(nvm / standalone installs) — and prefers an engine-compatible version. To pin a
specific runtime, set `NEXUS_REA_NODE` to a `node` executable path.

## How it is wired

`scripts/rea_mcp.py` is a thin launcher that finds Node and execs
`node vendor/rea/scripts/rea.mjs mcp` with stdio inherited, mirroring the
existing `python scripts/nexus_mcp.py` convention. It is registered as the `rea`
MCP server next to `nexus` in:

- `opencode.json` → `mcp.rea`
- `.vscode/mcp.json` → `servers.rea`
- `.agent/mcp_config.json` → `mcpServers.rea`

Restart your agent after the first build (or after changing the registration) so
it picks up the new server. Verify the registration from a shell:

```powershell
python scripts/rea_mcp.py --doctor        # node + entry + dist status
python scripts/rea_mcp.py --print-command # resolved [node, rea.mjs, mcp] argv
```

## Using it

Through an MCP-capable agent, just ask — e.g. *"use REA to inspect how feature X
works in <app> and show the evidence."* The terminal CLI works too:

```bash
node vendor/rea/scripts/rea.mjs --help
node vendor/rea/scripts/rea.mjs analyze-javascript-application /path/to/app --json
```

Native deep analysis (Hopper / Ghidra / IDA) and other providers are optional and
configured separately; static JavaScript and .NET inspection need no extra engine.

## Updating

Replace `vendor/rea/` with a newer `rea-main` unpack, rebuild with
`python scripts/setup_rea.py`, and re-run `pytest tests/unit/test_vendor_rea.py`.
Do not patch behaviour inside `vendor/rea/` — wrap it instead.

## Environment variables

- `NEXUS_REA_NODE` — optional override giving the `node` executable used to run
  (and build) the vendored REA server. Unset by default; auto-detection is used.
