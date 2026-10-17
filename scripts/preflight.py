#!/usr/bin/env python
"""NEXUS preflight - verify this machine is ready to run NEXUS, in one command.

Runs a short checklist (Python version, package import, env file, API keys,
LLM reachability, sandbox backend, infrastructure mode) and prints a
human-readable report. Exits non-zero when a required check fails, so it can
gate a launch from CI, a container entrypoint, or a shell script.

Usage:
    python scripts/preflight.py                # human-readable report
    python scripts/preflight.py --json         # machine-readable report
    python scripts/preflight.py --strict       # warnings also fail (exit 1)
    python scripts/preflight.py --skip-network # skip the live LLM probe
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OK, WARN, FAIL = "ok", "warn", "fail"
_ICON = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}


@dataclass
class Check:
    name: str
    status: str
    detail: str


def _load_env() -> dict[str, str]:
    """Read .env (KEY=VALUE) merged under the real environment (env wins)."""
    merged: dict[str, str] = {}
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            merged[key.strip()] = value.strip().strip('"').strip("'")
    merged.update(os.environ)
    return merged


def check_python() -> Check:
    v = sys.version_info
    detail = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 11):
        return Check("python", OK, detail)
    return Check("python", FAIL, f"{detail} (need >= 3.11)")


def check_package() -> Check:
    src = REPO_ROOT / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        import nexus  # noqa: F401
    except Exception as exc:  # pragma: no cover - depends on environment
        return Check("package", FAIL, f"cannot import nexus: {exc}")
    version = getattr(nexus, "__version__", "unknown")
    return Check("package", OK, f"nexus importable (version {version})")


def check_env_file() -> Check:
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        return Check("env-file", OK, ".env present")
    example = REPO_ROOT / ".env.example"
    hint = "copy .env.example -> .env" if example.exists() else "create .env"
    return Check("env-file", WARN, f"no .env found ({hint})")


def check_api_keys(env: dict[str, str]) -> Check:
    raw = (env.get("NEXUS_API_KEYS") or "").strip()
    if not raw or raw in ("{}", "null"):
        return Check(
            "api-keys",
            FAIL,
            "NEXUS_API_KEYS is empty - auth fails closed (every request returns 401)",
        )
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and parsed:
            return Check("api-keys", OK, f"{len(parsed)} key(s) configured")
    except json.JSONDecodeError:
        pass
    return Check("api-keys", WARN, "NEXUS_API_KEYS set but not a valid JSON object")


def _probe(url: str, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - operator-provided URL
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return True, f"HTTP {exc.code} (reachable)"
    except Exception as exc:
        return False, str(exc)


def check_llm(env: dict[str, str], skip_network: bool) -> Check:
    base = (env.get("NEXUS_LLM_BASE_URL") or "http://127.0.0.1:1234/v1").rstrip("/")
    if skip_network:
        return Check("llm", WARN, f"probe skipped (base {base})")
    reachable, detail = _probe(f"{base}/models")
    if reachable:
        return Check("llm", OK, f"{base} ({detail})")
    return Check("llm", WARN, f"{base} unreachable ({detail}) - start your LLM server")


def check_sandbox(env: dict[str, str]) -> Check:
    backend = (env.get("NEXUS_SANDBOX_BACKEND") or "docker").lower()
    if backend != "docker":
        return Check("sandbox", OK, f"backend={backend} (no Docker required)")
    docker = shutil.which("docker")
    if not docker:
        return Check("sandbox", WARN, "docker backend selected but 'docker' not on PATH")
    try:
        proc = subprocess.run([docker, "info"], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            return Check("sandbox", OK, "docker daemon reachable")
        return Check("sandbox", WARN, "docker installed but daemon not reachable")
    except Exception as exc:
        return Check("sandbox", WARN, f"docker check failed: {exc}")


def check_infra(env: dict[str, str]) -> Check:
    mode = (env.get("NEXUS_INFRA_BACKEND") or "external").lower()
    if mode == "memory":
        return Check("infra", OK, "memory backend (fully in-process, no external services)")
    return Check(
        "infra",
        WARN,
        "external backend - ensure Redis/Qdrant/Neo4j are running (set NEXUS_INFRA_BACKEND=memory to skip)",
    )


def check_workspace() -> Check:
    if os.access(REPO_ROOT, os.W_OK):
        return Check("workspace", OK, f"{REPO_ROOT} is writable")
    return Check("workspace", WARN, f"{REPO_ROOT} is not writable (state files may fail)")


def run_checks(skip_network: bool) -> list[Check]:
    env = _load_env()
    return [
        check_python(),
        check_package(),
        check_env_file(),
        check_api_keys(env),
        check_llm(env, skip_network),
        check_sandbox(env),
        check_infra(env),
        check_workspace(),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS preflight readiness check")
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--skip-network", action="store_true", help="skip the live LLM probe")
    args = parser.parse_args()

    checks = run_checks(args.skip_network)
    failures = [c for c in checks if c.status == FAIL]
    warnings = [c for c in checks if c.status == WARN]

    if args.json:
        print(json.dumps({"checks": [asdict(c) for c in checks]}, indent=2))
    else:
        print("NEXUS preflight")
        print("=" * 60)
        for c in checks:
            print(f"{_ICON[c.status]} {c.name:<10} {c.detail}")
        print("=" * 60)
        print(f"{len(checks)} checks: {len(failures)} failed, {len(warnings)} warnings")

    failed = bool(failures) or (args.strict and bool(warnings))
    if failed:
        if not args.json:
            print("Not ready. Fix the [FAIL] items above (and warnings under --strict).")
        return 1
    if not args.json:
        print("Ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
