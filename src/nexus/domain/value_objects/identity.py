"""Identity value object - who is calling, and on whose behalf.

The conscious loop no longer trusts a client-supplied user_id string.
Every protected route derives an Identity from a verified credential,
carrying the tenant for data isolation and the role for authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Role(Enum):
    ADMIN = "admin"
    USER = "user"
    SERVICE = "service"
    PEER = "peer"


@dataclass(frozen=True)
class Identity:
    user_id: str
    tenant_id: str = "default"
    role: Role = Role.USER
    display_name: str = ""

    def scope_key(self) -> str:
        """Stable key used for per-identity rate limiting."""
        return f"{self.tenant_id}:{self.user_id}"
