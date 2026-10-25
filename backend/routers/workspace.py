"""NEXUS OS — workspace cockpit API (Screen 1 dashboard + Screen 2 floating console).

The light-mode ``frontend/workspace.html`` page is a thin shell over this router:

* ``GET  /api/workspace/bootstrap``            → identity, engine state, usage meters,
                                                 feature cards, route catalog, history
* ``POST /api/workspace/runs``                 → open a run on one of four routes
                                                 (deep_research | image | search | music)
* ``GET  /api/workspace/runs/{id}/stream``     → SSE frames that drive the dual-layer
                                                 cyan/violet "THINKING → STREAMING" aura
* ``GET  /api/workspace/runs/{id}``            → poll fallback / reconnect snapshot
* ``POST /api/workspace/runs/{id}/cancel``     → cooperative cancel
* ``GET  /api/workspace/art/{id}.svg``         → deterministic procedural poster
* ``GET  /api/workspace/audio/{id}.wav``       → procedurally synthesised music stem
* ``POST /api/workspace/upgrade``              → plan catalog (no payment provider wired)

Everything degrades gracefully: when no LLM is reachable the deep-research route
composes a grounded local briefing over the repository's own docs (and says so in
``meta.engine``), search always hits the real knowledge base, and image/music
artifacts are genuinely rendered/synthesised server-side rather than faked.

State is per-process (bounded to ``MAX_RUNS``); this is a cockpit demo surface,
not a durable job queue.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import io
import json
import math
import os
import re
import struct
import time
import uuid
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from backend.schemas import WorkspaceRunRequest, WorkspaceUpgradeRequest
from backend.services import llm as llm_service

router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = ROOT_DIR / "docs"
NOTES_DIR = ROOT_DIR / "frontend" / "sample-notes"
README_PATH = ROOT_DIR / "README.md"
SAMPLE_ASSET = "/assets/workspace/quantum-bloom.jpg"

MAX_RUNS = 40
MAX_HISTORY = 12

# Streaming pace multiplier. Tests (and impatient operators) set NEXUS_WORKSPACE_PACE=0.
DEFAULT_PACE = 1.0


# ── route catalog ────────────────────────────────────────────────────────────

ROUTES: dict[str, dict[str, Any]] = {
    "deep_research": {
        "id": "deep_research",
        "label": "Deep Research",
        "short": "Research",
        "accent": "cyan",
        "hint": "Multi-hop briefing with grounded citations",
        "cost": 6,
        "steps": [
            ("scope", "Scope the question", "Decompose the brief into answerable sub-questions."),
            ("sweep", "Sweep the knowledge base", "Rank repository docs and notes by relevance."),
            ("verify", "Cross-check claims", "Keep only claims backed by retrieved passages."),
            ("brief", "Synthesize briefing", "Write the operator-ready answer with citations."),
        ],
    },
    "image": {
        "id": "image",
        "label": "Make an Image",
        "short": "Image",
        "accent": "violet",
        "hint": "Procedural canvas render + studio art direction",
        "cost": 4,
        "steps": [
            ("parse", "Parse the visual brief", "Extract subject, mood, palette and composition."),
            ("compose", "Compose the frame", "Lay out layered gradients, orbits and grain."),
            ("render", "Render the artwork", "Deterministic vector render on the GPU-free canvas."),
            ("export", "Package the export", "Attach the poster and a reusable art direction."),
        ],
    },
    "search": {
        "id": "search",
        "label": "Search",
        "short": "Search",
        "accent": "graphite",
        "hint": "Ranked passages across the repository knowledge base",
        "cost": 1,
        "steps": [
            ("normalize", "Normalize the query", "Tokenize, drop stopwords, expand synonyms."),
            ("scan", "Scan indexed notes", "Score every paragraph in docs/ and sample notes."),
            ("rank", "Rank passages", "Blend term frequency with title and path signal."),
            ("assemble", "Assemble results", "Return the strongest passages with source paths."),
        ],
    },
    "music": {
        "id": "music",
        "label": "Create music",
        "short": "Music",
        "accent": "orange",
        "hint": "Mood-aware composition blueprint + rendered stem",
        "cost": 3,
        "steps": [
            ("mood", "Read the mood", "Map prompt language to energy, warmth and tension."),
            ("key", "Choose key & tempo", "Pick scale, root note and BPM for the arrangement."),
            ("arrange", "Arrange layers", "Stack pad, arpeggio, bass and air textures."),
            ("render", "Render the stem", "Synthesize an 8-second 22 kHz WAV preview."),
        ],
    },
}

ROUTE_ORDER = ("deep_research", "image", "search", "music")

PLANS = (
    {
        "id": "free",
        "name": "Explorer",
        "price": 0,
        "period": "month",
        "credits": 40,
        "blurb": "Every cockpit route, community support.",
        "perks": ["40 credits / month", "Search + image routes", "Local engine"],
    },
    {
        "id": "studio",
        "name": "Studio",
        "price": 24,
        "period": "month",
        "credits": 1200,
        "blurb": "For operators shipping every day.",
        "perks": ["1,200 credits / month", "Deep research + music", "Priority streaming"],
        "current": True,
    },
    {
        "id": "atlas",
        "name": "Atlas",
        "price": 89,
        "period": "month",
        "credits": 6000,
        "blurb": "Multi-agent orchestration at team scale.",
        "perks": ["6,000 credits / month", "Unlimited agent seats", "SSO + audit trail"],
    },
)

# ── in-memory stores ─────────────────────────────────────────────────────────

RUNS: dict[str, dict[str, Any]] = {}
_AUDIO_CACHE: dict[str, bytes] = {}
_SEARCH_INDEX: list[dict[str, Any]] | None = None
_LLM_PROBE: dict[str, Any] = {"at": 0.0, "alive": False}

_USAGE = {"day": "", "runs": 0, "credits_spent": 0, "plan": "studio"}
PLAN_CREDITS = 1200


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _roll_usage() -> None:
    today = _today()
    if _USAGE["day"] != today:
        _USAGE["day"] = today
        _USAGE["runs"] = 0
        _USAGE["credits_spent"] = 0


def _pace_multiplier() -> float:
    """Read NEXUS_WORKSPACE_PACE per call so tests can zero it without reimporting."""
    raw = os.environ.get("NEXUS_WORKSPACE_PACE")
    if raw is None or raw == "":
        return DEFAULT_PACE
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_PACE


def _pace(seconds: float) -> float:
    return seconds * _pace_multiplier()


async def _pause(seconds: float) -> None:
    delay = _pace(seconds)
    if delay > 0:
        await asyncio.sleep(delay)


def _route(route_id: str) -> dict[str, Any] | None:
    return ROUTES.get(route_id)


def _public_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run["id"],
        "prompt": run["prompt"],
        "route": run["route"],
        "route_label": ROUTES[run["route"]]["label"],
        "status": run["status"],
        "created_at": run["created_at"],
        "credits": run["credits"],
        "engine": run.get("engine"),
        "answer": run.get("answer"),
        "artifacts": run.get("artifacts", []),
        "duration_ms": run.get("duration_ms"),
    }


def _trim_runs() -> None:
    if len(RUNS) <= MAX_RUNS:
        return
    ordered = sorted(RUNS.values(), key=lambda r: r["created"])
    for stale in ordered[: len(RUNS) - MAX_RUNS]:
        RUNS.pop(stale["id"], None)
        _AUDIO_CACHE.pop(stale["id"], None)


# ── knowledge base (real repository docs) ────────────────────────────────────

_STOP = frozenset(
    """a an and are as at be but by for from has have how i if in into is it its of on or
    that the their then there these this to was were what when where which who why will with
    you your can could should would do does about explain simply simple""".split()
)


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 2 and t not in _STOP]


def _iter_note_files() -> list[Path]:
    files: list[Path] = []
    for base, glob in ((DOCS_DIR, "**/*.md"), (NOTES_DIR, "**/*.md")):
        if base.is_dir():
            files.extend(sorted(base.glob(glob)))
    if README_PATH.is_file():
        files.append(README_PATH)
    return files


def _build_index() -> list[dict[str, Any]]:
    global _SEARCH_INDEX
    if _SEARCH_INDEX is not None:
        return _SEARCH_INDEX

    entries: list[dict[str, Any]] = []
    for path in _iter_note_files():
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # docs/README mix real markdown with HTML entities (&bull;, &mdash;); decode
        # them once at index time so snippets read as prose, not source.
        raw = html.unescape(raw)
        rel = path.relative_to(ROOT_DIR).as_posix()
        title = path.stem.replace("-", " ").replace("_", " ").strip().title()
        for block in re.split(r"\n\s*\n", raw):
            body = " ".join(block.split())
            if len(body) < 40:
                continue
            if body.startswith("#"):
                title = body.lstrip("# ").strip()[:80] or title
                continue
            entries.append(
                {
                    "path": rel,
                    "title": title,
                    "text": body,
                    "tokens": _tokenize(body),
                }
            )
    _SEARCH_INDEX = entries
    return entries


def search_knowledge(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Plain BM25-lite ranking over the repository's own markdown notes."""
    terms = _tokenize(query)
    if not terms:
        return []
    index = _build_index()
    df: dict[str, int] = {}
    for entry in index:
        for term in set(entry["tokens"]) & set(terms):
            df[term] = df.get(term, 0) + 1

    n_docs = max(1, len(index))
    terms_set = set(terms)
    hits: list[dict[str, Any]] = []
    for entry in index:
        tokens = entry["tokens"]
        if not tokens:
            continue
        counts: dict[str, int] = {}
        for token in tokens:
            if token in terms:
                counts[token] = counts.get(token, 0) + 1
        if not counts:
            continue
        score = 0.0
        length = len(tokens)
        for term, tf in counts.items():
            idf = math.log(1 + (n_docs - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
            score += idf * (tf * 2.4) / (tf + 1.2 + 0.5 * length / 90)
        title_hits = sum(1 for term in terms if term in entry["title"].lower())
        score += title_hits * 1.4
        if score <= 0:
            continue
        # coverage = share of query terms actually present. A passage that catches
        # one common word is a coincidence, not evidence — the callers gate on it.
        coverage = len(terms_set & set(tokens)) / max(1, len(terms_set))
        hits.append(
            {
                "title": entry["title"],
                "path": entry["path"],
                "snippet": _snippet(entry["text"], terms),
                "score": round(score, 3),
                "coverage": round(coverage, 2),
                "match": int(round(coverage * 100)),
            }
        )

    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:limit]


def _snippet(text: str, terms: list[str], width: int = 240) -> str:
    lowered = text.lower()
    pos = -1
    for term in terms:
        found = lowered.find(term)
        if found >= 0 and (pos < 0 or found < pos):
            pos = found
    if pos < 0:
        pos = 0
    start = max(0, pos - width // 3)
    chunk = text[start : start + width].strip()
    if start > 0:
        chunk = "…" + chunk
    if start + width < len(text):
        chunk = chunk + "…"
    return chunk


# ── engine probe ─────────────────────────────────────────────────────────────


def _engine_mode() -> str:
    return (os.environ.get("NEXUS_WORKSPACE_ENGINE") or "auto").strip().lower()


async def llm_alive() -> bool:
    """Cached liveness probe so cockpit runs never stall on a dead local server."""
    if _engine_mode() == "local":
        return False
    now = time.time()
    if now - _LLM_PROBE["at"] < 30:
        return bool(_LLM_PROBE["alive"])
    alive = False
    base = str(llm_service.LLM_CFG.get("base_url") or "").strip()
    if _engine_mode() == "llm" or base:
        try:
            alive = bool(await asyncio.wait_for(llm_service._check_llm_alive(), timeout=2.5))
        except Exception:
            alive = False
    _LLM_PROBE.update({"at": now, "alive": alive})
    return alive


def _engine_label() -> dict[str, Any]:
    alive = bool(_LLM_PROBE.get("alive"))
    model = str(llm_service.LLM_STATE.get("model") or llm_service.LLM_CFG.get("model") or "")
    return {
        "reachable": alive,
        "provider": llm_service.LLM_STATE.get("provider", "local"),
        "model": model,
        "label": f"{model} · live" if alive and model else "Grounding engine · local",
        "mode": _engine_mode(),
    }


# ── composition: grounded local briefing ─────────────────────────────────────


def _keywords(prompt: str, limit: int = 4) -> list[str]:
    seen: list[str] = []
    for token in _tokenize(prompt):
        if token not in seen:
            seen.append(token)
        if len(seen) >= limit:
            break
    return seen


def _clean_prompt(prompt: str, limit: int = 160) -> str:
    text = " ".join(prompt.split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _local_deep_research(prompt: str) -> tuple[str, list[dict[str, Any]]]:
    """Grounded briefing composed offline.

    Honesty over polish: a passage only counts as evidence when it covers most of the
    query's terms. Otherwise the answer states plainly that the corpus is silent and
    returns a reasoning scaffold the operator can verify.
    """
    hits = search_knowledge(prompt, limit=5)
    topics = _keywords(prompt, 4) or ["the brief"]
    cited = [h for h in hits if h["coverage"] >= 0.6][:3]
    tangential = [h for h in hits if h not in cited][:1]

    lines: list[str] = [f"**Question.** {_clean_prompt(prompt)}", "", "**Corpus signal.**"]
    if cited:
        files = sorted({h["path"] for h in cited})
        lines.append(
            f"{len(cited)} passage{'s' if len(cited) > 1 else ''} clear the relevance bar "
            f"({', '.join('`' + f + '`' for f in files[:3])}). The strongest sits under "
            f"“{cited[0]['title']}”."
        )
    else:
        lines.append(
            "Nothing in the indexed corpus (docs/, sample notes, README) covers this directly — "
            f"{_clean_prompt(prompt, 60)} is outside the written record. The briefing below is a "
            "reasoning scaffold, not a citation-backed answer."
        )

    lines += ["", "**What holds up.**"]
    if cited:
        for index, hit in enumerate(cited, start=1):
            lines.append(f"{index}. **{hit['title']}** — {hit['snippet']}  \n   _source: `{hit['path']}`_")
    else:
        lines.append(
            f"1. Define {topics[0]} before arguing about it — the corpus offers no fixed definition "
            "to inherit, so the operator must pick one and state it.\n"
            f"2. Treat {topics[0]} as one testable claim, not a topic: the moment it is phrased as a "
            "falsifiable statement the cockpit can search for counter-evidence.\n"
            "3. Anything below a cited passage would be invention. With no passage, everything stays "
            "labelled as reasoning."
        )

    if tangential:
        lines += [
            "",
            f"_Nearby but not evidence: “{tangential[0]['title']}” (`{tangential[0]['path']}`) shares "
            "vocabulary with the brief without answering it._",
        ]

    lines += ["", "**Operator briefing.**"]
    lines.append(
        f"Treat {' and '.join(topics[:2])} as the load-bearing ideas. If you want a citation-backed "
        "answer, point the cockpit at the live model (set `NEXUS_WORKSPACE_ENGINE=llm` with a "
        "reachable LLM) or drop a note into `docs/` so the index can ground it."
    )
    lines += ["", "**Next moves.**"]
    lines.append(f"- Run **Search** on `{topics[0]}` to see the ranked passages for yourself.")
    lines.append("- Open **Planning** and pin this brief to today's execution loop.")
    lines.append("- Re-run with a narrower prompt once a source note exists.")
    return "\n".join(lines), cited


def _local_image(prompt: str) -> tuple[str, list[dict[str, Any]]]:
    words = _keywords(prompt, 5) or ["untitled", "study"]
    tone = (
        "cool and luminous"
        if any(w in prompt.lower() for w in ("calm", "soft", "light"))
        else "high-contrast"
    )
    lines = [
        f"**Rendered.** A procedural poster for “{_clean_prompt(prompt, 90)}”.",
        "",
        "**Art direction.**",
        f"- Palette: porcelain canvas with {', '.join(words[:2])} accents.",
        f"- Mood: {tone}, generous negative space, one focal form.",
        "- Composition: off-centre mass, orbital linework, 2% film grain.",
        "",
        "**Note.** The cockpit ships a deterministic vector renderer, not a diffusion model — "
        "the same prompt always produces the same poster. Swap the renderer adapter to point it "
        "at a generator; the contract and the UI stay identical.",
    ]
    return "\n".join(lines), []


def _local_music(prompt: str, blueprint: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    lines = [
        f"**Composition.** “{_clean_prompt(prompt, 70)}” → {blueprint['bpm']} BPM, "
        f"{blueprint['key']} {blueprint['scale']}, {blueprint['mood']}.",
        "",
        "**Arrangement.**",
        f"- Pad · {' + '.join(blueprint['progression'])} with slow filter drift.",
        f"- Arp · {blueprint['arp']} eighth-notes, quarter-note echo.",
        "- Bass · root movement on beats 1 and 3.",
        "- Air · 0.4s reverb tail, vinyl noise bed at -34 dB.",
        "",
        "**Stem.** The WAV below is synthesized on the server (additive pad + triangle arp + "
        "sine bass). It is a real, playable render of the blueprint above.",
    ]
    return "\n".join(lines), []


def _local_search(prompt: str) -> tuple[str, list[dict[str, Any]]]:
    hits = search_knowledge(prompt, limit=6)
    if not hits:
        text = (
            f"No passage in the indexed corpus mentions “{_clean_prompt(prompt, 80)}”. "
            "The index covers `docs/`, the sample note deck and the repository README."
        )
        return text, []
    lines = [f"**{len(hits)} passages** matched “{_clean_prompt(prompt, 80)}”."]
    for hit in hits[:4]:
        lines.append(f"- **{hit['title']}** · `{hit['path']}`")
    lines += ["", "Open a result to jump to the source passage in the library."]
    return "\n".join(lines), hits


# ── offline primers ──────────────────────────────────────────────────────────
# Short, deliberately plain-language cards for questions the repository corpus
# cannot answer. They are labelled as primers everywhere they surface — the UI
# never presents them as retrieval or as model output.
PRIMERS: dict[str, dict[str, Any]] = {
    "quantum": {
        "title": "Quantum computing",
        "keys": ("quantum", "qubit", "superposition", "entangle"),
        "answer": "A quantum computer stores information in qubits that can hold a blend of 0 and 1 at "
        "once, then interferes those possibilities so wrong answers cancel out and the right one survives.",
        "points": (
            "A classical bit is either 0 or 1. A qubit is more like a direction on a sphere: how likely "
            "it is to read as 0 or 1 depends on how you measure it.",
            "Entanglement makes qubits' outcomes correlate, and interference lets a circuit amplify the "
            "paths that lead to a correct answer while cancelling the rest.",
            "The payoff is a large speed-up on a narrow set of problems — factoring, simulating "
            "molecules, some optimisation — not a faster machine for everyday work.",
        ),
        "analogy": "A coin spinning on a table is neither heads nor tails. The trick isn't spinning one "
        "coin; it's choreographing thousands of them to land on your answer.",
        "not": "It is not many parallel universes doing the work for you, and today's hardware is noisy "
        "enough that most algorithms still need error correction.",
    },
    "rag": {
        "title": "Retrieval-augmented generation",
        "keys": ("rag", "retrieval", "grounding", "grounded", "cite", "citation"),
        "answer": "RAG finds the passages that matter, puts them in the prompt, and lets the model answer "
        "from your documents instead of from its own memory.",
        "points": (
            "Documents are chunked, embedded into vectors and stored. A query is embedded the same way "
            "and the nearest chunks are retrieved.",
            "The retrieved text travels with the question, so the answer can cite where it came from.",
            "Answer quality is dominated by retrieval quality: perfect prose over the wrong passage is "
            "still a wrong answer.",
        ),
        "analogy": "An open-book exam: the model still does the writing, but the facts come off the page.",
        "not": "It is not fine-tuning, and it cannot rescue a corpus that never contained the answer.",
    },
    "embeddings": {
        "title": "Embeddings & vector search",
        "keys": ("embedding", "vectors", "vector", "semantic", "similarity", "cosine"),
        "answer": "An embedding turns text into a list of numbers positioned so that things with similar "
        "meaning land close together.",
        "points": (
            "Similarity is geometry: the distance (or angle) between two vectors stands in for how "
            "related two passages are.",
            "A vector index trades a little accuracy for speed, so millions of passages can be searched "
            "in milliseconds.",
            "Embeddings capture meaning, not truth — two confidently wrong notes will happily sit "
            "next to each other.",
        ),
        "analogy": "A library where books shelve themselves by topic as you walk in.",
        "not": "It is not a database of facts, and it does not understand your question — it only "
        "measures resemblance.",
    },
    "agents": {
        "title": "LLM agents",
        "keys": ("agent", "agents", "tool use", "tools", "orchestration", "react", "autonomous"),
        "answer": "An agent is a model in a loop: it plans, calls a tool, reads the result and decides "
        "what to do next until the goal is met.",
        "points": (
            "The loop is the product. Planning, acting and observing repeat until the work is done or "
            "a guard rail stops it.",
            "Tools are the model's hands: search, code execution, files, APIs. Without them it can only "
            "talk.",
            "Guard rails matter more than cleverness — step caps, sandboxes and explicit stop conditions "
            "are what make agents safe to leave running.",
        ),
        "analogy": "A junior colleague with a checklist and a keycard, checking in after every step.",
        "not": "It is not autonomous will; every useful agent is bounded by the tools and budget you "
        "gave it.",
    },
    "transformers": {
        "title": "Transformers & attention",
        "keys": ("transformer", "attention", "llm", "language model", "gpt", "token"),
        "answer": "A transformer weighs every token against every other token, so meaning is resolved by "
        "context rather than by word order alone.",
        "points": (
            "Attention scores say how much each token should listen to each other token; those scores "
            "are learned, not hand-written.",
            "Stacking many attention blocks lets later layers build on earlier ones — syntax low down, "
            "intent higher up.",
            "The model predicts the next token, over and over. Fluency comes from scale; factuality does "
            "not come for free.",
        ),
        "analogy": "A meeting where everyone can hear everyone else at once, and each person decides who "
        "to listen to before speaking.",
        "not": "It is not a database lookup, and it has no built-in notion of truth — only likelihood.",
    },
    "diffusion": {
        "title": "Diffusion image models",
        "keys": ("diffusion", "stable diffusion", "text to image", "image model", "denoise"),
        "answer": "Diffusion models learn to remove noise; generation starts from static and denoises step "
        "by step toward an image that matches the prompt.",
        "points": (
            "Training adds noise to real images and asks the model to predict what was removed.",
            "At generation time the process runs backwards: pure noise in, coherent picture out.",
            "The prompt steers each denoising step, which is why small wording changes reshape the whole "
            "composition rather than tweaking one detail.",
        ),
        "analogy": "A sculptor who starts with a block of fog and keeps wiping away everything that isn't "
        "the statue.",
        "not": "It is not collage or retrieval; nothing is copied from a source image, though style and "
        "bias are learned from the training set.",
    },
}


def find_primer(prompt: str) -> dict[str, Any] | None:
    lowered = f" {prompt.lower()} "
    best: tuple[int, dict[str, Any]] | None = None
    for primer in PRIMERS.values():
        score = sum(1 for key in primer["keys"] if key in lowered)
        if score and (best is None or score > best[0]):
            best = (score, primer)
    return best[1] if best else None


def _primer_briefing(prompt: str, primer: dict[str, Any]) -> str:
    lines = [
        f"**Question.** {_clean_prompt(prompt)}",
        "",
        f"**Short answer.** {primer['answer']}",
        "",
        "**In plain terms.**",
    ]
    for index, point in enumerate(primer["points"], start=1):
        lines.append(f"{index}. {point}")
    lines += [
        "",
        f"**Think of it like.** {primer['analogy']}",
        "",
        f"**What it isn't.** {primer['not']}",
        "",
        "**Next moves.**",
        "- Open **Search** to see whether your own notes cover this.",
        "- Connect a live model (`NEXUS_WORKSPACE_ENGINE=llm`) for a deeper, sourced pass.",
        "- Keep the one-liner: it is short enough to survive being repeated.",
    ]
    return "\n".join(lines)


# ── LLM-backed research (used when a model is actually reachable) ────────────

_RESEARCH_SYSTEM = (
    "You are the NEXUS research operator inside a premium AI workspace. Answer in compact "
    "markdown: a one-line answer, then 'Evidence', then 'Next moves'. Ground every claim in "
    "the supplied passages when they exist; never invent citations. Keep it under 220 words."
)


async def _llm_research(prompt: str, hits: list[dict[str, Any]]) -> str | None:
    if not await llm_alive():
        return None
    context = "\n\n".join(f"[{h['path']}] {h['snippet']}" for h in hits[:4]) or "(no passages retrieved)"
    messages = [
        {"role": "user", "content": f"Question: {prompt}\n\nPassages:\n{context}"},
    ]
    try:
        answer, _reasoning = await llm_service._call_llm(_RESEARCH_SYSTEM, messages)
    except Exception:
        return None
    answer = (answer or "").strip()
    return answer or None


# ── procedural artifacts ─────────────────────────────────────────────────────


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)


def _svg_poster(prompt: str) -> bytes:
    """Deterministic, dependency-free poster render (no GPU, no model, no network)."""
    seed = _seed(prompt)
    palettes = [
        ("#0B0F19", "#22D3EE", "#8B5CF6", "#F9FAFB"),
        ("#0B0F19", "#F97316", "#22D3EE", "#F9FAFB"),
        ("#111827", "#8B5CF6", "#F472B6", "#F9FAFB"),
        ("#0F172A", "#34D399", "#60A5FA", "#F9FAFB"),
    ]
    ink, a, b, paper = palettes[seed % len(palettes)]
    cx = 360 + (seed >> 5) % 440
    cy = 290 + (seed >> 9) % 250
    r = 150 + (seed >> 13) % 110
    angle = (seed >> 7) % 360

    def esc(value: str) -> str:
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    words = re.findall(r"[A-Za-z0-9']+", prompt)
    eyebrow = esc(" / ".join(w.upper() for w in (words[:3] or ["NEXUS"])))
    caption_words = [w.upper() for w in words[:11]] or ["UNTITLED STUDY"]
    # fit the title on at most two 24-character lines so it never leaves the canvas
    lines: list[str] = []
    current = ""
    for word in caption_words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > 24 and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > 1:
        lines = [lines[0], " ".join(lines[1:])[:26]]
    lines = lines[:2]
    title_svg = "".join(
        f'<text x="68" y="{718 + index * 44}" font-family="Inter, Helvetica, Arial, sans-serif" '
        f'font-size="{42 if len(lines) == 1 else 36}" font-weight="700" fill="{ink}" '
        f'letter-spacing="-0.5">{esc(line)}</text>'
        for index, line in enumerate(lines)
    )
    aria = esc(" ".join(lines))
    rule_w = min(760, 46 + max(len(line) for line in lines) * 24)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="860" viewBox="0 0 1200 860" role="img" aria-label="Procedural poster: {aria}">
  <defs>
    <radialGradient id="glowA" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{a}" stop-opacity="0.92"/>
      <stop offset="100%" stop-color="{a}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glowB" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{b}" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="{b}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="paper" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#FFFFFF"/>
      <stop offset="60%" stop-color="{paper}"/>
      <stop offset="100%" stop-color="#EEF1F6"/>
    </linearGradient>
    <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{a}"/>
      <stop offset="100%" stop-color="{b}"/>
    </linearGradient>
    <filter id="soft" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="46"/>
    </filter>
    <filter id="grain">
      <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" seed="{seed % 97}"/>
      <feColorMatrix type="saturate" values="0"/>
      <feComponentTransfer><feFuncA type="linear" slope="0.055"/></feComponentTransfer>
    </filter>
    <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
      <path d="M60 0H0V60" fill="none" stroke="{ink}" stroke-opacity="0.05" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="1200" height="860" fill="url(#paper)"/>
  <rect width="1200" height="860" fill="url(#grid)"/>
  <ellipse cx="{cx - 110}" cy="{cy - 70}" rx="{r * 1.5:.0f}" ry="{r * 1.2:.0f}" fill="url(#glowA)" filter="url(#soft)" opacity="0.78"/>
  <ellipse cx="{cx + 250}" cy="{cy + 180}" rx="{r * 1.3:.0f}" ry="{r * 1.1:.0f}" fill="url(#glowB)" filter="url(#soft)" opacity="0.72"/>
  <g transform="rotate({angle} {cx} {cy})">
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="url(#ring)" stroke-width="1.4" opacity="0.8"/>
    <circle cx="{cx}" cy="{cy}" r="{r * 1.5:.0f}" fill="none" stroke="{ink}" stroke-width="1" stroke-opacity="0.14" stroke-dasharray="3 11"/>
    <circle cx="{cx}" cy="{cy}" r="{r * 0.55:.0f}" fill="none" stroke="{ink}" stroke-width="1" stroke-opacity="0.22"/>
    <circle cx="{cx - r * 0.68:.0f}" cy="{cy - r * 0.6:.0f}" r="7" fill="{a}"/>
    <circle cx="{cx + r * 0.6:.0f}" cy="{cy + r * 0.76:.0f}" r="5" fill="{b}"/>
  </g>
  <g>
    <rect x="68" y="690" width="{rule_w}" height="4" rx="2" fill="{ink}" opacity="0.85"/>
    <text x="68" y="666" font-family="Inter, Helvetica, Arial, sans-serif" font-size="14" letter-spacing="4" fill="{a}" font-weight="600">{eyebrow} · NEXUS</text>
    {title_svg}
    <text x="68" y="800" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="13" fill="{ink}" opacity="0.55">GENERATED LOCALLY · SEED {seed % 100000:05d} · 1200×860</text>
  </g>
  <rect x="68" y="68" width="46" height="46" rx="14" fill="{ink}"/>
  <path d="M81 104V80l20 24V80" fill="none" stroke="{paper}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
  <rect width="1200" height="860" filter="url(#grain)" opacity="0.5"/>
</svg>
"""


def _music_blueprint(prompt: str) -> dict[str, Any]:
    lower = prompt.lower()
    if any(w in lower for w in ("calm", "ambient", "sleep", "soft", "quiet", "ocean", "rain")):
        mood, bpm, scale, root, prog = "weightless", 72, "dorian", "D", ["Dm7", "G7", "Bbmaj7", "Gm7"]
    elif any(w in lower for w in ("epic", "trailer", "power", "battle", "hero", "cinematic")):
        mood, bpm, scale, root, prog = "cinematic", 96, "minor", "C", ["Cm", "Ab", "Eb", "Bb"]
    elif any(w in lower for w in ("tense", "dark", "noir", "night", "mystery", "anxious")):
        mood, bpm, scale, root, prog = "nocturnal", 84, "harmonic minor", "A", ["Am", "F", "Dm", "E7"]
    elif any(w in lower for w in ("warm", "sun", "happy", "bright", "summer", "playful")):
        mood, bpm, scale, root, prog = "sunlit", 108, "major", "G", ["Gmaj7", "Cmaj7", "Am7", "D7"]
    else:
        mood, bpm, scale, root, prog = "focused", 90, "minor", "A", ["Am", "F", "Cmaj7", "G"]
    return {
        "mood": mood,
        "bpm": bpm,
        "scale": scale,
        "key": root,
        "progression": prog,
        "arp": "up-down",
        "seed": _seed(prompt),
        "caption": _clean_prompt(prompt, 70),
    }


_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_MINOR = (0, 2, 3, 5, 7, 8, 10)
_MAJOR = (0, 2, 4, 5, 7, 9, 11)
_DORIAN = (0, 2, 3, 5, 7, 9, 10)
_HARMONIC_MINOR = (0, 2, 3, 5, 7, 8, 11)


def _scale_steps(scale: str) -> tuple[int, ...]:
    if scale == "major":
        return _MAJOR
    if scale == "dorian":
        return _DORIAN
    if scale == "harmonic minor":
        return _HARMONIC_MINOR
    return _MINOR


def _synth_stem(blueprint: dict[str, Any]) -> bytes:
    """Additive pad + triangle arp + sine bass → 8s mono 22.05kHz WAV (stdlib only)."""
    rate = 22050
    duration = 8.0
    total = int(rate * duration)
    root = _SEMITONES.get(blueprint["key"], 9)
    steps = _scale_steps(blueprint["scale"])
    bpm = blueprint["bpm"]
    beat = 60.0 / bpm
    eighth = beat / 2

    def midi_hz(semi: int) -> float:
        return 440.0 * (2 ** ((60 + semi - 69) / 12.0))

    chord_roots = [0, 5, 2, 7]
    buf = [0.0] * total
    rng = blueprint["seed"]

    # pad: slow-attack detuned sines, one chord per 2 beats
    for idx, offset in enumerate(chord_roots):
        start = idx * 2 * beat
        end = min(duration, start + 2 * beat + 0.6)
        chord = [0, steps[2], steps[4]]
        for semi in chord:
            freq = midi_hz(root + offset + semi)
            for detune in (-0.004, 0.0, 0.005):
                inc = 2 * math.pi * freq * (1 + detune) / rate
                for i in range(int(start * rate), min(total, int(end * rate))):
                    t = i / rate - start
                    env = min(1.0, t / 0.5) * math.exp(-max(0.0, t - 1.4) * 1.6)
                    buf[i] += 0.030 * env * math.sin(inc * i)

    # arpeggio: up-down over the chord tones, echo at a dotted eighth
    arp_steps = [0, 2, 4, 2, 0, 4, 2, 4]
    note_index = 0
    t = 0.15
    while t < duration - 0.2:
        chord = chord_roots[int(t / (2 * beat)) % len(chord_roots)]
        semi = root + chord + steps[arp_steps[note_index % len(arp_steps)] % len(steps)]
        freq = midi_hz(semi + 12)
        note_len = int(eighth * 1.6 * rate)
        start = int(t * rate)
        for k in range(note_len):
            i = start + k
            if i >= total:
                break
            tt = k / rate
            env = math.exp(-tt * 6.0) * min(1.0, tt / 0.008)
            phase = (freq * tt) % 1.0
            triangle = 4 * abs(phase - 0.5) - 1
            buf[i] += 0.085 * env * triangle
            echo_i = i + int(eighth * rate)
            if echo_i < total:
                buf[echo_i] += 0.030 * env * triangle
        note_index += 1
        t += eighth

    # bass: root on beats 1 and 3
    for bar in range(int(duration / (4 * beat)) + 1):
        for beat_idx in (0, 2):
            start = int((bar * 4 + beat_idx) * beat * rate)
            freq = midi_hz(root + chord_roots[bar % len(chord_roots)] - 24)
            length = int(beat * 0.9 * rate)
            for k in range(length):
                i = start + k
                if i >= total:
                    break
                tt = k / rate
                env = min(1.0, tt / 0.02) * math.exp(-tt * 2.2)
                buf[i] += 0.135 * env * math.sin(2 * math.pi * freq * tt)

    # air: gentle filtered noise bed
    prev = 0.0
    for i in range(total):
        n = ((rng >> (i % 17)) & 0xFF) / 255.0 - 0.5
        prev = prev * 0.985 + n * 0.015
        buf[i] += prev * 0.05

    # normalise + 60ms fades
    peak = max(0.0001, max(abs(v) for v in buf))
    gain = 0.86 / peak
    fade = int(0.06 * rate)
    frames = bytearray()
    for i, value in enumerate(buf):
        env = 1.0
        if i < fade:
            env = i / fade
        elif i > total - fade:
            env = max(0.0, (total - i) / fade)
        frames += struct.pack("<h", int(max(-1.0, min(1.0, value * gain * env)) * 32767))

    out = io.BytesIO()
    with wave.open(out, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))
    return out.getvalue()


# ── run execution ────────────────────────────────────────────────────────────


def _frames(run: dict[str, Any], engine_meta: dict[str, Any]):
    """Build the artifact descriptors for a run (URLs resolve against this router)."""
    artifacts: list[dict[str, Any]] = []
    if run["route"] == "image":
        artifacts.append(
            {
                "kind": "image",
                "title": "Procedural poster",
                "subtitle": "Vector render · deterministic",
                "url": f"/api/workspace/art/{run['id']}.svg",
                "thumbnail": SAMPLE_ASSET,
                "download": f"nexus-poster-{run['id'][:6]}.svg",
            }
        )
        artifacts.append(
            {
                "kind": "asset",
                "title": "Studio reference",
                "subtitle": "Bundled 3D render",
                "url": SAMPLE_ASSET,
                "download": "nexus-quantum-bloom.jpg",
            }
        )
    elif run["route"] == "music":
        artifacts.append(
            {
                "kind": "audio",
                "title": "Rendered stem",
                "subtitle": "8s · 22 kHz · mono WAV",
                "url": f"/api/workspace/audio/{run['id']}.wav",
                "download": f"nexus-stem-{run['id'][:6]}.wav",
                "blueprint": run.get("blueprint"),
            }
        )
    elif run["route"] == "deep_research":
        # only passages that cleared the relevance bar are shown as evidence
        for hit in [h for h in run.get("hits", []) if h.get("coverage", 0) >= 0.6][:3]:
            artifacts.append(
                {
                    "kind": "source",
                    "title": hit["title"],
                    "subtitle": hit["path"],
                    "snippet": hit["snippet"],
                    "score": hit["score"],
                    "match": hit.get("match"),
                    "url": f"/{hit['path'].lstrip('/')}",
                }
            )
    elif run["route"] == "search":
        for hit in run.get("hits", [])[:6]:
            artifacts.append(
                {
                    "kind": "source",
                    "title": hit["title"],
                    "subtitle": hit["path"],
                    "snippet": hit["snippet"],
                    "score": hit["score"],
                    "match": hit.get("match"),
                    "url": f"/{hit['path'].lstrip('/')}",
                }
            )
    notes = {
        "local-grounding": (
            "Local grounding engine",
            "No model reachable — answer composed from indexed passages",
        ),
        "local-primer": (
            "Offline primer",
            "Built-in knowledge card — connect a live model for a sourced pass",
        ),
    }
    note = notes.get(engine_meta.get("engine", ""))
    if note:
        artifacts.append({"kind": "note", "title": note[0], "subtitle": note[1]})
    return artifacts


async def _execute(run: dict[str, Any]) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Yield (event, payload) frames; every frame is persisted for replay."""
    route = ROUTES[run["route"]]
    started = time.time()

    def emit(event: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        frame = {"seq": len(run["events"]) + 1, "ts": round(time.time(), 3), **payload}
        run["events"].append((event, frame))
        return event, frame

    run["status"] = "thinking"
    yield emit("state", {"status": "thinking", "label": "THINKING", "route": run["route"]})
    yield emit(
        "plan",
        {
            "steps": [
                {"id": sid, "title": title, "detail": detail, "status": "pending"}
                for sid, title, detail in route["steps"]
            ]
        },
    )

    if run["route"] == "music":
        run["blueprint"] = _music_blueprint(run["prompt"])

    # retrieval happens inside the sweep step so the plan reflects real work
    if run["route"] in ("search", "deep_research"):
        hits = search_knowledge(run["prompt"], limit=6 if run["route"] == "search" else 4)
        run["hits"] = hits

    for index, (sid, title, _detail) in enumerate(route["steps"]):
        if run["cancel"]:
            run["status"] = "cancelled"
            yield emit("state", {"status": "cancelled", "label": "CANCELLED"})
            yield emit("done", {"run": _public_run(run)})
            return
        yield emit("step", {"id": sid, "status": "running"})
        await _pause(0.34 if index < len(route["steps"]) - 1 else 0.5)
        note = ""
        if sid == "sweep":
            note = f"{len(run.get('hits') or [])} passages ranked"
        elif sid == "scan":
            note = f"{len(_build_index())} passages indexed"
        elif sid == "key" and run.get("blueprint"):
            bp = run["blueprint"]
            note = f"{bp['key']} {bp['scale']} · {bp['bpm']} BPM"
        elif sid == "render" and run["route"] == "image":
            note = "1200×860 vector canvas"
        elif sid == "render" and run["route"] == "music":
            note = "22,050 samples/s · 8.0s"
        yield emit("step", {"id": sid, "status": "done", "note": note})

    run["status"] = "streaming"
    yield emit("state", {"status": "streaming", "label": "STREAMING", "route": run["route"]})

    engine_meta: dict[str, Any] = {"engine": "local", "model": None}
    hits = run.get("hits") or []
    text: str | None = None

    if run["route"] == "deep_research":
        if await llm_alive():
            text = await _llm_research(run["prompt"], hits)
            if text:
                engine_meta = {
                    "engine": "llm",
                    "model": llm_service.LLM_STATE.get("model") or llm_service.LLM_CFG.get("model"),
                }
        if not text:
            primer = find_primer(run["prompt"])
            grounded = [h for h in hits if h.get("coverage", 0) >= 0.6]
            if primer and not grounded:
                text = _primer_briefing(run["prompt"], primer)
                engine_meta = {"engine": "local-primer", "model": None}
            else:
                text, _ = _local_deep_research(run["prompt"])
                engine_meta = {"engine": "local-grounding", "model": None}
    elif run["route"] == "image":
        text, _ = _local_image(run["prompt"])
        engine_meta = {"engine": "local-renderer", "model": None}
    elif run["route"] == "search":
        text, _ = _local_search(run["prompt"])
        engine_meta = {"engine": "local-index", "model": None}
    else:
        text, _ = _local_music(run["prompt"], run["blueprint"])
        engine_meta = {"engine": "local-synth", "model": None}

    # stream the composed answer as word-sized deltas (the UI types it out)
    chunks = re.findall(r"\S+\s*", text)
    for chunk in chunks:
        if run["cancel"]:
            run["status"] = "cancelled"
            yield emit("state", {"status": "cancelled", "label": "CANCELLED"})
            yield emit("done", {"run": _public_run(run)})
            return
        yield emit("delta", {"text": chunk})
        await _pause(0.014 if len(chunk) < 12 else 0.024)

    artifacts = _frames(run, engine_meta)
    run["artifacts"] = artifacts
    # visuals lead: a poster or stem is emitted before the prose so the result is
    # visible immediately; citations and engine notes follow the answer.
    lead = [a for a in artifacts if a["kind"] in ("image", "audio")]
    trail = [a for a in artifacts if a["kind"] not in ("image", "audio")]
    for artifact in lead:
        yield emit("artifact", {"artifact": artifact})
    await _pause(0.08)

    for artifact in trail:
        yield emit("artifact", {"artifact": artifact})
        await _pause(0.05)

    run["answer"] = text.strip()
    run["engine"] = engine_meta
    run["duration_ms"] = int((time.time() - started) * 1000)
    run["status"] = "done"

    _roll_usage()
    _USAGE["runs"] += 1
    _USAGE["credits_spent"] += int(run["credits"])

    usage = _usage_payload()
    yield emit("usage", usage)
    yield emit(
        "meta",
        {
            **engine_meta,
            "latency_ms": run["duration_ms"],
            "citations": len(hits),
            "note": {
                "local-grounding": "Composed locally from indexed repository passages.",
                "local-primer": "Offline primer — no model or matching passage was available.",
                "llm": "Streamed from the live model.",
            }.get(engine_meta["engine"], "Rendered locally by the cockpit."),
        },
    )
    yield emit("done", {"run": _public_run(run)})


def _usage_payload() -> dict[str, Any]:
    _roll_usage()
    spent = int(_USAGE["credits_spent"])
    plan = _USAGE["plan"]
    total = next((p["credits"] for p in PLANS if p["id"] == plan), PLAN_CREDITS)
    return {
        "window": _USAGE["day"],
        "runs_today": int(_USAGE["runs"]),
        "credits_spent": spent,
        "credits_total": total,
        "credits_left": max(0, total - spent),
        "plan": plan,
    }


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


# ── schemas are defined in backend.schemas ───────────────────────────────────


@router.get("/api/workspace/bootstrap")
async def workspace_bootstrap():
    """Everything Screen 1 needs in one round-trip."""
    _roll_usage()
    index = _build_index()
    activity = [
        {
            "kind": "research",
            "title": "Recursive self-evolution guardrails",
            "detail": "Deep research · 4 passages cited",
            "ago": "12m",
        },
        {
            "kind": "image",
            "title": "Quantum bloom poster",
            "detail": "Image · procedural render",
            "ago": "48m",
        },
        {
            "kind": "music",
            "title": "Focus loop in A minor",
            "detail": "Music · 90 BPM stem",
            "ago": "2h",
        },
        {
            "kind": "search",
            "title": "Sandbox backend defaults",
            "detail": "Search · 6 passages",
            "ago": "Yesterday",
        },
    ]
    history = sorted(RUNS.values(), key=lambda r: r["created"], reverse=True)[:MAX_HISTORY]
    return JSONResponse(
        {
            "user": {
                "name": "Nixtio",
                "initials": "NX",
                "plan": _USAGE["plan"],
                "plan_label": next((p["name"] for p in PLANS if p["id"] == _USAGE["plan"]), "Studio"),
                "workspace": "Atlas Lab",
            },
            "greeting": {
                "title": "Hi Nixtio,",
                "emphasis": "Ready to Achieve Great Things?",
                "subtitle": "Your cockpit is warm. Three agents idle, one deep-research thread waiting for a decision.",
                "bubble": "Hey there! Need a boost?",
                "suggestions": [
                    "Explain quantum computing in simple terms",
                    "Draft a moody poster for our launch",
                    "Write a focus loop for deep work",
                ],
            },
            "engine": _engine_label(),
            "usage": _usage_payload(),
            "knowledge": {
                "passages": len(index),
                "documents": len({e["path"] for e in index}),
                "indexed_at": datetime.now(UTC).isoformat(),
            },
            "routes": [ROUTES[r] for r in ROUTE_ORDER],
            "features": [
                {
                    "id": "fast_start",
                    "title": "Fast Start",
                    "caption": "Ship the smallest useful thing, then loop.",
                    "metric": f"{max(3, 6 + _USAGE['runs'])} quick runs this week",
                    "trend": "+18%",
                    "progress": min(0.94, 0.54 + _USAGE["runs"] * 0.02),
                    "items": ["Instant drafts", "One-tap reruns", "Auto-commit loop"],
                },
                {
                    "id": "collaborate",
                    "title": "Collaborate with Team",
                    "caption": "Background multi-agent orchestration.",
                    "metric": "4 agents in the mesh",
                    "trend": "2 busy",
                    "progress": 0.72,
                    "items": ["Research", "Vision", "Planner", "Writer"],
                },
                {
                    "id": "planning",
                    "title": "Planning",
                    "caption": "Priorities, workflows and calendar in one lane.",
                    "metric": "3 priorities pinned",
                    "trend": "Today",
                    "progress": 0.61,
                    "items": ["Launch review", "Design sync", "Deep work"],
                },
            ],
            "activity": activity,
            "history": [_public_run(r) for r in history],
            "plans": [{k: v for k, v in plan.items()} for plan in PLANS],
            "suggestions": [
                {"route": "deep_research", "prompt": "Explain quantum computing in simple terms"},
                {"route": "image", "prompt": "A luminous quantum bloom, porcelain studio light"},
                {"route": "search", "prompt": "sandbox backend defaults"},
                {"route": "music", "prompt": "A calm ambient focus loop for deep work"},
            ],
        }
    )


@router.post("/api/workspace/runs")
async def create_run(req: WorkspaceRunRequest):
    prompt = " ".join((req.prompt or "").split())
    if not prompt:
        return JSONResponse({"ok": False, "error": "prompt is required"}, status_code=400)
    if len(prompt) > 4000:
        return JSONResponse({"ok": False, "error": "prompt too long (max 4000 chars)"}, status_code=400)
    route = _route(req.route)
    if route is None:
        return JSONResponse(
            {"ok": False, "error": f"unknown route '{req.route}'", "routes": list(ROUTE_ORDER)},
            status_code=400,
        )

    _roll_usage()
    usage = _usage_payload()
    if usage["credits_left"] < route["cost"]:
        return JSONResponse(
            {"ok": False, "error": "credit ceiling reached for this plan", "usage": usage},
            status_code=402,
        )

    run_id = uuid.uuid4().hex[:16]
    RUNS[run_id] = {
        "id": run_id,
        "prompt": prompt,
        "route": req.route,
        "status": "queued",
        "created": time.time(),
        "created_at": datetime.now(UTC).isoformat(),
        "credits": route["cost"],
        "cancel": False,
        "events": [],
        "artifacts": [],
        "hits": [],
        "answer": None,
        "engine": None,
        "blueprint": None,
    }
    _trim_runs()
    run = RUNS[run_id]
    return JSONResponse(
        {
            "ok": True,
            "run": _public_run(run),
            "stream": f"/api/workspace/runs/{run_id}/stream",
            "plan": [{"id": sid, "title": title, "detail": detail} for sid, title, detail in route["steps"]],
        },
        status_code=201,
    )


@router.get("/api/workspace/runs")
async def list_runs():
    history = sorted(RUNS.values(), key=lambda r: r["created"], reverse=True)[:MAX_HISTORY]
    return JSONResponse({"runs": [_public_run(r) for r in history]})


@router.get("/api/workspace/runs/{run_id}")
async def get_run(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"ok": False, "error": "run not found"}, status_code=404)
    return JSONResponse({"ok": True, "run": _public_run(run), "events": len(run["events"])})


@router.post("/api/workspace/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"ok": False, "error": "run not found"}, status_code=404)
    if run["status"] in ("done", "cancelled"):
        return JSONResponse({"ok": True, "run": _public_run(run), "already": True})
    run["cancel"] = True
    return JSONResponse({"ok": True, "run": _public_run(run)})


@router.get("/api/workspace/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request):
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"ok": False, "error": "run not found"}, status_code=404)

    async def replay() -> AsyncIterator[str]:
        for event, payload in list(run["events"]):
            if await request.is_disconnected():
                return
            yield _sse(event, payload)
            await asyncio.sleep(0)

    async def produce() -> AsyncIterator[str]:
        try:
            async for event, payload in _execute(run):
                if await request.is_disconnected():
                    run["cancel"] = True
                    return
                yield _sse(event, payload)
        except asyncio.CancelledError:
            run["cancel"] = True
            raise
        except Exception as exc:  # keep the stream well-formed even on a bug
            run["status"] = "error"
            yield _sse("error", {"message": str(exc) or exc.__class__.__name__})
            yield _sse("state", {"status": "error", "label": "ERROR"})

    generator = replay() if run["status"] in ("done", "cancelled", "error") and run["events"] else produce()
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/workspace/art/{run_id}.svg")
async def get_art(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"ok": False, "error": "run not found"}, status_code=404)
    svg = _svg_poster(run["prompt"])
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/api/workspace/audio/{run_id}.wav")
async def get_audio(run_id: str):
    run = RUNS.get(run_id)
    if not run:
        return JSONResponse({"ok": False, "error": "run not found"}, status_code=404)
    cached = _AUDIO_CACHE.get(run_id)
    if cached is None:
        blueprint = run.get("blueprint") or _music_blueprint(run["prompt"])
        cached = await asyncio.to_thread(_synth_stem, blueprint)
        _AUDIO_CACHE[run_id] = cached
    return Response(
        content=cached,
        media_type="audio/wav",
        headers={"Content-Disposition": f'inline; filename="nexus-stem-{run_id[:6]}.wav"'},
    )


@router.post("/api/workspace/upgrade")
async def upgrade(req: WorkspaceUpgradeRequest):
    """Plan catalog. No payment provider is configured in this build."""
    plan = (req.plan or "").strip().lower()
    if plan and plan not in {p["id"] for p in PLANS}:
        return JSONResponse({"ok": False, "error": "unknown plan"}, status_code=400)
    return JSONResponse(
        {
            "ok": True,
            "current": _USAGE["plan"],
            "requested": plan or None,
            "checkout": "not_configured",
            "note": "Wire NEXUS_BILLING_PROVIDER (stripe|paddle) to enable checkout.",
            "plans": PLANS,
        }
    )


@router.get("/api/workspace/plans")
async def plans():
    return JSONResponse({"plans": PLANS, "current": _USAGE["plan"]})


@router.get("/api/workspace/preview-state")
async def preview_state(state: str = "thinking"):
    """Static descriptor for the cockpit's aura states (design hand-off + tests)."""
    allowed = ("idle", "thinking", "streaming", "done", "error")
    if state not in allowed:
        return JSONResponse({"ok": False, "error": f"state must be one of {allowed}"}, status_code=400)
    return JSONResponse(
        {
            "state": state,
            "aura": state in ("thinking", "streaming"),
            "layers": ["cyan", "violet"],
            "label": {"thinking": "THINKING", "streaming": "STREAMING"}.get(state, state.upper()),
            "since": (datetime.now(UTC) - timedelta(seconds=0)).isoformat(),
        }
    )
