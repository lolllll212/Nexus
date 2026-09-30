"""Pytest configuration and root path resolution."""

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
os.environ.setdefault(
    "NEXUS_API_KEYS",
    '{"sk-test-1": {"user_id": "u1", "tenant_id": "t1", "role": "admin"}, "sk-test-2": {"user_id": "u2", "tenant_id": "t2", "role": "user"}}',
)
# In test environments without Docker daemon running, use subprocess sandbox
os.environ.setdefault("NEXUS_SANDBOX_BACKEND", "subprocess")
