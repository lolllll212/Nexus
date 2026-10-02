"""Integration tests for Docker sandbox wiring across Dockerfile, Compose, and DI container.

Verifies:
1. Dockerfile runtime stage installs the docker CLI (docker.io).
2. All three compose files (docker-compose.yml, docker-compose.prod.yml, docker-compose.loop.yml)
   declare the /var/run/docker.sock mount for cortex and worker containers under an explicit opt-in profile.
3. The DI container provides a deliberate fallback to SubprocessSandbox with a loud warning
   when NEXUS_SANDBOX_BACKEND is unset and /var/run/docker.sock is not accessible.
4. Explicit configurations (NEXUS_SANDBOX_BACKEND=subprocess or docker) are honoured.
5. architecture-map.md documents the socket profile requirement and fallback behavior.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from nexus.infrastructure.adapters.sandbox.docker_sandbox import DockerSandbox
from nexus.infrastructure.adapters.sandbox.subprocess_sandbox import SubprocessSandbox
from nexus.infrastructure.di.container import Config, Container

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_runtime_installs_docker_cli() -> None:
    """The Dockerfile Stage 2 runtime must install the Docker CLI for container sandboxing."""
    dockerfile = REPO_ROOT / "Dockerfile"
    assert dockerfile.exists(), "Dockerfile must exist at repo root"
    content = dockerfile.read_text(encoding="utf-8")

    # Verify Stage 2 installs docker.io
    assert "FROM python:3.11-slim" in content, "Stage 2 python runtime must exist"
    stage2 = content.split("FROM python:3.11-slim")[1]
    assert "docker.io" in stage2, "Dockerfile runtime stage must install docker.io package"


@pytest.mark.parametrize(
    "compose_filename",
    [
        "docker-compose.yml",
        "docker-compose.prod.yml",
        "docker-compose.loop.yml",
    ],
)
def test_compose_files_declare_socket_mount_under_opt_in_profile(compose_filename: str) -> None:
    """Compose files must declare /var/run/docker.sock mount under an opt-in profile for cortex and worker."""
    compose_path = REPO_ROOT / compose_filename
    assert compose_path.exists(), f"{compose_filename} must exist at repo root"

    with open(compose_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    assert services, f"No services found in {compose_filename}"

    socket_services = {}
    for name, s in services.items():
        vols = s.get("volumes", [])
        has_socket = any("/var/run/docker.sock" in str(v) for v in vols)
        if has_socket:
            socket_services[name] = s

    assert socket_services, f"{compose_filename} must have services mounting /var/run/docker.sock"

    # Every service mounting the docker socket MUST declare an opt-in profile
    for name, s in socket_services.items():
        profiles = s.get("profiles", [])
        assert profiles, f"Service '{name}' in {compose_filename} mounts docker socket but lacks profiles"
        assert (
            "docker-sandbox" in profiles or "sandbox" in profiles
        ), f"Service '{name}' in {compose_filename} must include an opt-in profile (e.g. 'docker-sandbox')"

    # Must cover cortex and worker services
    cortex_matches = [name for name in socket_services if "cortex" in name]
    worker_matches = [name for name in socket_services if "worker" in name]
    assert (
        cortex_matches
    ), f"{compose_filename} must have a cortex service with socket mount under opt-in profile"
    assert (
        worker_matches
    ), f"{compose_filename} must have a worker service with socket mount under opt-in profile"


def test_container_sandbox_falls_back_when_socket_missing_and_backend_unset(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When NEXUS_SANDBOX_BACKEND is unset and docker.sock is missing, log loud warning and fall back."""
    monkeypatch.delenv("NEXUS_SANDBOX_BACKEND", raising=False)
    monkeypatch.setenv("NEXUS_INFRA_BACKEND", "memory")

    # Emulate socket missing on host
    with patch.object(Path, "exists", return_value=False), caplog.at_level(logging.WARNING):
        container = Container(Config())
        sandbox = container.sandbox

    assert isinstance(
        sandbox, SubprocessSandbox
    ), "Must deliberately fall back to SubprocessSandbox when socket is missing"
    assert any(
        "LOUD WARNING" in record.message or "docker-sandbox" in record.message for record in caplog.records
    ), "Loud warning explaining the socket profile requirement must be logged"


def test_container_sandbox_honours_explicit_subprocess_setting(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When NEXUS_SANDBOX_BACKEND=subprocess is explicit, use SubprocessSandbox without warning."""
    monkeypatch.setenv("NEXUS_SANDBOX_BACKEND", "subprocess")
    monkeypatch.setenv("NEXUS_INFRA_BACKEND", "memory")

    with caplog.at_level(logging.WARNING):
        container = Container(Config())
        sandbox = container.sandbox

    assert isinstance(sandbox, SubprocessSandbox)
    # No socket missing warning should be emitted when explicitly configured
    assert not any("LOUD WARNING" in record.message for record in caplog.records)


def test_container_sandbox_uses_docker_when_socket_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When docker.sock exists and backend is unset, use DockerSandbox."""
    monkeypatch.delenv("NEXUS_SANDBOX_BACKEND", raising=False)
    monkeypatch.setenv("NEXUS_INFRA_BACKEND", "memory")

    # Patch Path.exists specifically for docker.sock
    orig_exists = Path.exists

    def mock_exists(self: Path) -> bool:
        if str(self).replace("\\", "/") == "/var/run/docker.sock":
            return True
        return orig_exists(self)

    with patch.object(Path, "exists", mock_exists):
        container = Container(Config())
        sandbox = container.sandbox

    assert isinstance(sandbox, DockerSandbox), "Must build DockerSandbox when socket exists"


def test_container_sandbox_honours_explicit_docker_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When NEXUS_SANDBOX_BACKEND=docker is explicit, use DockerSandbox."""
    monkeypatch.setenv("NEXUS_SANDBOX_BACKEND", "docker")
    monkeypatch.setenv("NEXUS_INFRA_BACKEND", "memory")

    container = Container(Config())
    assert isinstance(container.sandbox, DockerSandbox)


def test_architecture_map_documents_sandbox_profile_and_fallback() -> None:
    """architecture-map.md must document the opt-in profile and fallback behavior."""
    arch_doc = REPO_ROOT / "docs" / "architecture-map.md"
    assert arch_doc.exists(), "docs/architecture-map.md must exist"
    text = arch_doc.read_text(encoding="utf-8")

    assert "/var/run/docker.sock" in text
    assert "docker-sandbox" in text
    assert "SubprocessSandbox" in text
    assert "NEXUS_SANDBOX_BACKEND" in text
