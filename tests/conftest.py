"""Pytest configuration and root path resolution."""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Default test keys for authenticating routes during tests
_test_keys = {
    "sk-test-1": {"user_id": "u1", "tenant_id": "t1", "role": "admin"},
    "sk-test-2": {"user_id": "u2", "tenant_id": "t2", "role": "user"},
}
try:
    _raw = os.environ.get("NEXUS_API_KEYS", "{}").strip("'\"")
    _existing = json.loads(_raw) if _raw else {}
except Exception:
    _existing = {}
_existing.update(_test_keys)
os.environ["NEXUS_API_KEYS"] = json.dumps(_existing)

# In test environments without Docker daemon running, use subprocess sandbox
os.environ.setdefault("NEXUS_SANDBOX_BACKEND", "subprocess")
