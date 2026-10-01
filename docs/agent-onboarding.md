# Agent Onboarding

You are one of three agents working on NEXUS at the same time, in three
different tools, against one shared git working tree. This page is the short
version.

## Read this first

**[AGENTS.md](../AGENTS.md) is the single source of truth.** It has the
architecture, the commands, the known quirks, the file→task mapping, and the
list of bugs already fixed. Do not memorize it and do not copy it into your own
config file — link to it, so there is exactly one copy to keep correct.

Then read **[docs/AGENT_COORDINATION.md](AGENT_COORDINATION.md)** for the
ownership table, the handoff format, and the branch strategy.

## Who you are

| Agent | Tool | Owns | Reads AGENTS.md via |
|---|---|---|---|
| opencode | terminal (CLI) | `src/nexus/application/`, `tests/eval/`, `docs/` | `instructions` in `opencode.json` |
| Antigravity | Antigravity IDE | `src/nexus/domain/`, `plugins/`, `tests/unit/` | auto-loaded, plus `.agent/rules/` |
| Copilot | GitHub Copilot (VS Code) | `src/nexus/infrastructure/`, `web/`, `config/`, `tests/integration/` | `.github/copilot-instructions.md` |

A fourth opencode window runs as the **CEO** (`.opencode/agent/ceo.md`). It
does not edit files — it delegates via `scripts/agent_comm.py`, monitors
`scripts/agent_comm.py status`, and reports to the user.

## The one rule that matters

**Never edit a file another agent owns.** If your task needs
`src/nexus/infrastructure/`, do not do it — write a HANDOFF asking for it.

## Before you touch anything

```bash
git status --short          # what has someone else already changed?
git log --oneline -5        # what did they land?
```

`git status` will show you other agents' uncommitted work. **That is expected
and it is not yours to commit.** When you commit, stage only your own paths:

```bash
git add src/nexus/application/ tests/eval/ docs/
git status --short           # confirm nothing foreign got staged
```

Then commit with attribution:

```
<scope>: <imperative summary>

Agent: opencode | Antigravity | Copilot
```

One logical unit per commit. Do not amend, force-push, or touch git config.

## Branches

```
opencode    -> work/opencode-<topic>
antigravity -> work/antigravity-<topic>
copilot     -> work/copilot-<topic>
```

Never commit to `master` unless asked. If you started on someone else's branch
(a shared working tree makes this easy), `git checkout -b` your own before
editing.

## Locking a file

If you must work on a file another agent is mid-way through, create
`.<file>.lock` next to it containing your name and a timestamp. Delete it when
done. Check for `*.lock` before editing.

## The handoff

When you cannot finish something, state it to the user in exactly this form:

```
HANDOFF
  task: <one line>
  branch: <branch name>
  files: <comma separated>
  verify: <the command you ran + result>
  notes: <anything the next agent must know>
```

## Definition of done

Everything below must be green before you say you are done:

```bash
pytest tests/ -q                  # no new failures
ruff check src/ tests/
black --check src/ tests/
mypy src/nexus/domain/ src/nexus/application/ --ignore-missing-imports
lint-imports                      # domain never imports infrastructure
```

## Talking to the others

| Mechanism | Where |
|---|---|
| Message board | `docs/HANDOFF.md` |
| Shared state | `nexus_state.json` (gitignored, local) |
| Notifications | `python scripts/notify.py --agent <you> --task "..." --status done` |
| Coordination CLI | `python scripts/agent_comm.py status` |

## Things that will waste your time if you do not know them

- **`.env` is gitignored.** `Copy-Item .env.example .env` on Windows.
- **Auth is fail-closed.** `NEXUS_API_KEYS={}` means every request 401s. Set a
  key before testing endpoints.
- **Never hit a live LLM in a test.** Use `ScriptedLLM` / `RecordingLLM` from
  `tests/fakes/` and `FakeContainer`. The only test allowed to talk to a real
  endpoint is the nightly `python -m nexus eval`.
- **Qwen 3.5 is a reasoning model** — its output arrives in
  `reasoning_content`; `content` is empty until it finishes. Needs
  `max_tokens` ≥ 200.
- **PowerShell, not bash.** `curl` is `Invoke-WebRequest`. No `&&` chaining.
- **The DI container is the only place adapters are chosen.** If you need to
  swap an implementation, edit `infrastructure/di/container.py` — not the use
  case, and never by adding an `import` from `domain/` into the outside world.
- **`docs/architecture-map.md` is verified by a test.** If you add a port or
  change a binding, update that page or CI fails.

## Your first task

1. Read `AGENTS.md` and `docs/AGENT_COORDINATION.md`.
2. `git status --short` — see who is mid-flight.
3. Take a task **inside your ownership area**. If the request is out of area,
   write a HANDOFF instead of editing.
4. Ship it with the DoD checklist above and a HANDOFF block.
