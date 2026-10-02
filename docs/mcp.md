# MCP Server

NEXUS speaks **standard MCP (JSON-RPC 2.0 over stdio, protocolVersion
`2024-11-05`)** — any MCP client (VS Code Copilot, Antigravity, opencode)
connects natively with zero copy-paste. The server is `scripts/nexus_mcp.py`,
and it is wired in `.vscode/mcp.json` + `.agent/mcp_config.json` (and
`opencode.json`) as `python scripts/nexus_mcp.py`.

## What it gives an MCP client

### Resources (read)

- `nexus://tasks/pending` — the ticket queue
- `nexus://state/current` — git + agents
- `nexus://board/plans` — the plan-first gate's drafts
- `nexus://board/consensus` — consensus proposals and verdicts
- `nexus://memory/recent` — the content-addressable agent memory

### Tools (the blackboard pattern)

18 tools: `next_task(agent_id)` — capability-based auto-pick;
`claim_task`, `resolve_task(evidence)`, `heartbeat`, `progress`, `ask_ceo`,
`check_inbox`; the plan-first gate as tools —
`plan_create` / `plan_begin` / `plan_step` / `plan_finish` / `plan_check_file`;
`memory_put` / `memory_query`; `consensus_propose` / `consensus_review` /
`consensus_vote`; and `git_status`.

## CRITICAL: stdout is the protocol channel

Every reuse of an `agent_comm` command function inside the server must be
wrapped in `contextlib.redirect_stdout` — a bare `print` corrupts the JSON-RPC
stream and the client sees garbage. Reuse the real APIs instead of shelling
out: `PlanningBoard.list_plans()`, `AgentMemoryStore.latest(n=)`,
`store.put()` (returns `(chunk, created)`), `board.begin/finish/complete_step`
(return `(plan, error)`), `cp.review(...)`, `cp.vote(...)`.

Malformed JSON, unknown methods and bad arguments return JSON-RPC errors
(`-32700`, `-32601`, `-32602`) — the server never crashes mid-stream.

## Hermetic tests

`tests/unit/test_nexus_mcp.py` — a subprocess round-trip covering the
handshake, the full tools list, resources, `next_task`, and the three error
codes, plus unit tests for the JSON-RPC handler, the plan lifecycle and the
memory/consensus tools. Verified end-to-end: the handshake returns
protocolVersion `2024-11-05` and `tools/list` returns all 18 tools.

## Enabling it

Already wired in all three apps — VS Code Copilot (`.vscode/mcp.json`),
Antigravity (`.agent/mcp_config.json`) and opencode (`opencode.json`), each
pointing at `python scripts/nexus_mcp.py`. If a client shows no NEXUS tools,
check the server is reachable and that no other process is holding stdout.
