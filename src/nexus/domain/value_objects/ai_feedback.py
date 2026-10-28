"""Closed-loop AI quality feedback value objects and aggregation.

Modern AI systems need an explicit signal from users about whether a response
was useful.  These pure domain types make that signal portable across the
API, eval harness, model router, and future training pipelines without tying
it to a database or web framework.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Iterable
from uuid import uuid4

from nexus.domain.value_objects.clock import utc_now


class FeedbackCategory(StrEnum):
    HELPFUL = "helpful"
    INACCURATE = "inaccurate"
    INCOMPLETE = "incomplete"
    UNSAFE = "unsafe"
    SLOW = "slow"
    TOOL_ERROR = "tool_error"
    OTHER = "other"


@dataclass(frozen=True)
class AIFeedback:
    """One user's assessment of one AI response."""

    tenant_id: str
    user_id: str
    session_id: str
    response_id: str
    rating: int  # -1 (negative) or +1 (positive)
    id: str = field(default_factory=lambda: str(uuid4()))
    stars: int | None = None  # optional 1..5 quality score
    categories: tuple[FeedbackCategory, ...] = ()
    comment: str = ""
    model: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.rating not in (-1, 1):
            raise ValueError("rating must be -1 or +1")
        if self.stars is not None and not 1 <= self.stars <= 5:
            raise ValueError("stars must be between 1 and 5")
        normalized: list[FeedbackCategory] = []
        for category in self.categories:
            value = FeedbackCategory(category)
            if value not in normalized:
                normalized.append(value)
        object.__setattr__(self, "categories", tuple(normalized))
        object.__setattr__(self, "comment", self.comment[:2000])

    @property
    def quality_score(self) -> float:
        """Normalize thumbs/stars onto a 0..1 quality scale."""
        if self.stars is not None:
            return self.stars / 5.0
        return 1.0 if self.rating > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "response_id": self.response_id,
            "rating": self.rating,
            "stars": self.stars,
            "quality_score": round(self.quality_score, 4),
            "categories": [category.value for category in self.categories],
            "comment": self.comment,
            "model": self.model,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AIFeedback:
        def parse_dt(value: Any) -> datetime:
            if isinstance(value, datetime):
                return value
            if isinstance(value, str) and value:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return utc_now()

        return cls(
            id=str(raw.get("id") or uuid4()),
            tenant_id=str(raw.get("tenant_id") or "default"),
            user_id=str(raw.get("user_id") or "unknown"),
            session_id=str(raw.get("session_id") or ""),
            response_id=str(raw.get("response_id") or ""),
            rating=1 if int(raw.get("rating") or 0) > 0 else -1,
            stars=int(raw["stars"]) if raw.get("stars") is not None else None,
            categories=tuple(FeedbackCategory(str(c)) for c in raw.get("categories") or ()),
            comment=str(raw.get("comment") or ""),
            model=str(raw["model"]) if raw.get("model") else None,
            created_at=parse_dt(raw.get("created_at")),
            updated_at=parse_dt(raw.get("updated_at")),
        )


def summarize_feedback(records: Iterable[AIFeedback]) -> dict[str, Any]:
    """Aggregate feedback into dashboard/eval-friendly quality metrics."""
    items = list(records)
    total = len(items)
    positive = sum(1 for item in items if item.rating > 0)
    negative = total - positive
    starred = [item.stars for item in items if item.stars is not None]

    category_counts = Counter(category.value for item in items for category in item.categories)
    model_counts: dict[str, Counter[str]] = {}
    for item in items:
        model = item.model or "unknown"
        bucket = model_counts.setdefault(model, Counter())
        bucket["total"] += 1
        bucket["positive" if item.rating > 0 else "negative"] += 1

    by_model = {
        model: {
            "total": counts["total"],
            "positive": counts["positive"],
            "negative": counts["negative"],
            "positive_rate": round(counts["positive"] / counts["total"], 4) if counts["total"] else 0.0,
        }
        for model, counts in sorted(model_counts.items())
    }
    last_feedback_at = max((item.updated_at for item in items), default=None)

    return {
        "total": total,
        "positive": positive,
        "negative": negative,
        "positive_rate": round(positive / total, 4) if total else 0.0,
        "average_quality_score": round(sum(item.quality_score for item in items) / total, 4) if total else 0.0,
        "average_stars": round(sum(starred) / len(starred), 4) if starred else None,
        "categories": dict(sorted(category_counts.items())),
        "by_model": by_model,
        "last_feedback_at": last_feedback_at.isoformat() if last_feedback_at is not None else None,
    }
