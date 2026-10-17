# Vendored: REA — Reverse Engineer Anything

This directory is a **vendored, source-only** copy of REA, the reverse-engineering
MCP server + CLI. It is not first-party NEXUS code and is kept out of `src/nexus`
so the hexagonal dependency rule (domain never imports infrastructure) is
untouched.

| Field    | Value |
| -------- | ----- |
| Upstream | https://github.com/morluto/rea |
| Package  | `rea-agents` v6.5.0 |
| License  | MIT (see `LICENSE`) |
| Source   | unpacked from `rea-main.zip` |
| Runtime  | Node.js `^22.19.0 || ^24.11.0 || >=26.0.0` + npm |

## What is committed

The full source tree (TypeScript `src/`, Python/Java/Swift `bridge/`, `tests/`,
`docs/`, `scripts/`, website, build configs). **Build and install outputs are
not committed** — they are ignored here and by the repo-root `.gitignore`:

- `node_modules/` — installed via `npm ci` (see below)
- `dist/` — compiled from `src/` via `npm run compile`
- `.cache/`, `.turbo/`, `.stryker-tmp/`, coverage/report outputs

## Build it (required before first use)

REA's entrypoint (`scripts/rea.mjs`) loads compiled code from `dist/`, so the
server will not run until it is built. Use the repo helper, which locates a
usable Node runtime even when `node` is not on `PATH`:

```powershell
python scripts/setup_rea.py          # npm ci + npm run compile in vendor/rea
python scripts/setup_rea.py --doctor # report node/npm/dist status only
```

Or build manually with a Node/npm on `PATH`:

```bash
cd vendor/rea
npm ci
npm run compile
```

## How NEXUS uses it

NEXUS registers REA as a **second stdio MCP server** next to `nexus` in
`opencode.json`, `.vscode/mcp.json` and `.agent/mcp_config.json`:

```jsonc
"rea": { "type": "local", "command": ["python", "scripts/rea_mcp.py"] }
```

`scripts/rea_mcp.py` is a thin launcher that finds a Node runtime and execs
`node vendor/rea/scripts/rea.mjs mcp` (stdio JSON-RPC). This matches the existing
`python scripts/nexus_mcp.py` pattern and keeps the command portable across
machines where `node` lives in different places.

## Updating

Replace the contents of this directory with a newer `rea-main` unpack, rebuild
with `python scripts/setup_rea.py`, and re-run the test suite. Do not edit files
here to fix NEXUS behaviour — wrap them instead (`scripts/rea_mcp.py`).

See `docs/rea.md` for the operator guide.
