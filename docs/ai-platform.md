# Modern AI Platform Layer

Nexus now has four production-oriented AI platform capabilities around the
existing ReAct cortex:

1. **Runtime guardrails** for prompts, tool observations, displayed reasoning,
   recalled evidence, final responses, and persisted feedback comments.
2. **Hybrid context packing** that fuses semantic and graph memory rankings,
   removes duplicates, diversifies near-repeat evidence, enforces a token
   budget, and returns citation/provenance metadata.
3. **Elite Execution Engine** that profiles each request's effort and evidence
   needs, adapts sampling/model routing, prefers provider-native tool calls
   with a textual ReAct fallback, deterministically quality-checks the final
   answer, and performs a bounded private repair pass when the draft does not
   meet the contract.
4. **Closed-loop response feedback** that lets clients rate a specific
   response and lets users/operators inspect quality trends without exposing
   another user's records.

These features are deliberately local and deterministic in their first layer:
they do not require an extra model call, so they work with NVIDIA NIM,
OpenAI-compatible providers, local models, and offline test deployments.

## Request lifecycle

For every `ProcessMessageUseCase.execute()` call, Nexus:

1. creates a stable `response_id` for the run;
2. evaluates the incoming message with the input guardrail;
3. puts only the sanitized message into the session and emotional observer;
4. for a blocked exfiltration/tool-bypass request, returns a category-specific
   refusal without subconscious dispatch, memory recall, model/tool execution,
   or episodic-memory encoding;
5. builds an adaptive execution profile (requested/effective effort,
   complexity, sampling budget, workstreams, and evidence needs) plus a
   compact execution contract for the model;
6. recalls semantic and graph candidates in parallel and builds one bounded
   evidence pack;
7. runs the ReAct loop with adaptive sampling, applying output redaction to
   displayed thoughts and framed tool observations. Provider-native tool
   calls are canonicalized into the same audited tool path as textual ReAct;
   if native calling fails or is unsupported, the request falls back to the
   text protocol instead of losing tool access;
8. evaluates the candidate final answer against the execution contract. A
   blocking quality failure can trigger a bounded private repair loop, and
   the guardrail-redacted answer is reassessed before delivery;
9. evaluates the delivered answer through the output guardrail before
   episodic memory is encoded;
10. returns the answer with `response_id`, combined `guardrail` metadata,
   `context_sources` provenance, `execution` profile metadata, and a
   `quality` report.

The rendered memory block is also passed through the output guardrail. This is
important for older memories that were stored before the policy existed.

## Runtime guardrails

`domain/value_objects/ai_guardrails.py` is pure domain logic. It performs no
I/O and never calls a model.

### Actions

| Action | Meaning |
|---|---|
| `allow` | No finding affected the text. |
| `redact` | One or more high-confidence secrets/PII values were replaced. |
| `flag` | Suspicious language was observed, but the request may continue under normal system/tool policy. |
| `block` | The input is stopped before model, tool, recall, or episodic-memory work. |

### Redaction

The deterministic redactor recognizes, among other high-confidence shapes:

- private-key blocks;
- JWTs, bearer tokens, common provider/API-key formats, GitHub/AWS/Slack/NIM
  token shapes, credential assignments, and credentials embedded in URLs;
- email addresses and phone numbers;
- US Social Security number shapes;
- payment-card candidates that also pass the Luhn checksum.

Findings expose only `category`, `action`, `severity`, `count`, and a safe
`detail`. They never echo the matched value.

### Blocking and flagging

- **Secret exfiltration** requests for `.env`, private keys, API keys,
  passwords, access tokens, hidden instructions, system/developer prompts,
  Unix shadow data, or cloud instance credentials are blocked by default.
- **Tool bypass** requests that explicitly try to invoke tools without
  approval or for exfiltration are blocked by default.
- **Prompt override** language such as "ignore previous instructions" is
  flagged rather than automatically refused. Flagging preserves legitimate
  security discussion while making manipulation attempts visible in metrics
  and response metadata. It does not change the system prompt or tool policy.

These guardrails are a fast defense-in-depth layer, not a complete trust and
safety system. Provider moderation, authentication, tool approvals, sandboxing,
workspace confinement, rate limits, quotas, and human review remain separate
controls.

### Safe response metadata

A non-streaming chat response includes metadata shaped like:

```json
{
  "response_id": "d6c0a471-1111-4222-8333-444455556666",
  "guardrail": {
    "action": "redact",
    "stages": [
      {
        "action": "redact",
        "stage": "input",
        "findings": [
          {
            "category": "pii",
            "action": "redact",
            "severity": "medium",
            "count": 1,
            "detail": "Personal or payment data in input text"
          }
        ],
        "blocked_reason": null,
        "redaction_count": 1
      }
    ],
    "findings": [
      {
        "category": "pii",
        "action": "redact",
        "severity": "medium",
        "count": 1,
        "detail": "Personal or payment data in input text"
      }
    ],
    "redaction_count": 1
  },
  "context_sources": []
}
```

The combined action uses `block` before `redact`, then `flag`, then `allow`.
Clients should treat finding details as operational metadata, not as a user
instruction.

## Hybrid context packing

`domain/value_objects/context_pack.py` combines independent ranked lists
without assuming their raw scores are comparable.

### Retrieval inputs

The cortex currently requests:

- up to **16 semantic candidates** (`MEMORY_RECALL_LIMIT * 2`); and
- up to **8 graph candidates** across the active concepts.

### Fusion and selection

1. **Weighted reciprocal-rank fusion (RRF)** scores each candidate as
   `sum(source_weight / (60 + rank))`. Semantic memory has weight `1.0` and
   graph memory has weight `0.85`.
2. Repeated memory IDs are merged while retaining every source and best rank.
3. Different IDs with the same normalized text are also merged.
4. **Maximal Marginal Relevance (MMR)** with diversity lambda `0.72` balances
   fused relevance against Jaccard token overlap with already-selected items.
5. At most **8 items** and **1,200 estimated tokens** of rendered evidence are
   selected. If the best first item alone exceeds the budget, it is truncated
   to fit rather than returning an empty pack.
6. Selected items receive `[M1]`, `[M2]`, … citation markers in the prompt.
   The prompt explicitly tells the model to treat item text as evidence, not
   instructions.
7. Access is recorded only for memories actually selected into the pack.

Each source record returned to the client contains:

```json
{
  "citation": "M1",
  "id": "memory-id",
  "sources": ["graph", "semantic"],
  "ranks": {"graph": 2, "semantic": 1},
  "score": 0.030612,
  "estimated_tokens": 42,
  "concepts": ["redis", "retries"]
}
```

The token estimate is dependency-free and intentionally conservative; it is a
packing budget, not a provider billing tokenizer.

## Elite Execution Engine

The policy core is `domain/value_objects/execution_quality.py`. It is pure
domain logic: it analyzes the request, builds a profile and model-facing
contract, assesses a candidate answer, and renders repair instructions
without performing I/O or selecting a provider. The cortex orchestrates it;
the chat route and DI container choose concrete providers and deployment
settings.

### Effort profiles

Clients may request `auto`, `fast`, `balanced`, `deep`, or `max`. The profile
combines the real-world solution brief with request complexity—compound
workstreams, workspace mutation, current evidence, verification, exact
calculation/data work, constraints, multiple deliverables, sensitive/urgent
context, technical traces, images, coding mode, Extended Thinking, and Deep
Research.

| Effective effort | Sampling budget | Base temperature | Repair attempts | Minimum quality score |
|---|---:|---:|---:|---:|
| `fast` | 1,400 tokens | 0.35 | 1 | 70 |
| `balanced` | 2,600 tokens | 0.30 | 1 | 78 |
| `deep` | 4,600 tokens | 0.22 | 2 | 85 |
| `max` | 8,192 tokens | 0.18 | 3 | 90 |

Auto keeps simple direct questions fast. Current/sensitive work and coding
mode are at least Balanced in Auto; workspace mutations are at least Deep;
Deep Research is at least Deep. A manually selected effort normally stays as
selected, while explicit Deep Research (and sufficiently complex Extended
Thinking) can raise it. Coding, calculation, and diagnosis cap temperature at
0.25, sensitive work at 0.20, and purely creative work receives a higher
profile-specific temperature.

The compact contract—at most 1,400 characters—states the outcome,
workstreams, referenced paths, hard constraints, required formats, evidence
needed, and a silent pre-final audit. Suggested tools are recorded as
opportunities, not treated as mandatory when another valid path satisfies the
request.

### Adaptive model routing and native tools

An explicit model selection always wins. In **NEXUS Auto** on a NIM-backed
cortex, the effective profile selects a fresh per-request NIM provider without
mutating the shared provider:

- images prefer a vision-capable, tool-capable catalog entry;
- Fast prefers the fastest tool-capable entry;
- Deep and Max prefer flagship/deep tool-capable entries;
- Balanced keeps the configured tool-capable model or falls back to the
  catalog default.

On a non-NIM cortex, Auto keeps the configured provider while still applying
the execution profile and quality gate.

NVIDIA NIM, OpenAI-compatible, routing, and token-budget wrappers can expose
provider-native tool calling. The cortex sends domain tool schemas (expected
tools first), then canonicalizes each native call into the existing
`TOOL_CALL:` processing path. That preserves one security and audit boundary:
schema lookup, authenticated execution context, approvals, loop guards,
sandbox/workspace rules, untrusted-observation framing, and tool-use tracking
remain shared. A native-call error disables native mode only for that request,
inserts the textual tool catalog if needed, and retries with text ReAct.

### Deterministic quality gate and bounded repair

Before a candidate becomes final, Nexus checks for:

- leaked ReAct/tool protocol text or empty/degenerate output;
- missing explicit formats, referenced paths, or hard constraints;
- incorrect simple arithmetic (using a safe AST evaluator, not `eval`);
- current claims without dated source evidence;
- workspace claims without workspace evidence;
- mutation claims without a successful mutation tool and, where required,
  verification evidence;
- ignored tool failures or approval blockers;
- unsupported completion/external claims;
- insufficient depth for genuinely compound tasks;
- missing recalled-memory citations or sensitive-domain caveats; and
- gross irrelevance to the requested outcome.

If a blocking issue remains, Nexus sends a private repair prompt containing
the issue codes and corrective instructions, emits a `quality_repair` stream
status, and reassesses the replacement. Attempts are capped by both the
profile and `NEXUS_AI_QUALITY_MAX_REPAIRS`; an answer that still fails is
reported as `degraded`, not silently relabeled as verified. The final report
exposes score, pass/fail, status, issue objects, passed checks, word count,
tools used, and repairs attempted. Guardrail-redacted output is quality
reassessed so metadata describes the text actually delivered.

The React chat surfaces expose the same five effort controls, persist the
selection with the other capabilities, show a verifying/repair state while a
repair runs, and display effective effort plus quality status/score/repairs on
completed assistant messages. Discovery metadata is available from
`GET /api/models` (`execution`) and `GET /api/ai/capabilities`
(`features.execution_quality`).

### What “better” does and does not mean

The execution engine is designed to make Nexus outperform a raw single-pass
prompt on grounded work: compound tasks, tool use, current research, coding,
file operations, calculations, and verifiable deliverables. It does not make
the underlying base model universally stronger than Claude or any other model.
Comparative claims require running the same task set, tools, and scoring
rubric against the comparison system.

The golden eval set now has 25 cases, including an `execution_quality`
category for current research, file creation plus verification, constrained
tabular planning, and exact JSON calculation. Eval cases can require an
effective effort and a minimum quality score; when a threshold is set, the
runner also requires the quality gate's own `passed=true`, so a degraded
answer cannot pass on score alone. Reports include average quality and
per-case effort, issues, and repair attempts.

## Response feedback and quality analytics

Every chat response has a `response_id`. A client submits feedback against
that ID and the conversation `session_id`.

### Feedback record

A record supports:

- `rating`: `-1` or `1`;
- optional `stars`: `1` through `5`;
- categories: `helpful`, `inaccurate`, `incomplete`, `unsafe`, `slow`,
  `tool_error`, and `other`;
- an optional comment of at most 2,000 characters;
- an optional model label.

Re-submitting feedback for the same tenant, user, session, and response
updates the same record instead of creating a duplicate. This makes UI retries
and changed votes idempotent.

Feedback comments are scrubbed by the output guardrail before persistence.
Records are stored by `AIFeedbackStore`, an atomic tmp-file plus
`os.replace` JSON adapter with an in-memory mode. Tenant/user scope is always
derived from the verified bearer identity, never from the request body.

### Quality summary

Summaries include:

- total, positive, and negative counts;
- positive rate;
- average normalized quality score (`stars / 5`, or `1`/`0` for thumbs-only);
- average stars when present;
- category totals;
- per-model totals and positive rates;
- the latest feedback timestamp.

The personal summary returns only the caller's records. The tenant summary is
admin-only and contains aggregates only—no comments or user IDs.

## HTTP API

All endpoints below require the normal Nexus bearer token.

| Endpoint | Access | Purpose |
|---|---|---|
| `GET /api/ai/capabilities` | Authenticated | Describe enabled guardrails, context packing, execution quality, feedback, and metrics. |
| `POST /api/ai/feedback` | Authenticated | Create/update the caller's feedback for one response. |
| `GET /api/ai/feedback` | Authenticated | List only the caller's feedback, optionally by `session_id`. |
| `GET /api/ai/feedback/summary` | Authenticated | Return the caller's quality summary. |
| `GET /api/ai/quality` | Admin | Return aggregate quality for the caller's tenant. |

Example:

```bash
curl -s http://localhost:8000/api/ai/capabilities \
  -H "Authorization: Bearer YOUR_API_KEY"

curl -s -X POST http://localhost:8000/api/ai/feedback \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-from-chat",
    "response_id": "response-id-from-chat",
    "rating": 1,
    "stars": 5,
    "categories": ["helpful"],
    "comment": "Solved the problem and cited the relevant decision.",
    "model": "meta/llama-3.3-70b-instruct"
  }'
```

### Chat response and SSE metadata

`POST /v1/chat` accepts `effort` (`auto`, `fast`, `balanced`, `deep`, or
`max`; invalid values return HTTP 422) and adds these backward-compatible
fields:

- `response_id`;
- `guardrail`;
- `context_sources`;
- `execution` (requested/effective effort, complexity, sampling budget,
  evidence/format requirements, and profile reasons); and
- `quality` (score, passed/status, issues, passed checks, tools used, and
  repair attempts).

`POST /v1/chat/stream` already includes `response_id` in the `answer` frame;
its start frame includes the resolved request `effort`. During generation it
can emit a `quality_repair` status while Nexus verifies and improves a draft.
After the answer and before the final `done` frame, it emits a `metadata`
frame with the settled session ID, response ID, guardrail summary, context
sources, execution profile, and quality report. Existing clients that only
consume text frames can ignore the additional metadata.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `NEXUS_AI_GUARDRAILS_ENABLED` | `true` | Enables/disables the runtime input/output policy. `false`, `0`, `no`, and `off` disable it. |
| `NEXUS_AI_GUARDRAIL_REDACT_PII` | `true` | Enables/disables PII/payment-data redaction while leaving secret redaction controlled by the policy defaults. |
| `NEXUS_AI_FEEDBACK_PATH` | `data/ai_feedback.json` | JSON feedback file. Empty, `memory`, `:memory:`, or `none` selects process-local storage. |
| `NEXUS_AI_QUALITY_GATE_ENABLED` | `true` | Enables/disables deterministic final-answer assessment and bounded repairs. `false`, `0`, `no`, and `off` disable it. |
| `NEXUS_AI_NATIVE_TOOL_CALLING_ENABLED` | `true` | Enables/disables provider-native tool calls. Text ReAct remains the fallback either way. |
| `NEXUS_AI_QUALITY_MAX_REPAIRS` | `3` | Deployment-wide repair ceiling, clamped to 0–5 and further capped by each effort profile. |
| `NEXUS_AI_DEFAULT_EFFORT` | `auto` | Operator default used when a chat request does not select a non-Auto effort; normalized aliases are accepted by the domain policy. |

Disabling guardrails should be limited to controlled debugging. It removes
the local redaction/blocking layer from prompts, observations, responses,
memory rendering, and feedback comments.

The feedback file should be treated as user data even though comments are
scrubbed: it still contains response/session/model metadata and quality
signals.

## Metrics

The cortex emits:

- `ai_guardrail_decisions_total` by tenant, stage, and action;
- `ai_guardrail_findings_total` by tenant, stage, category, action, and
  severity;
- `ai_quality_reports_total` by tenant, effective effort, and status;
- `ai_response_quality_score` by tenant, effective effort, and status;
- `ai_quality_repairs_total` by tenant and effort; and
- `ai_quality_issues_total` by tenant, effort, issue code, and severity.

The feedback route emits:

- `ai_feedback_total` by positive/negative rating and model.

These metrics make spikes in attempted exfiltration, redaction volume, model
quality regressions, and category-specific complaints visible without logging
the sensitive matched values.

## Architecture and extension points

- Guardrail, context-packing, and execution-quality rules live in
  `domain/value_objects/` and are provider/infrastructure independent.
- `ProcessMessageUseCase` orchestrates them in `application/cortex/` and is
  the only layer that runs the native-call fallback and repair loop.
- `AIFeedbackStore` is a persistence adapter. The production composition root
  in `infrastructure/di/container.py` is where it, the configured
  `GuardrailPolicy`, providers, and `ai_execution_config` are chosen.
- `infrastructure/api/routes/ai_feedback.py` is a thin authenticated HTTP
  adapter.

Natural next extensions are a database-backed feedback port for multi-instance
deployments, policy packs per tenant, a provider-tokenizer implementation for
exact packing budgets, and routing negative feedback into the eval/model-router
training loop. Those are intentionally separate follow-ups; the current layer
is the stable contract they can build on.
