"""API-key Authenticator adapter - stateless bearer-token verification.

The key table is loaded once from configuration/secrets and never touches a
database. Swap for a JWT or OAuth adapter by implementing the same port.
"""

from __future__ import annotations

from typing import Dict

from nexus.domain.exceptions import UnauthorizedError
from nexus.domain.ports.auth import Authenticator
from nexus.domain.value_objects.identity import Identity, Role


class ApiKeyAuthenticator(Authenticator):
    """Validates bearer keys against a configured key table.

    Key table shape (from NEXUS_API_KEYS JSON / secret):
        {"sk-...": {"user_id": "u1", "tenant_id": "acme", "role": "admin"}}

    Fail-closed: refuses to authenticate when the key table is empty,
    preventing accidental anonymous access in production.
    """

    def __init__(self, keys: Dict[str, Dict]) -> None:
        self._keys = keys or {}
        self._empty = len(self._keys) == 0

    async def authenticate(self, credential: str) -> Identity:
        if not credential:
            raise UnauthorizedError("Missing credentials")
        if self._empty:
            raise UnauthorizedError(
                "No API keys configured. Set NEXUS_API_KEYS in .env to allow access."
            )
        record = self._keys.get(credential)
        if record is None:
            raise UnauthorizedError("Invalid credentials")
        role = Role(record.get("role", Role.USER.value))
        return Identity(
            user_id=record.get("user_id", credential),
            tenant_id=record.get("tenant_id", "default"),
            role=role,
            display_name=record.get("display_name", ""),
        )
