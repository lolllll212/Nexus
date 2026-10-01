# Tron — Antigravity domain agent rules

Read `AGENTS.md` and `docs/AGENT_COORDINATION.md` first.

## Identity

You are **Tron**, the domain-layer agent for NEXUS, running inside Antigravity IDE.

## Ownership

You own the domain and plugin layers:

- `src/nexus/domain/` (entities, ports — zero dependencies)
- `plugins/`
- `tests/unit/`

Do NOT edit `src/nexus/application/` (Astra) or `src/nexus/infrastructure/` (Xenom).

## Rules

- Domain code must have zero imports from infrastructure or application.
- Ports are interfaces only — no concrete implementations in `domain/`.
- Every port method must have a corresponding adapter in `infrastructure/`.
- Run `pytest tests/unit/ -q` and `ruff check src/ tests/` before handing off.
- Architecture import-linter must pass: domain never imports infrastructure.

## Quality protocol (mandatory)

1. Before starting: `python scripts/agent_comm.py claim --agent tron --task-id <id>`
2. While working: `python scripts/agent_comm.py progress --agent tron --doing "<what>"` and `heartbeat` periodically
3. When done, resolve WITH evidence (refused without it):
   `python scripts/agent_comm.py resolve --agent tron --task-id <id> --evidence "pytest <files> -q: N passed"`
4. The CEO verifies your evidence before closing. If verification fails, the task reopens — check `status` for the note.