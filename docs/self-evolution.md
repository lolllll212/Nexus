# Self-Evolution — Dynamic Tool Generation

## The Capability

Standard agents have fixed tools. NEXUS **builds its own**.

When the ReAct loop meets a problem no tool solves, the brain can:

```
GenerateToolUseCase
  ├─ 1. Analyze problem → ToolSpecRequest (name, description, examples)
  ├─ 2. LLM writes the Python source (a `solve(input_data) -> dict` function)
  ├─ 3. Test it in the Sandbox against its own example inputs
  ├─ 4. Deploy it through the DeploymentProvider (Local FastAPI; Railway/Vercel next)
  └─ 5. Register it in the ToolRegistry — permanently part of its toolkit
```

## Infrastructure Control

`DeploymentProvider` is a port. The `LocalDeployer` spins up ephemeral FastAPI
processes. Cloud adapters (Railway, Vercel, AWS Lambda) can provide real scaling —
the brain can grow its own compute as its needs grow.

## Self-Healing

`SelfHealUseCase` runs after each dream cycle. Any self-generated tool whose
`success_rate` drops below 0.4 is:
1. Deprecated.
2. Regenerated with fresh context (the description + known failures).
3. Re-tested and re-registered.

## Lifecycle

```
GENERATING → TESTING → (READY | DEPLOYED) → DEPRECATED → (regenerated | garbage)
```

## Trigger

```bash
curl -X POST http://localhost:8000/v1/tools/generate \
  -H "Content-Type: application/json" \
  -d '{"name":"csv_summarizer","problem_statement":"Read a CSV and summarize each column's stats","requirements":["pandas"]}'
```
