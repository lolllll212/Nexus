"""Tenant-scoped persistence for closed-loop AI quality feedback.

Like the chat-history store, this is deliberately local-first: one atomic
JSON document in production/dev and a pure in-memory mode for tests.  The
store keeps feedback owner-scoped and updates an existing vote when the same
user rates the same response again, which makes UI retries idempotent.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from nexus.domain.value_objects.ai_feedback import AIFeedback, FeedbackCategory, summarize_feedback
from nexus.domain.value_objects.clock import utc_now

logger = logging.getLogger("nexus.ai_feedback")

MAX_FEEDBACK_RECORDS = 10_000


class AIFeedbackStore:
    """Thread-safe feedback store with optional JSON-file persistence."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else None
        self._lock = threading.Lock()
        self._records: dict[str, AIFeedback] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self._path is None or not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            rows = data.get("feedback") if isinstance(data, dict) else None
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    try:
                        record = AIFeedback.from_dict(row)
                    except Exception:
                        continue
                    self._records[record.id] = record
        except Exception as exc:
            logger.warning("AI feedback file unreadable (%s); starting empty", exc)
            self._records = {}

    def _flush_locked(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            rows = [
                record.to_dict()
                for record in sorted(self._records.values(), key=lambda item: item.created_at)
            ]
            tmp.write_text(
                json.dumps({"feedback": rows}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(tmp, self._path)
        except Exception as exc:
            logger.warning("failed to persist AI feedback: %s", exc)

    def _prune_locked(self) -> None:
        if len(self._records) <= MAX_FEEDBACK_RECORDS:
            return
        ordered = sorted(self._records.values(), key=lambda item: item.updated_at, reverse=True)
        self._records = {record.id: record for record in ordered[:MAX_FEEDBACK_RECORDS]}

    def record(
        self,
        *,
        tenant_id: str,
        user_id: str,
        session_id: str,
        response_id: str,
        rating: int,
        stars: int | None = None,
        categories: Iterable[FeedbackCategory | str] = (),
        comment: str = "",
        model: str | None = None,
    ) -> AIFeedback:
        normalized_categories = tuple(FeedbackCategory(str(category)) for category in categories)
        with self._lock:
            self._ensure_loaded()
            existing = next(
                (
                    record
                    for record in self._records.values()
                    if record.tenant_id == tenant_id
                    and record.user_id == user_id
                    and record.session_id == session_id
                    and record.response_id == response_id
                    and response_id
                ),
                None,
            )
            if existing is not None:
                record = replace(
                    existing,
                    rating=rating,
                    stars=stars,
                    categories=normalized_categories,
                    comment=comment[:2000],
                    model=model,
                    updated_at=utc_now(),
                )
            else:
                record = AIFeedback(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    session_id=session_id,
                    response_id=response_id,
                    rating=rating,
                    stars=stars,
                    categories=normalized_categories,
                    comment=comment[:2000],
                    model=model,
                )
            self._records[record.id] = record
            self._prune_locked()
            self._flush_locked()
            return record

    def list_feedback(
        self,
        *,
        tenant_id: str,
        user_id: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[AIFeedback]:
        with self._lock:
            self._ensure_loaded()
            records = [
                record
                for record in self._records.values()
                if record.tenant_id == tenant_id
                and (user_id is None or record.user_id == user_id)
                and (session_id is None or record.session_id == session_id)
            ]
            records.sort(key=lambda item: item.updated_at, reverse=True)
            return records[: max(1, min(limit, 200))]

    def summary(self, *, tenant_id: str, user_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            records = [
                record
                for record in self._records.values()
                if record.tenant_id == tenant_id and (user_id is None or record.user_id == user_id)
            ]
        return summarize_feedback(records)

    def clear(self, *, tenant_id: str, user_id: str | None = None) -> int:
        with self._lock:
            self._ensure_loaded()
            before = len(self._records)
            self._records = {
                record_id: record
                for record_id, record in self._records.items()
                if not (
                    record.tenant_id == tenant_id and (user_id is None or record.user_id == user_id)
                )
            }
            deleted = before - len(self._records)
            self._flush_locked()
            return deleted
