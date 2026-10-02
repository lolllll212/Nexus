"""Integration tests for DockerSandbox isolation and execution.

Tests ephemeral container execution, resource capping, network isolation,
and sandbox execution of untrusted scripts.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from nexus.infrastructure.adapters.sandbox.docker_sandbox import DockerSandbox

DOCKER_IMAGE = "python:3.13-slim"


@pytest.fixture
def docker_available() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is not available in this test runner")
    try:
        daemon = subprocess.run(
            ["docker", "info"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Docker daemon is not available in this test runner")
    if daemon.returncode != 0:
        pytest.skip("Docker daemon is not available in this test runner")

    try:
        image = subprocess.run(
            ["docker", "image", "inspect", DOCKER_IMAGE],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip(f"Docker image {DOCKER_IMAGE} is not available locally")
    if image.returncode != 0:
        pytest.skip(f"Docker image {DOCKER_IMAGE} is not available locally")


@pytest.mark.asyncio
async def test_docker_sandbox_run_code(docker_available):
    sandbox = DockerSandbox(image=DOCKER_IMAGE)
    code = "import sys\nprint('sandbox-ok')\n"
    res = await sandbox.run_code(code, timeout=120)

    assert "sandbox-ok" in res.get("output", "")
    assert not res.get("error")


@pytest.mark.asyncio
async def test_docker_sandbox_network_isolated(docker_available):
    sandbox = DockerSandbox(image=DOCKER_IMAGE)
    # Attempt outbound network call inside --network none container
    code = (
        "import urllib.request, sys\n"
        "try:\n"
        "    urllib.request.urlopen('http://1.1.1.1', timeout=2)\n"
        "    print('network-leak')\n"
        "except Exception as e:\n"
        "    print('blocked-safely')\n"
    )
    res = await sandbox.run_code(code, timeout=120)
    assert "blocked-safely" in res.get("output", "")
    assert "network-leak" not in res.get("output", "")


@pytest.mark.asyncio
async def test_docker_sandbox_solve_function(docker_available):
    sandbox = DockerSandbox(image=DOCKER_IMAGE)
    code = "return {'doubled': input_data.get('val', 0) * 2}"
    res = await sandbox.run(code, inputs={"val": 21}, timeout=120)

    assert res.get("ok") is True
    assert res.get("result", {}).get("doubled") == 42
