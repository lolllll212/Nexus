"""Secrets port - abstract access to sensitive configuration.

Production hardening requirement: secrets (API keys, deploy tokens, DB
passwords) must be resolvable through a swappable SecretStore instead of
being read directly from environment in business code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class SecretStore(ABC):
    """Resolves a secret by name, or None when it is not configured."""

    @abstractmethod
    def get(self, name: str) -> Optional[str]: ...
