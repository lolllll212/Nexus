"""Authentication port - derives a verified Identity from a credential."""

from __future__ import annotations

from abc import ABC, abstractmethod

from nexus.domain.value_objects.identity import Identity


class Authenticator(ABC):
    """Turns a bearer credential into a verified Identity.

    Implementations are swappable: API keys, JWT, OAuth, mTLS - the
    application and API layers only ever see an Identity.
    """

    @abstractmethod
    async def authenticate(self, credential: str) -> Identity:
        """Verify the credential and return its Identity.

        Raises UnauthorizedError when the credential is missing/invalid.
        """
        ...
