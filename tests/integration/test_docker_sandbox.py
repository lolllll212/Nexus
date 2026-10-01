"""Integration tests for DockerSandbox isolation and execution.

Tests ephemeral container execution, resource capping, network isolation,
and sandbox execution of untrusted scripts.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from nexus.infrastructure.adapters.sandbox.docker_sandbox import DockerSandbox


@pytest.fixture
def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


@pytest.mark.asyncio
async def test_docker_sandbox_run_code(docker_available):
    if not docker_available:
        pytest.skip("Docker daemon/CLI not available in this test runner")

    sandbox = DockerSandbox(image="python:3.13-slim")
    code = "import sys\nprint('sandbox-ok')\n"
    res = await sandbox.run_code(code, timeout=30)

    assert "sandbox-ok" in res.get("output", "")
    assert not res.get("error")


@pytest.mark.asyncio
async def test_docker_sandbox_network_isolated(docker_available):
    if not docker_available:
        pytest.skip("Docker daemon/CLI not available in this test runner")

    sandbox = DockerSandbox(image="python:3.13-slim")
    # Attempt outbound network call inside --network none container
    code = (
        "import urllib.request, sys\n"
        "try:\n"
        "    urllib.request.urlopen('http://1.1.1.1', timeout=2)\n"
        "    print('network-leak')\n"
        "except Exception as e:\n"
        "    print('blocked-safely')\n"
    )
    res = await sandbox.run_code(code, timeout=30)
    assert "blocked-safely" in res.get("output", "")
    assert "network-leak" not in res.get("output", "")


@pytest.mark.asyncio
async def test_docker_sandbox_solve_function(docker_available):
    if not docker_available:
        pytest.skip("Docker daemon/CLI not available in this test runner")

    sandbox = DockerSandbox(image="python:3.13-slim")
    code = "return {'doubled': input_data.get('val', 0) * 2}"
    res = await sandbox.run(code, inputs={"val": 21}, timeout=30)

    assert res.get("ok") is True
    assert res.get("result", {}).get("doubled") == 42
