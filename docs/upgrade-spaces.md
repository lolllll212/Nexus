# Upgrade Spaces

The multi-agent upgrade plan: ten spaces that turn NEXUS from a system with
coordination scripts into one that operates autonomously around the clock. The
plan of record is [`plan-upgrade-spaces.json`](plan-upgrade-spaces.json) — the
CEO dispatched it as 11 subtasks (task-027..task-037) with no scope overlap, and
every acceptance criterion includes the rule learned during the dispatch: **new
`NEXUS_*` vars land documented in the same commit as the code that reads them**
(the [env-var guard](../tests/eval/test_docs_env_vars.py) enforces it).

Status below is the measured state, not the plan's intent — this page is
updated as each space lands on master. Nine of ten spaces are landed on master
(verified in the code: `src/nexus/domain/crdt/`, `LearnedRouter` +
`train_from_route_log`, bandit in the consensus reviewers, the swarm dashboard,
the bridge token auth, hybrid memory scoring, `docker-compose.loop.yml`); only
Space 9 (OTel spans for the heal and consensus loops) is not wired yet — the
`OTELTracer` adapter exists but nothing in `heal_loop.py` or the consensus
protocol emits spans.

| Space | What it is | Priority | Status | Owner |
|---|---|---|---|---|
| 1 | Semantic memory for coordination (hybrid cosine + TF-IDF) | high | **landed** | Xenom |
| 2 | Full overnight autonomy daemon | high | **landed** | Astra |
| 3 | Swarm state as real CRDTs (G-Counter, LWW-Register, OR-Set) | high | **landed** | Tron |
| 4 | Learned model router (trained on route_log + eval feedback) | medium | **landed** | Xenom |
| 5 | Automated first-pass consensus reviewers | medium | **landed** | Xenom |
| 6 | Real-time swarm dashboard (Vite over the WebSocket bridge) | medium | **landed** | Xenom |
| 7 | Bridge security hardening (shared-token auth, op allowlist) | high | **landed** | Xenom |
| 8 | Offline LoRA fine-tuning on approved work | medium | **landed** | Astra |
| 9 | Agent-layer observability (OTel spans, Prometheus counters) | low | not landed | Xenom |
| 10 | Containerized full loop (docker-compose profile) | low | **landed** | Xenom |

## Space 2 — Overnight autonomy daemon (landed)

One loop with safety gates, not a free-running script:
bridge events + task queue -> heal -> consensus -> apply (CEO-approved only) ->
verify -> commit -> dream.

- **Core:** `src/nexus/application/autonomy/overnight_daemon.py` — injected
  callables, no infrastructure imports.
- **Wiring:** `scripts/overnight_daemon.py` — composes `heal_loop`, the
  consensus protocol, pytest verification, git commits, and a dream cycle.
- **Kill switch:** `touch .nexus_overnight_stop` (or `NEXUS_DAEMON_KILL_SWITCH=1`)
  stops the daemon before any work and again after each item.
- **Blackouts:** `NEXUS_DAEMON_BLACKOUTS="09:00-17:00,22:00-06:00"` — start
  inclusive, end exclusive, wrap-around-midnight windows supported.
- **Budget:** pauses when the agent's daily token budget is spent; over-budget
  traffic also degrades to the local tier.
- **Consensus:** no patch applies without an approved verdict — the daemon
  filters statuses AND `scripts/consensus.py apply` refuses non-approved ones,
  so a refactor of either half must leave one intact. A patch that applies but
  breaks the verify gates is reverse-applied and never committed.
- **Tests:** `tests/eval/test_overnight_daemon.py` (15 tests).

Run it:

```bash
python scripts/overnight_daemon.py --max-cycles 50
python scripts/overnight_daemon.py --dry-run   # no LLM calls, no applies
```

## Space 8 — Offline LoRA fine-tuning (landed)

Trains a local model on work the swarm has already judged: consensus-approved
patches become `chosen`, rejected ones `rejected` (a DPO-style pair). The
golden-set eval gates the swap: a candidate whose pass rate regresses is
blocked, never swapped.

- **Core:** `src/nexus/application/training/lora_pipeline.py` — pure logic;
  the GPU trainer is an adapter concern (injected `train` callable), so the
  core never touches torch/peft.
- **Pairs:** `pairs_from_proposals` reads ONLY approved/rejected proposals,
  matched by title slug — an in_review or draft patch never forms a training
  pair, because training on unjudged work teaches the model work that may be
  wrong.
- **Wiring:** `python -m nexus.training.cli lora` — writes the JSONL
  preference-pair dataset, evaluates against the golden set (reads an existing
  `eval-report.json`; `--run-eval` runs the real eval), and gates the swap.
  The local-tier swap itself is a follow-up seam (`swap_model`).

Run it:

```bash
python -m nexus.training.cli lora --baseline 0.8 --min-pass-rate 0.6
python -m nexus.training.cli lora --run-eval   # evaluate now, not from a report
```

## The remaining space

**Space 9** — not landed. The `OTELTracer` adapter exists (the pre-existing
observability adapter, enabled by `NEXUS_OTEL_ENABLED=true`), but nothing in
`heal_loop.py` or the consensus protocol emits spans for heal iterations and
consensus verdicts, and no Prometheus counters are exported. Owner: Xenom,
dispatch in [`plan-upgrade-spaces.json`](plan-upgrade-spaces.json). This page's
status table is updated as it lands, and its env vars must arrive documented in
the same commit as the code that reads them (the
[ops table](architecture-map.md) + the
[env-var guard](../tests/eval/test_docs_env_vars.py)).
