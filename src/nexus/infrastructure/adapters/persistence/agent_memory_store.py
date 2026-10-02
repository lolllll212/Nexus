"""Content-addressable agent memory store (Conflux-style).

A deterministic, local-first state store for multi-agent coordination.
Agents append immutable chunks once; other agents pull only the diffs or
semantically relevant chunks they need instead of re-reading raw history.

Conflux laws honored here:
- Content-addressable identity: a chunk's id is the SHA-256 of its canonical
  JSON body, so identical content always collapses to one entry (idempotent puts).
- Order independence: every listing sorts by (tick, id) canonical ordering.
- Append-only: chunks are never mutated; corrections are new chunks with `refs`.
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")

_STOP_WORDS = frozenset(
    "the a an and or of to in is are was were for on with as by at from this that "
    "it be has have had not but if then than so we you i they he she do does did "
    "into onto over under again further once here there when where why how all any "
    "both each few more most other some such no nor only own same too very can will "
    "just should now also its our your".split()
)


def canonical_json(body: dict[str, Any]) -> str:
    """Deterministic serialization: sorted keys, no whitespace."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class Chunk:
    """An immutable, content-addressed memory chunk."""

    agent: str
    kind: str
    text: str
    tags: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)
    id: str = ""
    tick: int = 0
    created_at: str = ""
    embedding: list[float] = field(default_factory=list)

    def body(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "kind": self.kind,
            "text": self.text,
            "tags": sorted(self.tags),
            "refs": sorted(self.refs),
        }

    def compute_id(self) -> str:
        return hashlib.sha256(canonical_json(self.body()).encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tick": self.tick,
            "agent": self.agent,
            "kind": self.kind,
            "text": self.text,
            "tags": sorted(self.tags),
            "refs": sorted(self.refs),
            "created_at": self.created_at,
            "embedding": list(self.embedding),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Chunk:
        return cls(
            agent=d["agent"],
            kind=d["kind"],
            text=d["text"],
            tags=list(d.get("tags", [])),
            refs=list(d.get("refs", [])),
            id=d["id"],
            tick=d.get("tick", 0),
            created_at=d.get("created_at", ""),
            embedding=list(d.get("embedding", [])),
        )


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, stop words removed. Deterministic order."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP_WORDS]


def _term_freq(tokens: list[str]) -> dict[str, float]:
    tf: dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0.0) + 1.0
    n = max(len(tokens), 1)
    return {t: c / n for t, c in tf.items()}


class AgentMemoryStore:
    """Local content-addressable store over a JSON file.

    The file lives in the main worktree (callers pass the rendezvous path) so
    every linked worktree shares one store. All reads sort canonically; writes
    are idempotent by content hash.
    """

    def __init__(self, path: Path, embedder: Any | None = None, alpha: float = 0.7) -> None:
        self.path = Path(path)
        self._chunks: dict[str, Chunk] = {}
        self._tick = 0
        self._embedder = embedder
        self._alpha = alpha
        self._load()

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        length = min(len(a), len(b))
        if length == 0:
            return 0.0
        dot = sum(x * y for x, y in zip(a[:length], b[:length]))
        norm_a = math.sqrt(sum(x * x for x in a[:length])) or 1.0
        norm_b = math.sqrt(sum(y * y for y in b[:length])) or 1.0
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _run_embedder_sync(self, text: str) -> list[float]:
        return asyncio.run(self._embedder.embed(text))

    def _embed_text(self, text: str) -> list[float]:
        if self._embedder is None:
            return []

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._embedder.embed(text))

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(self._run_embedder_sync, text).result()

    def _normalized_embedding(self, chunk: Chunk) -> list[float]:
        if chunk.embedding:
            return chunk.embedding
        if not self._embedder:
            return []
        try:
            chunk.embedding = self._embed_text(chunk.text)
        except Exception:
            chunk.embedding = []
        return chunk.embedding

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for d in data.get("chunks", []):
            chunk = Chunk.from_dict(d)
            self._chunks[chunk.id] = chunk
        self._tick = data.get("next_tick", len(self._chunks) + 1)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        chunks = sorted(self._chunks.values(), key=lambda c: (c.tick, c.id))
        data = {
            "chunks": [c.to_dict() for c in chunks],
            "next_tick": self._tick,
        }
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def put(
        self,
        agent: str,
        kind: str,
        text: str,
        tags: list[str] | None = None,
        refs: list[str] | None = None,
        created_at: str = "",
    ) -> tuple[Chunk, bool]:
        """Append a chunk. Returns (chunk, created) - created=False when the
        identical content was already stored (same id)."""
        chunk = Chunk(agent=agent, kind=kind, text=text, tags=tags or [], refs=refs or [])
        chunk.id = chunk.compute_id()
        existing = self._chunks.get(chunk.id)
        if existing is not None:
            return existing, False
        self._tick += 1
        chunk.tick = self._tick
        chunk.created_at = created_at
        if self._embedder is not None:
            try:
                chunk.embedding = self._embed_text(chunk.text)
            except Exception:
                chunk.embedding = []
        self._chunks[chunk.id] = chunk
        self._save()
        return chunk, True

    def get(self, chunk_id: str) -> Chunk | None:
        return self._chunks.get(chunk_id)

    def _df(self, chunks: list[Chunk]) -> dict[str, int]:
        df: dict[str, int] = {}
        for c in chunks:
            for t in set(tokenize(c.text)):
                df[t] = df.get(t, 0) + 1
        return df

    def query(
        self,
        q: str,
        k: int = 5,
        kind: str | None = None,
        agent: str | None = None,
        alpha: float | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Top-k chunks via hybrid semantic + TF-IDF scoring.

        With an active `EmbeddingProvider`, scores combine semantic cosine and TF-IDF
        similarity. When the embedder is unavailable or fails, the method falls back
        to plain TF-IDF scoring to preserve deterministic retrieval.
        """
        candidates = [
            c
            for c in self._chunks.values()
            if (kind is None or c.kind == kind) and (agent is None or c.agent == agent)
        ]
        if not candidates:
            return []
        if alpha is None:
            alpha = self._alpha
        alpha = max(0.0, min(1.0, float(alpha)))

        df = self._df(candidates)
        n_docs = len(candidates)
        q_tf = _term_freq(tokenize(q))

        def _idf(t: str) -> float:
            return math.log((n_docs + 1) / (df.get(t, 0) + 1)) + 1.0

        q_vec = {t: f * _idf(t) for t, f in q_tf.items()}
        q_norm = sum(v * v for v in q_vec.values()) ** 0.5 or 1.0

        tfidf_scores: dict[str, float] = {}
        for c in candidates:
            c_tf = _term_freq(tokenize(c.text))
            c_vec = {t: f * _idf(t) for t, f in c_tf.items()}
            dot = sum(q_vec.get(t, 0.0) * v for t, v in c_vec.items())
            c_norm = sum(v * v for v in c_vec.values()) ** 0.5 or 1.0
            score = dot / (q_norm * c_norm) if q_norm and c_norm else 0.0
            tfidf_scores[c.id] = score

        if self._embedder is not None:
            query_embedding = []
            try:
                query_embedding = self._embed_text(q)
            except Exception:
                query_embedding = []
            if query_embedding:
                hybrid: list[tuple[Chunk, float]] = []
                for c in candidates:
                    chunk_embedding = self._normalized_embedding(c)
                    semantic_score = self._cosine_similarity(query_embedding, chunk_embedding)
                    tfidf = tfidf_scores.get(c.id, 0.0)
                    score = alpha * semantic_score + (1.0 - alpha) * tfidf
                    hybrid.append((c, score))
                hybrid.sort(key=lambda pair: (-pair[1], pair[0].tick, pair[0].id))
                return hybrid[:k]

        scored = [(c, tfidf_scores.get(c.id, 0.0)) for c in candidates if tfidf_scores.get(c.id, 0.0) > 0.0]
        scored.sort(key=lambda pair: (-pair[1], pair[0].tick, pair[0].id))
        return scored[:k]

    def latest(self, kind: str | None = None, n: int = 10) -> list[Chunk]:
        chunks = [c for c in self._chunks.values() if kind is None or c.kind == kind]
        chunks.sort(key=lambda c: (-c.tick, c.id))
        return chunks[:n]

    def diff(self, from_id: str, to_id: str, context_lines: int = 3) -> str | None:
        """Unified diff between two chunk texts. None if either id is unknown."""
        a = self._chunks.get(from_id)
        b = self._chunks.get(to_id)
        if a is None or b is None:
            return None
        return "\n".join(
            difflib.unified_diff(
                a.text.splitlines(),
                b.text.splitlines(),
                fromfile=f"{from_id} ({a.kind})",
                tofile=f"{to_id} ({b.kind})",
                lineterm="",
                n=context_lines,
            )
        )

    def prune(self, max_chunks: int) -> int:
        """Keep the newest max_chunks (by tick). Deterministic. Returns removed count."""
        if len(self._chunks) <= max_chunks:
            return 0
        ordered = sorted(self._chunks.values(), key=lambda c: (c.tick, c.id))
        doomed = ordered[: len(self._chunks) - max_chunks]
        for c in doomed:
            del self._chunks[c.id]
        self._save()
        return len(doomed)

    def __len__(self) -> int:
        return len(self._chunks)
