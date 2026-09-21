"""
Production-grade coding training store.

Hybrid storage:
  - Qdrant for vector similarity search (semantic matching)
  - JSON file as durable backup (survives Qdrant restarts)
  - Quality scoring, versioning, auto-learning
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class CodingExample:
    """A single coding example with quality metadata."""
    id: str = field(default_factory=lambda: str(uuid4())[:12])
    task: str = ""
    solution: str = ""
    language: str = "python"
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    explanation: str = ""
    test_cases: str = ""
    difficulty: str = "medium"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: int = 1
    # Quality metrics
    use_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    avg_rating: float = 0.0
    source: str = "manual"  # manual | auto-learned | imported | git
    # Vector search support
    embedding: List[float] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 1.0

    def record_use(self, succeeded: bool, rating: float = 0.0) -> None:
        self.use_count += 1
        if succeeded:
            self.success_count += 1
        else:
            self.fail_count += 1
        if rating > 0:
            alpha = 0.2
            self.avg_rating = (1 - alpha) * self.avg_rating + alpha * rating
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("embedding", None)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> CodingExample:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_prompt(self) -> str:
        parts = [f"Task: {self.task}", f"Language: {self.language}"]
        if self.explanation:
            parts.append(f"Approach: {self.explanation}")
        parts.append(f"Solution:\n```{self.language}\n{self.solution}\n```")
        if self.test_cases:
            parts.append(f"Test:\n```{self.language}\n{self.test_cases}\n```")
        return "\n".join(parts)

    def search_text(self) -> str:
        """Text used for embedding generation."""
        return f"{self.task} {self.explanation} {' '.join(self.tags)} {self.category}"


class CodingStore:
    """Production-grade store with Qdrant + JSON backup."""

    def __init__(
        self,
        store_path: str | Path = "data/coding_examples.json",
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        embedding_dim: int = 384,
    ) -> None:
        self._path = Path(store_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._dim = embedding_dim
        self._examples: List[CodingExample] = []
        self._qdrant = None
        self._collection = "coding_examples"

        # Try to connect to Qdrant (optional — JSON-only mode if unavailable)
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import VectorParams, Distance
            self._qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)
            collections = [c.name for c in self._qdrant.get_collections().collections]
            if self._collection not in collections:
                self._qdrant.create_collection(
                    collection_name=self._collection,
                    vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
                )
        except Exception:
            self._qdrant = None

        self._load()

    def _load(self) -> None:
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._examples = [CodingExample.from_dict(e) for e in data]
        else:
            self._examples = []

    def _save(self) -> None:
        self._path.write_text(
            json.dumps([e.to_dict() for e in self._examples], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _upsert_vector(self, example: CodingExample) -> None:
        if not self._qdrant or not example.embedding:
            return
        try:
            from qdrant_client.models import PointStruct
            self._qdrant.upsert(
                collection_name=self._collection,
                points=[PointStruct(id=example.id, vector=example.embedding, payload=example.to_dict())],
            )
        except Exception:
            pass

    def _search_vectors(self, query_vector: List[float], limit: int = 5) -> List[str]:
        if not self._qdrant:
            return []
        try:
            results = self._qdrant.search(
                collection_name=self._collection,
                query_vector=query_vector,
                limit=limit,
            )
            return [r.id for r in results]
        except Exception:
            return []

    def add(self, example: CodingExample) -> CodingExample:
        example.updated_at = datetime.now(timezone.utc).isoformat()
        self._examples.append(example)
        self._save()
        self._upsert_vector(example)
        return example

    def add_batch(self, examples: List[CodingExample]) -> int:
        for e in examples:
            e.updated_at = datetime.now(timezone.utc).isoformat()
            self._examples.extend(examples)
            self._save()
            for ex in examples:
                self._upsert_vector(ex)
            return len(examples)
        return 0

    def update(self, example: CodingExample) -> bool:
        for i, e in enumerate(self._examples):
            if e.id == example.id:
                example.version += 1
                example.updated_at = datetime.now(timezone.utc).isoformat()
                self._examples[i] = example
                self._save()
                self._upsert_vector(example)
                return True
        return False

    def get(self, example_id: str) -> Optional[CodingExample]:
        for e in self._examples:
            if e.id == example_id:
                return e
        return None

    def list_all(self) -> List[CodingExample]:
        return list(self._examples)

    def search(self, query: str, category: Optional[str] = None, limit: int = 5) -> List[CodingExample]:
        q = query.lower()
        results = []
        for e in self._examples:
            if category and e.category != category:
                continue
            score = 0
            for word in q.split():
                if word in e.task.lower():
                    score += 3
                if word in e.tags:
                    score += 2
                if word in e.category.lower():
                    score += 1
                if word in e.explanation.lower():
                    score += 1
            # Quality boost: higher-rated examples rank higher
            score += e.avg_rating * 0.5
            score += min(e.use_count * 0.1, 2.0)
            if score > 0:
                results.append((score, e))
        results.sort(key=lambda x: (-x[0], -x[1].avg_rating))
        return [e for _, e in results[:limit]]

    def search_semantic(self, query_vector: List[float], limit: int = 5) -> List[CodingExample]:
        """Vector similarity search via Qdrant."""
        ids = self._search_vectors(query_vector, limit)
        return [self.get(id) for id in ids if self.get(id)]

    def record_outcome(self, example_id: str, succeeded: bool, rating: float = 0.0) -> bool:
        ex = self.get(example_id)
        if not ex:
            return False
        ex.record_use(succeeded, rating)
        self._save()
        return True

    def get_top_rated(self, limit: int = 10) -> List[CodingExample]:
        scored = [(e.avg_rating * 2 + e.success_rate + min(e.use_count * 0.1, 3), e) for e in self._examples]
        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:limit]]

    def get_underused(self, min_uses: int = 2) -> List[CodingExample]:
        return [e for e in self._examples if e.use_count < min_uses]

    def get_low_quality(self, min_success_rate: float = 0.5) -> List[CodingExample]:
        return [e for e in self._examples if (e.success_count + e.fail_count) > 3 and e.success_rate < min_success_rate]

    def deprecate(self, example_id: str) -> bool:
        ex = self.get(example_id)
        if not ex:
            return False
        ex.difficulty = "deprecated"
        self._save()
        return True

    def delete(self, example_id: str) -> bool:
        for i, e in enumerate(self._examples):
            if e.id == example_id:
                self._examples.pop(i)
                self._save()
                if self._qdrant:
                    try:
                        self._qdrant.delete(collection_name=self._collection, points=[example_id])
                    except Exception:
                        pass
                return True
        return False

    def export_version(self, version_tag: str) -> Path:
        """Export a versioned snapshot."""
        export_path = self._path.parent / f"coding_examples_{version_tag}.json"
        export_path.write_text(
            json.dumps([e.to_dict() for e in self._examples], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return export_path

    def import_from_git(self, repo_path: str, patterns: List[str] = None) -> int:
        """Auto-ingest coding examples from a git repository."""
        from nexus.application.training.git_ingester import GitIngester
        ingester = GitIngester(self)
        return ingester.ingest_repo(repo_path, patterns or ["*.py"])

    def stats(self) -> Dict[str, Any]:
        categories = {}
        langs = {}
        total_uses = 0
        total_success = 0
        for e in self._examples:
            categories[e.category] = categories.get(e.category, 0) + 1
            langs[e.language] = langs.get(e.language, 0) + 1
            total_uses += e.use_count
            total_success += e.success_count
        return {
            "total": len(self._examples),
            "categories": categories,
            "languages": langs,
            "total_uses": total_uses,
            "overall_success_rate": total_success / total_uses if total_uses > 0 else 0,
            "qdrant_connected": self._qdrant is not None,
        }
