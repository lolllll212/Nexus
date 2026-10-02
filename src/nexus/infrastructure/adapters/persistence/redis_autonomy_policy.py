"""Redis-backed autonomy approvals and append-only audit log."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from urllib.parse import quote

from redis.exceptions import RedisError

from nexus.domain.entities.goal import Goal, GoalEvent
from nexus.domain.ports.autonomy import AutonomyDecision, AutonomyPolicy

logger = logging.getLogger(__name__)


class RedisAutonomyPolicy(AutonomyPolicy):
    """Persist approvals and audit events across API and worker processes."""

    def __init__(
        self,
        delegate: AutonomyPolicy,
        redis_url: str = "redis://localhost:6379",
        client: Any | None = None,
    ) -> None:
        self._delegate = delegate
        self._redis_url = redis_url
        self._client = client

    async def _redis(self):
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    @staticmethod
    def _tenant_key(prefix: str, tenant_id: str) -> str:
        return f"nexus:autonomy:{prefix}:{quote(tenant_id, safe='')}"

    async def authorize_action(self, tenant_id: str = "default", units: int = 1) -> AutonomyDecision:
        return await self._delegate.authorize_action(tenant_id=tenant_id, units=units)

    async def authorize_step(self, goal: Goal, tenant_id: str = "default") -> AutonomyDecision:
        return await self._delegate.authorize_step(goal, tenant_id=tenant_id)

    async def spend(self, goal: Goal, tenant_id: str = "default", units: int = 1) -> AutonomyDecision:
        return await self._delegate.spend(goal, tenant_id=tenant_id, units=units)

    async def require_approval(self, action: str, actor: str, tenant_id: str = "default") -> bool:
        if await self._delegate.require_approval(action, actor, tenant_id=tenant_id):
            return True
        try:
            redis = await self._redis()
            approval = await redis.hget(self._tenant_key("approvals", tenant_id), action)
        except RedisError:
            logger.warning(
                "Redis unavailable for autonomy approval lookup; using in-memory policy", exc_info=True
            )
            return False
        return bool(approval and json.loads(approval).get("granted") is True)

    async def grant_approval(self, action: str, approver: str, tenant_id: str = "default") -> None:
        approval = {"granted": True, "approver": approver}
        try:
            redis = await self._redis()
            await redis.hset(self._tenant_key("approvals", tenant_id), action, json.dumps(approval))
        except RedisError:
            logger.warning(
                "Redis unavailable for autonomy approval write; using in-memory policy", exc_info=True
            )
            await self._delegate.grant_approval(action, approver, tenant_id=tenant_id)
            return
        await self.audit(
            GoalEvent(kind="approved", detail=f"action={action}", actor=approver),
            tenant_id=tenant_id,
        )

    async def audit(self, event: GoalEvent, tenant_id: str = "default") -> None:
        payload = {
            "kind": event.kind,
            "detail": event.detail,
            "actor": event.actor,
            "ts": event.ts.isoformat(),
        }
        try:
            redis = await self._redis()
            await redis.rpush(self._tenant_key("audit", tenant_id), json.dumps(payload))
        except RedisError:
            logger.warning(
                "Redis unavailable for autonomy audit write; retaining it in memory", exc_info=True
            )
            await self._delegate.audit(event, tenant_id=tenant_id)

    async def pending_approvals(self, tenant_id: str = "default", limit: int = 50) -> list[dict[str, Any]]:
        try:
            redis = await self._redis()
            approvals = await redis.hgetall(self._tenant_key("approvals", tenant_id))
        except RedisError:
            logger.warning(
                "Redis unavailable for autonomy approval listing; using in-memory policy", exc_info=True
            )
            return await self._delegate.pending_approvals(tenant_id=tenant_id, limit=limit)
        items = [{"action": action, **json.loads(payload)} for action, payload in approvals.items()]
        return items[:limit]

    async def audit_log(self, tenant_id: str = "default", limit: int = 200) -> list[GoalEvent]:
        if limit <= 0:
            return []
        try:
            redis = await self._redis()
            payloads = await redis.lrange(self._tenant_key("audit", tenant_id), -limit, -1)
        except RedisError:
            logger.warning(
                "Redis unavailable for autonomy audit listing; using in-memory policy", exc_info=True
            )
            return await self._delegate.audit_log(tenant_id=tenant_id, limit=limit)
        return [
            GoalEvent(
                kind=data["kind"],
                detail=data["detail"],
                actor=data["actor"],
                ts=datetime.fromisoformat(data["ts"]),
            )
            for data in map(json.loads, payloads)
        ]

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
