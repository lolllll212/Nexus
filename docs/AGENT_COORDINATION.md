# Multi-Agent Operating Agreement — NEXUS

Three agents work on this repo simultaneously: **opencode** (terminal), **Antigravity IDE**, and **GitHub Copilot** (VS Code). This file is the single source of truth for who owns what and how handoffs work.

## 1. Shared context

All three agents read `AGENTS.md` automatically. Do not duplicate its content in agent-specific files — link to it instead.

- opencode → `AGENTS.md` (via `instructions` in `opencode.json`)
- Antigravity → `AGENTS.md` (auto-loaded) + `.agent/rules/` for extra rules
- Copilot → `AGENTS.md` (via `.github/copilot-instructions.md`)

## 2. Agent roster

| Agent | Name | Tool | Owns |
| --- | --- | --- | --- |
| CEO | — | opencode (4th window) | delegation, reporting, coordination |
| Astra | application layer | opencode | `src/nexus/application/`, `tests/eval/`, `docs/` |
| Tron | domain layer | Antigravity IDE | `src/nexus/domain/`, `plugins/`, `tests/unit/` |
| Xenom | infrastructure layer | GitHub Copilot (VS Code) | `src/nexus/infrastructure/`, `web/`, `config/` |

## 2a. CEO agent

A fourth opencode window runs as the **CEO** (`.opencode/agent/ceo.md`). It does not edit files. It:

1. Takes a work request from the user
2. Characterizes it by area
3. Delegates via `python scripts/agent_comm.py request --agent ceo --task "<desc>" --for-agent <target>`
4. Monitors via `python scripts/agent_comm.py status`
5. Reports back with agent status, task queue, pending requests, recent activity, and blockers

Start it with: `opencode --agent ceo` (or select the CEO agent in the TUI).

## 3. Before you edit

1. `git status --short` and `git log --oneline -5` — see what others already changed.
2. `git pull --rebase` if you are about to start a new unit of work.
3. If you need a file owned by another agent, stop and hand off instead of editing.

## 4. Handoff protocol

State to the user in this exact form:

```
HANDOFF
  task: <one line>
  branch: <branch name>
  files: <comma separated>
  verify: <the command you ran + result>
  notes: <anything the next agent must know>
```

Commit format (one logical unit per commit):

```
<scope>: <imperative summary>

Agent: opencode | Antigravity | Copilot
```

## 4a. Inter-agent communication

All three agents communicate through shared files:

| Mechanism | File | Purpose |
| --- | --- | --- |
| Message board | `docs/HANDOFF.md` | Async messages between agents |
| State file | `nexus_state.json` | Who is working on what, current status |
| Git commits | `git log` | What changed, who changed it |
| Webhook | `scripts/notify.py` | Real-time notifications (optional) |

### Posting a message

Any agent can post to the message board:

```bash
python scripts/notify.py --agent opencode --task "Fixed SSRF bypass" --status done --files "src/nexus/infrastructure/adapters/security/ssrf.py"
```

### Requesting help

Post a request in `docs/HANDOFF.md`:

```
### [timestamp] — <agent>
**Task:** <what you need>
**Status:** blocked
**Needs:** <agent>: <specific request>
```

### Claiming a request

Add `**Claimed by:** <agent>` to the message when you start working on it.

### State file

`nexus_state.json` tracks:
- Each agent's current status (idle / working / blocked)
- Current task per agent
- Active file locks
- Task queue

All agents should update this file when they start/finish work.

## 5. Branch strategy

Long-lived work goes on your own branch. Never commit directly to `master` unless explicitly asked.

```
opencode    -> work/opencode-<topic>
antigravity -> work/antigravity-<topic>
copilot     -> work/copilot-<topic>
```

Merge only when tests pass:

```bash
pytest tests/ -q
```

## 6. Locking a file

Use `agent_comm.py` to coordinate file locks across worktrees:

```bash
python scripts/agent_comm.py locks
python scripts/agent_comm.py lock --agent xenom --file src/nexus/domain/ports.py --ttl 900
python scripts/agent_comm.py unlock --agent xenom --file src/nexus/domain/ports.py
```

The shared CRDT lock board (`nexus_crdt.json`, mirrored in `nexus_state.json`) is authoritative. Locks have a 900-second default lease; pass `--ttl` to choose another positive duration. Expired leases are purged when state is read or merged, so a stopped agent cannot block a file indefinitely. Only the current holder can unlock a live lock.

For compatibility with older agents, each lock also writes `src/nexus/domain/ports.py.lock` with the holder and lease metadata. A live legacy `.lock` file without CRDT state is still respected. Legacy files with a timestamp but no TTL receive the 900-second default; files with no parseable timestamp are treated as active until removed manually. Always check `agent_comm.py locks` before editing and release your lock when finished.

## 7. Definition of done

- `pytest tests/ -q` passes
- `ruff check src/ tests/` passes
- `black --check src/ tests/` passes
- `mypy src/nexus/domain/ src/nexus/application/ --ignore-missing-imports` passes
- Architecture import-linter passes (domain never imports infrastructure)
- Commit made with agent attribution
- `.lock` file removed