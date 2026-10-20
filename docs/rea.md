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

## Agent skill

REA's user-facing skill — `reverse-engineer-anything` — is installed at
`.opencode/skills/reverse-engineer-anything/` (SKILL.md + a `references/`
folder covering native artifacts, JavaScript/Electron, Android, runtime
observation, evidence workflows, and connection recovery). opencode auto-loads
project skills from `.opencode/skills/<name>/SKILL.md`; **restart opencode** the
first time so the skill (and the `rea` MCP server) are picked up.

The skill is what tells the agent *when* to reach for REA and *how* to drive its
207 tools: it uses REA for shipped binaries/packages, decompilation, passive
runtime evidence, or version comparison — and explicitly tells the agent to use
ordinary repository analysis instead for a complete source tree. It is a faithful
copy of the upstream skill that ships in the vendored source; update it whenever
you update `vendor/rea/` (see [Updating](#updating)).

Only this one user-facing skill is installed. REA also bundles developer skills
(`rea-tool-design`, `rea-ci-tests-audit`, `rea-changelog-update`) that exist to
build REA itself — those stay under `vendor/rea/.agents/skills/` and are not
installed into the agent surface. That directory is git-ignored, which is why the
skill is copied into `.opencode/skills/` rather than referenced in place.

## Windows native controls

Some REA providers (notably the JavaScript static analyzer) load a packaged
Windows native addon that is **not** part of the source-only vendor tree. If a
tool fails with `Missing packaged Windows native file native/windows/build/manifest.json`,
restore both files from the upstream tarball of the vendored version:

```powershell
cd $env:TEMP
node <path-to-npm-cli.js> pack rea-agents@6.5.0
tar -xzf rea-agents-6.5.0.tgz
Copy-Item package\native\windows\build\* C:\Users\Ashut\Nexus\vendor\rea\native\windows\build\
```

The `.node` binary is git-ignored (`vendor/rea/native/windows/build/*.node`) —
restore it per checkout after building REA. `manifest.json` is tracked.

## Agent tests & blueprint memory

Agents validate REA and record their work through two mechanisms:

- **Health/analysis tests** — `tests/unit/test_rea_agent_tools.py` checks the
  stdio handshake, the advertised tool catalog, and one real end-to-end
  analysis with evidence. Run them before the first REA task in a session
  (`python -m pytest tests/unit/test_rea_agent_tools.py -q`); they skip with an
  actionable message when REA is not built.
- **Blueprint memory** — completed REA work must be saved as a reusable recipe
  via the nexus MCP `blueprint_save` tool (goal, steps, files, verify commands,
  tools used). Similar future work starts with `blueprint_query` and replays
  the recipe instead of re-deriving it. `resolve_task` also auto-saves a
  minimal blueprint for every completed swarm task. The operating discipline
  lives in the `nexus-blueprints` and `nexus-rea-workflow` skills.

## Updating

Replace `vendor/rea/` with a newer `rea-main` unpack, rebuild with
`python scripts/setup_rea.py`, and re-run `pytest tests/unit/test_vendor_rea.py`.
Do not patch behaviour inside `vendor/rea/` — wrap it instead.

## Environment variables

- `NEXUS_REA_NODE` — optional override giving the `node` executable used to run
  (and build) the vendored REA server. Unset by default; auto-detection is used.
