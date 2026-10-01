# Self-Evolution - Dynamic Tool Generation

## The Capability

Standard agents have fixed tools. NEXUS **builds its own**.

When the ReAct loop meets a problem no tool solves, the brain can:

```
GenerateToolUseCase
  1. Analyze problem -> ToolSpecRequest (name, description, examples)
  2. LLM writes the Python source (a `solve(input_data) -> dict` function)
  3. Test it in the Sandbox against its own example inputs
  4. Deploy it through the DeploymentProvider (Local FastAPI; Railway/Vercel next)
  5. Register it in the ToolRegistry -> permanently part of its toolkit
```

## Infrastructure Control

`DeploymentProvider` is a port. The container picks the adapter from
`NEXUS_DEPLOY_PLATFORM`:

| `NEXUS_DEPLOY_PLATFORM` | Adapter |
|---|---|
| unset / anything else | `LocalDeployer` |
| `railway` | `RailwayDeployer` (needs a token + project id) |
| `vercel` | `VercelDeployer` (needs a token + team id) |

The brain can grow its own compute as its needs grow, without the application
layer knowing what is on the other side.

## Validation: Why a Tool Is Not "Generated"

`GenerateToolUseCase.execute()` only registers a tool if the generated code
actually ran. It does **not** just check `error is None` - it compares the real
output against `expected_outputs` from the spec. A `solve()` that returns `None`,
raises, or returns the wrong shape fails validation and the tool is discarded
rather than registered broken. This is in `AGENTS.md` under "Critical Bugs
Fixed"; the bug was that a tool could be marked `READY` having never produced a
correct result.

Generated tools run through the `Sandbox` port, so on the default backend they
execute inside Docker. Set `NEXUS_SANDBOX_BACKEND=subprocess` to fall back to a
subprocess on trusted hosts.

## Self-Healing

`SelfHealUseCase` runs after each dream cycle. Any self-generated tool whose
`success_rate` drops below `FAILURE_THRESHOLD = 0.4` is:

1. Deprecated.
2. Regenerated with fresh context (the description + known failures).
3. Re-tested and re-registered.

Self-generated tools with a `use_count` of 0 are skipped entirely - a tool that
has never been called has no evidence of being broken.

Every regeneration passes through the `AutonomyPolicy` guardrail:

- the per-tenant hourly budget is checked,
- regeneration requires approval (`tool_selfheal` is allowlisted by default via
  `NEXUS_AUTONOMY_ALLOWLIST`),
- and each attempt is written to the tenant audit log (`GET /v1/goals/audit`).

A denied regeneration leaves the tool `DEPRECATED` and records the reason in
`SelfHealResult.blocked` / `.denied_reason` - it does not silently retry.

## Lifecycle

```
GENERATING -> TESTING -> (READY | DEPLOYED) -> DEPRECATED -> (regenerated | garbage)
```

`ToolStatus` lives in `domain/entities/tool.py`. `Tool` also carries
`use_count` and `success_rate`, which are what phase 2 of self-healing reads.

## Triggering Generation

```bash
curl -X POST http://localhost:8000/v1/tools/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $NEXUS_API_KEY" \
  -d '{"name":"csv_summarizer",
       "problem_statement":"Read a CSV and summarize each column'"'"'s stats",
       "requirements":["pandas"]}'
```

`NEXUS_QUOTA_TOOL_GEN_PER_DAY` caps how many generations a tenant can start per
day (`0` = unlimited, the default). The rate-limited route and the daily quota
are independent guards: the sliding window protects the endpoint, the quota
protects the tenant's tool budget over a full day.

## Evaluating the Evolution Loop

The golden set in `src/nexus/eval/harness.py` has a `self_evolution` category
(2 of 16 cases). Those cases check the *shape* of the behaviour - the agent
inspects existing tools, then produces a named, working new one - rather than
pinning specific tool names, so a model that evolves along a different path is
not punished for it.

```bash
python -m nexus eval --output eval-report --min-pass-rate 0.8
```

See `tests/eval/test_eval_gate.py` for how the gate is verified without a live
endpoint.

## See also

- [Dreaming Pipeline](dreaming.md) - when self-healing runs
- [Autonomous Goals](autonomous-goals.md) - the budget/approval/audit guardrail
- [Architecture Map](architecture-map.md) - the `DeploymentProvider` and `Sandbox` ports
