"""API-key Authenticator adapter - stateless bearer-token verification.

The key table is loaded once from configuration/secrets and never touches a
database. Swap for a JWT or OAuth adapter by implementing the same port.
"""

from __future__ import annotations

import secrets

from nexus.domain.exceptions import UnauthorizedError
from nexus.domain.ports.auth import Authenticator
from nexus.domain.value_objects.identity import Identity, Role


class ApiKeyAuthenticator(Authenticator):
    """Validates bearer keys against a configured key table.

    Key table shape (from NEXUS_API_KEYS JSON / secret):
        {"sk-...": {"user_id": "u1", "tenant_id": "acme", "role": "admin"}}

    Fail-closed: refuses to authenticate when the key table is empty,
    preventing accidental anonymous access in production.
    Uses secrets.compare_digest to prevent timing side-channel attacks.
    """

    def __init__(self, keys: dict[str, dict]) -> None:
        self._keys = keys or {}
        self._empty = len(self._keys) == 0

    async def authenticate(self, credential: str) -> Identity:
        if not credential:
            raise UnauthorizedError("Missing credentials")
        if self._empty:
            raise UnauthorizedError("No API keys configured. Set NEXUS_API_KEYS in .env to allow access.")
        matched_record = None
        for key, record in self._keys.items():
            if secrets.compare_digest(key, credential):
                matched_record = record

        if matched_record is None:
            raise UnauthorizedError("Invalid credentials")

        role = Role(matched_record.get("role", Role.USER.value))
        return Identity(
            user_id=matched_record.get("user_id", credential),
            tenant_id=matched_record.get("tenant_id", "default"),
            role=role,
            display_name=matched_record.get("display_name", ""),
        )
