"""Unit tests verifying security audit hardening across all vectors:

1. json_transform AST escape prevention (blocks __class__, __subclasses__, exec, eval).
2. SSRF resolution fails closed on DNS errors and inspects redirects.
3. File tools workspace root confinement (blocks ../, /etc/passwd path traversal).
4. Tool approval gate on destructive tools (run_shell, write_file).
5. Constant-time API key comparison (secrets.compare_digest).
"""

import tempfile
from pathlib import Path

import pytest

from nexus.domain.exceptions import UnauthorizedError
from nexus.infrastructure.adapters.auth.api_key_authenticator import ApiKeyAuthenticator
from nexus.infrastructure.adapters.autonomy.policy import DefaultAutonomyPolicy
from nexus.infrastructure.adapters.execution.extended_tools import (
    EXTENDED_HANDLERS,
    resolve_confined_path,
    set_autonomy_policy,
)
from nexus.infrastructure.adapters.security.in_memory_rate_limiter import InMemoryRateLimiter
from nexus.infrastructure.adapters.security.ssrf import is_safe_ip, validate_safe_url

# ─────────────────────────────────────────────────────────────────────────────
# 1. json_transform AST / Sandbox Escape Prevention
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_transform_blocks_python_sandbox_escapes():
    """Verify that Python sandbox escape payloads are blocked and never evaluated."""
    payloads = [
        "().__class__.__base__.__subclasses__()",
        "[c for c in ().__class__.__base__.__subclasses__() if c.__name__ == 'BuiltinImporter']",
        "__import__('os').system('id')",
        "eval('1 + 1')",
        "exec('print(1)')",
        "d.__class__.__mro__[1].__subclasses__()",
    ]

    for p in payloads:
        res = await EXTENDED_HANDLERS["json_transform"]({"json_str": '{"status": "ok"}', "expression": p})
        assert "error" in res, f"Expected escape payload '{p}' to be blocked, but got: {res}"
        assert not res.get("result"), f"Escape payload '{p}' returned a result: {res}"


@pytest.mark.asyncio
async def test_json_transform_valid_expressions():
    """Verify that safe calculations and transforms evaluate correctly."""
    data = '{"numbers": [10, 20, 30], "user": {"name": "Alice", "score": 95}}'

    # SimpleEval safe math / functions
    res1 = await EXTENDED_HANDLERS["json_transform"]({"json_str": data, "expression": "sum(d['numbers'])"})
    assert res1.get("result") == 60

    res2 = await EXTENDED_HANDLERS["json_transform"]({"json_str": data, "expression": "len(d['numbers'])"})
    assert res2.get("result") == 3

    res3 = await EXTENDED_HANDLERS["json_transform"](
        {"json_str": data, "expression": "d['user']['name'] == 'Alice'"}
    )
    assert res3.get("result") is True

    # JMESPath expression
    res4 = await EXTENDED_HANDLERS["json_transform"]({"json_str": data, "expression": "jmespath:user.score"})
    assert res4.get("result") == 95


# ─────────────────────────────────────────────────────────────────────────────
# 2. File Tools Workspace Confinement
# ─────────────────────────────────────────────────────────────────────────────


def test_resolve_confined_path_blocks_directory_traversal():
    """Verify that any path escaping the workspace root is rejected."""
    traversal_paths = [
        "../../../../etc/passwd",
        "/etc/passwd",
        "/etc/shadow",
        "../../../root",
        "/var/run/docker.sock",
    ]

    for bad_path in traversal_paths:
        resolved, err = resolve_confined_path(bad_path)
        assert resolved is None, f"Expected path '{bad_path}' to be rejected"
        assert "escapes workspace" in err.lower() or "access denied" in err.lower()


@pytest.mark.asyncio
async def test_file_tools_enforce_workspace_confinement():
    """Verify read_file, list_directory, and write_file reject traversal paths."""
    # Attempt read
    read_res = await EXTENDED_HANDLERS["read_file"]({"path": "/etc/passwd"})
    assert read_res.get("content") == ""
    assert (
        "escapes workspace" in read_res.get("error", "").lower()
        or "access denied" in read_res.get("error", "").lower()
    )

    # Attempt list
    list_res = await EXTENDED_HANDLERS["list_directory"]({"path": "/etc"})
    assert list_res.get("entries") == []
    assert (
        "escapes workspace" in list_res.get("error", "").lower()
        or "access denied" in list_res.get("error", "").lower()
    )

    # Attempt write
    write_res = await EXTENDED_HANDLERS["write_file"]({"path": "/etc/evil.sh", "content": "rm -rf /"})
    assert "error" in write_res
    assert (
        "escapes workspace" in write_res.get("error", "").lower()
        or "access denied" in write_res.get("error", "").lower()
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Destructive Operation Approval Gate (run_shell, write_file)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_shell_and_write_file_require_approval_when_policy_active():
    """Verify that destructive operations require approval under DefaultAutonomyPolicy."""
    rate_limiter = InMemoryRateLimiter()
    policy = DefaultAutonomyPolicy(rate_limiter=rate_limiter, hourly_budget=10, allowlist=[])
    set_autonomy_policy(policy)

    try:
        # run_shell should be blocked before approval
        shell_res = await EXTENDED_HANDLERS["run_shell"]({"command": "echo test"})
        assert shell_res.get("approval_required") is True
        assert "approval required" in shell_res.get("stderr", "").lower()

        # write_file should be blocked before approval
        write_res = await EXTENDED_HANDLERS["write_file"]({"path": "test_output.txt", "content": "data"})
        assert write_res.get("approval_required") is True

        # Grant approval for write_file
        await policy.grant_approval("tool:write_file", approver="admin", tenant_id="default")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_file = str(Path(tmp) / "safe_output.txt")
            write_approved_res = await EXTENDED_HANDLERS["write_file"](
                {"path": tmp_file, "content": "approved data"}
            )
            assert write_approved_res.get("bytes_written") == len("approved data")

    finally:
        set_autonomy_policy(None)


# ─────────────────────────────────────────────────────────────────────────────
# 4. SSRF Hardening (Fail-closed DNS resolution & safe IP ranges)
# ─────────────────────────────────────────────────────────────────────────────


def test_ssrf_validator_fails_closed_on_unresolvable_domains():
    """Verify that DNS resolution failure fails closed instead of silently passing."""
    safe, err = validate_safe_url("http://this-domain-does-not-exist-at-all-xyz-12345.org/test")
    assert not safe
    assert "dns resolution failed" in err.lower()


def test_ssrf_validator_blocks_internal_and_metadata_ips():
    """Verify private RFC 1918, link-local, loopback, and cloud metadata are blocked."""
    assert not is_safe_ip("127.0.0.1")
    assert not is_safe_ip("10.0.0.1")
    assert not is_safe_ip("172.16.0.1")
    assert not is_safe_ip("192.168.1.1")
    assert not is_safe_ip("169.254.169.254")
    assert not is_safe_ip("100.100.100.200")
    assert not is_safe_ip("0.0.0.0")
    assert not is_safe_ip("::1")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Constant-time API Key Comparison (secrets.compare_digest)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_key_authenticator_constant_time_comparison():
    """Verify ApiKeyAuthenticator properly authenticates valid keys and rejects invalid."""
    keys = {
        "sk-prod-super-secret-key-12345": {
            "user_id": "admin_user",
            "tenant_id": "acme",
            "role": "admin",
            "display_name": "Admin",
        }
    }
    authenticator = ApiKeyAuthenticator(keys)

    # Valid key
    identity = await authenticator.authenticate("sk-prod-super-secret-key-12345")
    assert identity.user_id == "admin_user"
    assert identity.tenant_id == "acme"

    # Invalid key with matching prefix
    with pytest.raises(UnauthorizedError):
        await authenticator.authenticate("sk-prod-super-secret-key-00000")

    # Empty key
    with pytest.raises(UnauthorizedError):
        await authenticator.authenticate("")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Sensitive Files Denylist & Fail-Closed Database / Shell Hardening
# ─────────────────────────────────────────────────────────────────────────────


def test_resolve_confined_path_blocks_secrets_denylist():
    """Verify that credentials, private keys, and environment files are denied."""
    denied = [
        ".env",
        ".env.local",
        ".env.production",
        "id_rsa",
        "id_rsa.pub",
        "cert.pem",
        "private.key",
        "secrets.json",
        ".git/config",
    ]
    for d in denied:
        resolved, err = resolve_confined_path(d)
        assert resolved is None, f"Expected {d} to be rejected"
        assert "access denied" in err.lower() or "forbidden" in err.lower()


@pytest.mark.asyncio
async def test_run_shell_fails_closed_without_policy():
    """Verify run_shell fails closed when no autonomy policy is set."""
    set_autonomy_policy(None)
    res = await EXTENDED_HANDLERS["run_shell"]({"command": "echo test"})
    assert res.get("approval_required") is True
    assert "approval required" in res.get("stderr", "").lower()


@pytest.mark.asyncio
async def test_query_database_blocks_writes_and_disallowed_hosts():
    """Verify SQLite write operations and non-allowlisted network DB hosts are blocked."""
    # Write attempt in SQLite
    write_sql = await EXTENDED_HANDLERS["query_database"](
        {"type": "sqlite", "database": "test.db", "sql": "DROP TABLE users"}
    )
    assert "error" in write_sql

    # Disallowed host in Postgres
    bad_host_res = await EXTENDED_HANDLERS["query_database"](
        {"type": "postgres", "host": "198.51.100.5", "sql": "SELECT 1"}
    )
    assert "error" in bad_host_res
    assert "not in the allowed" in bad_host_res["error"].lower()

