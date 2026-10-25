"""RL training service: hard-question corpus, judge, reward store, exemplars.

Extracted from backend/main.py (strangler refactor, Upgrade 1). The judge calls
the LLM through ``llm_service`` so tests patch the owning module.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from backend.services import llm as llm_service

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

# ─── RL training: hard-question corpus, judge, reward store ──────────────────
#
# A working reinforcement-lite loop: hard questions are answered, an LLM judge
# scores them 0-10 against rubrics, pairs land in a reward store, and the
# highest-scoring answers become few-shot exemplars injected into JARVIS's
# prompt when a similar question returns - reward-weighted behavior shaping.

TRAINING_CORPUS = [
    {
        "id": "gil-py313",
        "category": "python-internals",
        "q": "How does Python 3.13 (free-threading / GIL changes) alter CPU-bound vs I/O-bound multithreading compared to older 3.x releases?",
        "rubric": [
            "GIL remains the default; free-threading is opt-in and experimental",
            "CPU-bound threads gain real core parallelism only under free-threading, and race-safety shifts to user code",
            "I/O-bound behavior is essentially unchanged because the GIL is released during blocking waits",
            "Multiprocessing remains the safe route for heavy CPU compute",
        ],
    },
    {
        "id": "cap-partition",
        "category": "distributed-systems",
        "q": "For a 3-node replicated key-value store, what must you sacrifice during a network partition, and why can consistency and availability not both hold?",
        "rubric": [
            "A partition forces a choice: reject writes (CP) or serve stale reads/writes (AP)",
            "Consistency + availability cannot both hold because nodes cannot agree on truth while cut off",
            "Concrete examples: quorum writes vs last-writer-wins divergence",
        ],
    },
    {
        "id": "friday-deadlock",
        "category": "debugging",
        "q": "Your REST API deadlocks under load only on Fridays. Describe a systematic diagnosis method.",
        "rubric": [
            "Start with observability: correlate the time pattern with scheduled jobs (Friday backups/reports/cron)",
            "Capture thread dumps / stack samples at the hang; identify the lock ordering cycle",
            "Reproduce under controlled load; fix via consistent lock ordering or timeouts",
        ],
    },
    {
        "id": "param-queries",
        "category": "security",
        "q": "Why are parameterized queries immune to SQL injection at the parser level?",
        "rubric": [
            "SQL structure is parsed/planned BEFORE parameter values are bound",
            "Injected strings remain data in a typed channel - they can never alter the parse tree",
            "Contrast with string concatenation, which mixes code and data channels",
        ],
    },
    {
        "id": "raft-timeout",
        "category": "distributed-systems",
        "q": "Why must a Raft election timeout be substantially larger than the round-trip time variance between nodes?",
        "rubric": [
            "Election timeout must exceed the worst-case round-trip so a follower does not call elections while a leader is healthy",
            "Too-small timeouts cause split votes and livelock churn",
            "Randomized timeouts break symmetry so split votes resolve",
        ],
    },
    {
        "id": "jmm-happens-before",
        "category": "concurrency",
        "q": "What does 'happens-before' actually guarantee in a memory model, and what defines a data race?",
        "rubric": [
            "Happens-before is a visibility/ordering guarantee between operations, not wall-clock time",
            "Concurrent unsynchronized conflicting accesses on shared data = data race",
            "Proper synchronization (locks/volatile) creates happens-before edges that forbid reordering observable effects",
        ],
    },
    {
        "id": "contains-p99",
        "category": "complexity",
        "q": "A colleague claims p99 latency improved 10x after switching list.contains to set.contains, but you know list and set both 'check membership'. When is that claim impossible, and what actually explains any real speedup?",
        "rubric": [
            "O(n) vs O(1) average - a 10x claim is plausible only for large n, not universally",
            "Hashing cost and collision behaviour matter; tiny collections can be faster as lists",
            "Real wins come from asymptotics at scale, cache-friendly buckets, and avoiding quadratic loops",
        ],
    },
    {
        "id": "refcycle-leak",
        "category": "python-internals",
        "q": "Why can a Python object involved in a reference cycle still leak despite refcounting plus the cycle collector?",
        "rubric": [
            "Refcounting alone never frees cycles; the cyclic GC handles pure cycles",
            "Cycles containing objects with __del__/finalizers or C-level references can evade or delay collection",
            "Global caches and exception tracebacks pin objects beyond the cycle",
        ],
    },
    {
        "id": "ecb-images",
        "category": "security",
        "q": "Why is ECB mode considered broken for images even with a cryptographically strong block cipher?",
        "rubric": [
            "ECB encrypts identical blocks to identical ciphertext - patterns survive",
            "Semantic leakage of structure (the penguin outline) without breaking the cipher itself",
            "Fix: randomized modes (CBC with IV, GCM) that chain or nonce-encrypt blocks",
        ],
    },
    {
        "id": "hex-domain-rule",
        "category": "nexs-architecture",
        "q": "In NEXUS's hexagonal architecture, why does the domain layer forbid importing infrastructure, and how do ports fix this?",
        "rubric": [
            "Domain holds pure business rules; infrastructure is replaceable detail",
            "Ports (abstract interfaces) let domain/application depend on contracts, adapters implement them",
            "The DI container is the only place concrete adapters are chosen; import-linter enforces the rule",
        ],
    },
    {
        "id": "bat-ball",
        "category": "reasoning",
        "q": "A bat and a ball cost $1.10 together. The bat costs $1.00 more than the ball. How much is the ball - and what is the intuitive trap?",
        "rubric": [
            "Ball = $0.05 (the $1.10-1.00 = 0.10 answer is the System-1 trap)",
            "Algebra: ball b, bat b+1.00, total 2b+1.00=1.10",
            "Explains why the intuitive answer feels right but fails the constraint",
        ],
    },
    {
        "id": "goroutine-race",
        "category": "concurrency",
        "q": "Two goroutines increment a shared counter 1000 times each and the final value varies per run. Name the phenomenon and give two fixes.",
        "rubric": [
            "Read-modify-write race (non-atomic increment) causing lost updates",
            "Fix 1: sync.Mutex around the critical section; Fix 2: atomic.AddInt64 or channels to serialize ownership",
            "Note determinism: correct code always yields 2000",
        ],
    },
    {
        "id": "cache-hurts",
        "category": "performance",
        "q": "Give three concrete ways adding a cache can INCREASE end-to-end latency for a workload.",
        "rubric": [
            "Low hit rate: extra hop + serialization overhead with rare hits",
            "Cache stampede/thundering herd on expiry; locking contention on hot keys",
            "Invalidation overhead and stale-read retries outweigh savings for rapidly changing data",
        ],
    },
    {
        "id": "doh-privacy",
        "category": "networking",
        "q": "Why is DNS-over-HTTPS not a privacy panacea even though it hides queries from the local network?",
        "rubric": [
            "The DoH resolver sees everything the ISP used to see - trust moves, it does not vanish",
            "Traffic analysis / SNI and IP patterns still leak destinations",
            "Centralization risks: few providers gain a global query log",
        ],
    },
    {
        "id": "docker-layers",
        "category": "containerization",
        "q": "How do Docker image layers relate to containers, and why does an unchanged layer make rebuilds fast?",
        "rubric": [
            "Images are read-only layer stacks; containers add one writable layer on top",
            "Layer caching: unchanged instruction layers are reused, only later layers rebuild",
            "Ordering matters: frequently changing files should go in later layers",
        ],
    },
    {
        "id": "k8s-probes",
        "category": "orchestration",
        "q": "In Kubernetes, what is the difference between a liveness probe and a readiness probe, and what breaks if you confuse them?",
        "rubric": [
            "Liveness failure restarts the container; readiness failure removes it from service routing",
            "Confusing them causes restart storms instead of graceful traffic shedding",
            "Startup probes guard slow-booting apps from liveness false positives",
        ],
    },
    {
        "id": "sql-index-writes",
        "category": "databases",
        "q": "Why can adding an index make SELECTs faster but UPDATEs slower?",
        "rubric": [
            "Indexes speed reads by avoiding full scans (B-tree lookups)",
            "Every write must also update each index - extra B-tree maintenance cost",
            "Over-indexing trade-off: read-heavy vs write-heavy workload tuning",
        ],
    },
    {
        "id": "http2-hol",
        "category": "networking",
        "q": "How does HTTP/2 multiplexing fix HTTP/1.1 head-of-line blocking, and what blocking remains?",
        "rubric": [
            "HTTP/1.1 blocks on one slow response per connection (HOL at request level)",
            "HTTP/2 streams multiplex over one connection, eliminating request-level HOL",
            "TCP-level HOL remains: one lost packet stalls all streams until HTTP/3/QUIC",
        ],
    },
    {
        "id": "tls-handshake",
        "category": "security",
        "q": "What does the TLS handshake actually establish, and why does an encrypted tunnel not hide the server identity from a passive observer?",
        "rubric": [
            "Handshake authenticates the server certificate and derives session keys (ECDHE)",
            "Certificates chain to trusted roots; SNI and certificate details are visible pre-encryption",
            "Passive observers still see IPs, timing, and without ECH the SNI hostname",
        ],
    },
    {
        "id": "regex-backtracking",
        "category": "algorithms",
        "q": "Give an example of catastrophic regex backtracking and how to defuse it.",
        "rubric": [
            "Nested quantifiers like (a+)+ cause exponential backtrack on near-match inputs",
            "ReDoS: a single malicious input can hang the parser",
            "Fixes: atomic groups or possessive quantifiers, rewriting patterns, RE2-style engines",
        ],
    },
    {
        "id": "float-precision",
        "category": "numerics",
        "q": "Why does 0.1 + 0.2 != 0.3 in most languages, and when does that matter in practice?",
        "rubric": [
            "Binary floating point (IEEE 754) cannot represent 0.1 exactly",
            "Accumulated rounding error breaks equality checks - use epsilon or decimals",
            "Critical domains: money (integer cents or decimal), scientific accumulation",
        ],
    },
    {
        "id": "overfitting",
        "category": "machine-learning",
        "q": "What is overfitting, how would you detect it, and name two mitigations?",
        "rubric": [
            "Model memorizes training data instead of generalizing",
            "Detection: training loss keeps dropping while validation loss rises",
            "Mitigations: regularization (L1/L2, dropout), more or augmented data, early stopping",
        ],
    },
    {
        "id": "git-rebase-shared",
        "category": "version-control",
        "q": "Why is rebasing a shared branch considered dangerous, and when is rebase the right choice?",
        "rubric": [
            "Rebase rewrites commits - collaborator histories diverge and collide",
            "Merge preserves history; rebase gives linear history on private or local branches",
            "Rule: never rebase pushed shared branches; rebase local work before a PR",
        ],
    },
    {
        "id": "eventloop-starve",
        "category": "async",
        "q": "How can a single CPU-bound task starve an async event loop, and what are two remedies?",
        "rubric": [
            "Cooperative scheduling: a task that never awaits blocks everything else",
            "Remedies: offload to a thread or process pool, or chunk work with awaited yields",
            "Symptom: all other requests freeze despite low per-task CPU",
        ],
    },
    {
        "id": "jwt-revocation",
        "category": "auth",
        "q": "Why is JWT revocation hard compared to server-side sessions, and what are two practical mitigations?",
        "rubric": [
            "JWTs are self-contained and stateless - the server has no list to delete from",
            "Mitigations: short expiry with refresh rotation, or a denylist and version marker",
            "Trade-off: statelessness vs immediate revocation control",
        ],
    },
    {
        "id": "payment-idempotency",
        "category": "api-design",
        "q": "Why must payment APIs be idempotent, and how is idempotency typically implemented?",
        "rubric": [
            "Retries and timeout duplicates must not double-charge the customer",
            "Idempotency keys: the server stores the first response per key and replays it",
            "Contrast naturally safe methods (GET) with unsafe ones (POST payment)",
        ],
    },
    {
        "id": "amortized-append",
        "category": "data-structures",
        "q": "Why is appending to a dynamic array O(1) amortized even though resizing is O(n)?",
        "rubric": [
            "Doubling capacity makes total copy cost across n appends O(n)",
            "Amortized analysis spreads the occasional O(n) resize over many O(1) ops",
            "Contrast: arbitrary mid-list insertion stays O(n) always",
        ],
    },
    {
        "id": "hash-collision-resistance",
        "category": "crypto",
        "q": "What makes a hash function collision-resistant, and why was MD5 abandoned?",
        "rubric": [
            "Collision resistance: computationally infeasible to find two inputs with the same digest",
            "MD5: practical chosen-prefix collisions demonstrated since 2004 - broken for signatures",
            "Modern choices: SHA-256 or BLAKE3; length-extension issues with Merkle-Damgard",
        ],
    },
    {
        "id": "vm-container-isolation",
        "category": "infrastructure",
        "q": "What is the fundamental difference in isolation boundary between containers and virtual machines?",
        "rubric": [
            "VMs virtualize hardware with a hypervisor - one kernel per guest",
            "Containers share the host kernel - namespace and cgroup isolation, lighter but weaker",
            "Blast radius: a container kernel vulnerability affects every container on that host",
        ],
    },
    {
        "id": "nplus1-queries",
        "category": "databases",
        "q": "Explain the N+1 query problem in ORMs and two concrete fixes.",
        "rubric": [
            "One query for the parent list, then one query per child - N+1 round trips",
            "Detection: query logging or ORM eager-load warnings on list endpoints",
            "Fixes: JOIN or eager loading (select_related, preloaded), or batched IN queries",
        ],
    },
]

RL_STATE_PATH = BACKEND_DIR / "rl_training_state.json"


# Tool-grounded training items: each question REQUIRES live tool output, so the
# RL round exercises real tool calls (cortex -> tool -> grounded answer -> judge).
TOOL_GROUND_CORPUS = [
    {
        "id": "tg-git-branch",
        "tool": "git",
        "category": "tool-grounded",
        "q": "What branch is this repository on right now, and how many uncommitted changes exist in the working tree?",
        "rubric": [
            "Answer uses the live git tool output, not a guess",
            "Names the actual branch and the actual uncommitted-change count",
        ],
    },
    {
        "id": "tg-graph-nodes",
        "tool": "diag",
        "category": "tool-grounded",
        "q": "How many nodes and links are currently in the knowledge graph?",
        "rubric": [
            "Answer uses live system diagnostics data",
            "States the actual node and link counts",
        ],
    },
    {
        "id": "tg-tasks-queue",
        "tool": "tasks",
        "category": "tool-grounded",
        "q": "How many tasks are in the swarm queue right now, and how many are resolved?",
        "rubric": [
            "Answer uses live task-queue data",
            "States actual total and resolved counts",
        ],
    },
    {
        "id": "tg-agents-online",
        "tool": "agents",
        "category": "tool-grounded",
        "q": "Which swarm agents exist, and what is each one's current status?",
        "rubric": [
            "Answer uses live agent telemetry",
            "Names the agents and their real statuses",
        ],
    },
    {
        "id": "tg-repo-read",
        "tool": "repo",
        "category": "tool-grounded",
        "q": "List the top-level entries of this repository's docs directory.",
        "rubric": [
            "Answer uses the live repo-reading tool",
            "Names real directory entries",
        ],
    },
    {
        "id": "tg-memory-blueprints",
        "tool": "memory",
        "category": "tool-grounded",
        "q": "Search memory for blueprint-related entries and summarize what you find.",
        "rubric": [
            "Answer uses live memory-query output",
            "Summarizes real chunk content, not invented summaries",
        ],
    },
]


def _load_rl_state() -> dict:
    try:
        if RL_STATE_PATH.is_file():
            data = json.loads(RL_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("pairs"), list):
                data.setdefault("daily", {})
                return data
    except Exception:
        pass
    return {"pairs": [], "daily": {}}


def _save_rl_state(state: dict) -> None:
    try:
        RL_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


RL_STATE = _load_rl_state()


def _record_training_pair(
    q: str,
    a: str,
    score: float,
    critique: str,
    category: str,
    model: str,
    judge: str = "",
) -> dict:
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "category": category,
        "model": model,
        "judge": judge,
        "score": round(float(score), 2),
        "critique": (critique or "")[:400],
        "q": (q or "")[:400],
        "a": (a or "")[:1200],
    }
    RL_STATE["pairs"].append(entry)
    day = entry["ts"][:10]
    day_stat = RL_STATE["daily"].setdefault(day, {"count": 0, "score_sum": 0.0})
    day_stat["count"] += 1
    day_stat["score_sum"] += entry["score"]
    _save_rl_state(RL_STATE)
    return entry


async def _judge_answer(q: str, answer: str, rubric: list[str]) -> dict:
    """LLM-as-judge: score 0-10 against rubric key points + a short critique."""
    system = (
        "You are a strict evaluation judge for an AI assistant. Score the ANSWER "
        "from 0 to 10 against the RUBRIC key points (each covered point earns "
        "marks; wrong, vague, or evasive claims lose marks). Reply in EXACTLY this format:\n"
        "SCORE: <number 0-10, one decimal allowed>\n"
        "CRITIQUE: <one or two sentences>"
    )
    user = f"QUESTION: {q}\n\nRUBRIC:\n- " + "\n- ".join(rubric) + f"\n\nANSWER:\n{(answer or '')[:1500]}"
    try:
        content, reasoning = await llm_service._call_llm(system, [{"role": "user", "content": user}])
        m = re.search(r"SCORE:\s*([0-9]+(?:\.[0-9]+)?)", content or "")
        c = re.search(r"CRITIQUE:\s*(.+)", content or "", re.S)
        if m:
            score = max(0.0, min(10.0, float(m.group(1))))
            critique = c.group(1).strip() if c else ""
            return {"score": score, "critique": critique[:400], "judge": "llm"}
        if reasoning:
            # Reasoning-heavy judges sometimes do the scoring inside their
            # chain-of-thought - extract it instead of falling to heuristic.
            m2 = re.search(r"SCORE:\s*([0-9]+(?:\.[0-9]+)?)", reasoning) or re.search(
                r"(\d+(?:\.\d+)?)\s*(?:/|out of)\s*10", reasoning
            )
            if m2:
                score = max(0.0, min(10.0, float(m2.group(1))))
                return {
                    "score": score,
                    "critique": "scored from judge reasoning",
                    "judge": "reasoning-derived",
                }
    except Exception:
        pass
    # Heuristic fallback so training never stalls when the judge is offline.
    words = len((answer or "").split())
    heuristic = 3.0 + (1.0 if words > 40 else 0.0) + (1.0 if words > 90 else 0.0)
    return {
        "score": min(heuristic, 10.0),
        "critique": "judge offline - heuristic length-based score",
        "judge": "heuristic",
    }


def _pick_exemplars(query: str, k: int = 2) -> list[dict]:
    """Reward-weighted memory: top-scoring past pairs whose question words
    overlap the query. These become few-shot exemplars for the live answer."""
    best = [p for p in RL_STATE["pairs"] if p.get("score", 0) >= 8.0]
    if not best:
        return []
    from nexus.infrastructure.adapters.persistence.agent_memory_store import tokenize

    q_tokens = set(tokenize(query or ""))

    def overlap(p: dict) -> int:
        return len(q_tokens & set(tokenize(p.get("q", ""))))

    best.sort(key=lambda p: (overlap(p), p.get("score", 0)), reverse=True)
    return [p for p in best[:k] if overlap(p) > 0]


# ─── Self-training: extract coding examples from research notes ─────────────

EXAMPLES_PATH = ROOT_DIR / "data" / "coding_examples.json"


def _load_examples() -> list[dict]:
    try:
        if EXAMPLES_PATH.is_file():
            data = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _save_examples(examples: list[dict]) -> None:
    EXAMPLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXAMPLES_PATH.write_text(json.dumps(examples, indent=2), encoding="utf-8")


async def extract_examples(note_path: str = "") -> dict:
    """Pull structured {instruction, input, output} coding examples from a
    research note (newest research note when no path given) and append them,
    deduplicated, to data/coding_examples.json - the self-training dataset."""
    notes_dir = ROOT_DIR / "docs" / "notes"
    if note_path:
        candidate = ROOT_DIR / note_path
        target = candidate if candidate.is_file() else notes_dir / note_path
    else:
        research_notes = sorted(notes_dir.glob("research-*.md")) if notes_dir.is_dir() else []
        if not research_notes:
            return {"ok": False, "error": "no research notes found to extract from"}
        target = research_notes[-1]

    try:
        note_text = target.read_text(encoding="utf-8")[:6000]
    except OSError as exc:
        return {"ok": False, "error": f"cannot read note: {exc}"}

    try:
        content, _r = await llm_service._call_llm(
            "You are a training-data curator. From the research note below, extract "
            "up to 4 concrete, high-value coding/question examples as a JSON array "
            'of objects {"instruction": str, "input": str, "output": str}. Reply '
            "ONLY with the JSON array.",
            [{"role": "user", "content": note_text}],
        )
        match = re.search(r"\[.*\]", content or "", re.S)
        arr = json.loads(match.group(0)) if match else []
    except Exception as exc:
        return {"ok": False, "error": f"extraction synthesis failed: {exc}"}

    if not isinstance(arr, list):
        return {"ok": False, "error": "extraction returned a non-list payload"}

    known = {e.get("instruction") for e in _load_examples()}
    added = []
    for item in arr[:4]:
        if (
            isinstance(item, dict)
            and item.get("instruction")
            and item.get("output")
            and item["instruction"] not in known
        ):
            known.add(item["instruction"])
            added.append(
                {
                    "instruction": str(item["instruction"])[:400],
                    "input": str(item.get("input", ""))[:400],
                    "output": str(item["output"])[:800],
                }
            )

    if added:
        _save_examples(_load_examples() + added)
    return {
        "ok": True,
        "note": str(target),
        "added": len(added),
        "total": len(_load_examples()),
    }
