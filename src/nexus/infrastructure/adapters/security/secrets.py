"""SecretStore adapters - environment, JSON file, and chained composition.

Production hardening: the composition root resolves secrets through a store
instead of business code reading process env directly. Swap the backend by
changing NEXUS_SECRET_BACKEND (env | json:<path>).
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from nexus.domain.ports.secrets import SecretStore


class EnvSecretStore(SecretStore):
    """Reads secrets from the process environment."""

    def get(self, name: str) -> Optional[str]:
        return os.getenv(name)


class JsonFileSecretStore(SecretStore):
    """Reads secrets from a JSON file, falling back to env."""

    def __init__(self, path: str) -> None:
        self._data: Dict[str, str] = {}
        if path and os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                parsed = json.load(fh)
            if isinstance(parsed, dict):
                self._data = {str(k): str(v) for k, v in parsed.items()}

    def get(self, name: str) -> Optional[str]:
        value = self._data.get(name)
        if value is not None:
            return value
        return os.getenv(name)


class ChainedSecretStore(SecretStore):
    """Tries each store in order; returns the first configured value."""

    def __init__(self, stores: List[SecretStore]) -> None:
        self._stores = stores

    def get(self, name: str) -> Optional[str]:
        for store in self._stores:
            value = store.get(name)
            if value is not None:
                return value
        return None
