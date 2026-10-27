# How to Train the NEXUS Framework (RL Loop)

NEXUS improves through a **reinforcement-lite loop**: it answers hard
questions, an LLM judge grades each answer 0–10 against a rubric, scored
pairs land in a reward store, and the highest-rated answers become few-shot
exemplars that are injected into future prompts. Training runs in three
modes: manual rounds, the daily background loop, and **tool-grounded rounds**
where answers must be backed by live tool output.

## The loop, in one picture

```
question ──▶ cortex (+ tools ──▶ shared blackboard) ──▶ answer
                                                           │
        exemplars ◀── reward store ◀── judge (0-10 + critique)
             └──────────────▶ next answers improve
```

## 1. Run a training round

```powershell
# answer + judge 3 fresh questions (skips already-scored ones)
Invoke-RestMethod "http://127.0.0.1:8001/api/training/run?n=3" -Method Post
```

- `n` caps how many *new* questions are trained per call.
- Two corpora are pooled: the 30-question hard-question corpus (23 domains —
  Python internals, distributed systems, security, crypto, ML, databases,
  async, API design…) and the 6 **tool-grounded** questions that exercise
  live tools (git status, task queue, agent telemetry, memory query, repo
  reads, graph diagnostics).
- Each round: answer → judge → store → next run picks up new questions.

## 2. Tool-grounded rounds (the tools get trained too)

Corpus items with a `"tool"` field make the round **call the real tool**
(`run_tool_by_name`), publish the result on the **shared tool blackboard**,
and require the answer to be grounded in those actual values — the judge has
an extra rubric point for grounding. This trains tool-calling behavior, not
just prose. Add a new tool-grounded question by appending to
`TOOL_GROUND_CORPUS` in `backend/services/training.py`:

```python
{"id": "tg-my-tool", "tool": "git", "category": "tool-grounded",
 "q": "…", "rubric": ["answer uses live tool output", …]}
```

## 2b. Real-task rounds (objective verification)

Real-task rounds are different from the question corpus: instead of asking a
question and judging the answer with an LLM rubric, the brain is given real
engineering work (write a module, fix a bug) inside a fresh throwaway
workspace, and the reward is OBJECTIVE - the task ships its own verification
script, and the score is whether the generated code actually passes it.

| Outcome | Score |
| --- | --- |
| Passes verification first try | 10.0 |
| Passes after one repair round (with the traceback fed back) | 7.5 |
| Never passes | 3.0 |

Passing transcripts are stored as coding exemplars in
`data/coding_examples.json`, so the brain trains on its own successful work.

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8001/api/training/run-tasks `
  -Method Post -ContentType application/json -Body '{"n": 2, "repair": true}'
```

The request body: `n` = how many not-yet-attempted tasks to run (tasks already
in the reward store are skipped), `repair` = give the model one repair round
with its own traceback when verification fails. Each response item carries the
task id, score, pass flag, attempt count and the tail of the verifier output.

## 3. Add hard questions

Append to `TRAINING_CORPUS` in `backend/services/training.py`:

```python
{"id": "unique-id", "category": "databases",
 "q": "the hard question",
 "rubric": ["key point 1", "key point 2", "key point 3"]}
```

Rules: unique `id`, ≥3 rubric key points (the judge scores against them),
prefer questions the current model gets *partially* wrong — that's where the
reward signal is. The corpus now spans 23 non-NEXUS domains; keep it broad.

## 4. Judge custom answers

```powershell
Invoke-RestMethod "http://127.0.0.1:8001/api/training/judge" -Method Post `
  -ContentType "application/json" `
  -Body '{"q": "…", "a": "…", "category": "…"}'
```

## 5. Read the progress

- `GET /api/training/stats` — total pairs, average score, **day-by-day
  averages**, per-category averages, top exemplars.
- Reward store: `backend/rl_training_state.json` (git-ignored).
- Exemplars: pairs scoring ≥ 8 are injected into future prompts when a
  similar question appears (token-overlap matching via `bb_get`-backed
  `_pick_exemplars`).

## 6. The daily loop

On backend startup a background task trains 3 questions every 24 hours —
no action needed. `POST /api/training/run` adds extra rounds on demand.

## 7. Cross-tool data sharing (the blackboard)

Every dispatched tool publishes its structured output to
`TOOL_BLACKBOARD` (`bb_put`); later tools and the synthesis pass read it
(`bb_get`/`bb_compact`). A multi-part question ("check git status and the
task queue") runs **both** tools and merges their data into one grounded
answer; deep research consumes the blackboard as shared context. Tools that
need what another tool knows get it through `bb_get(key)` or
`run_tool_by_name(name, query)`.
