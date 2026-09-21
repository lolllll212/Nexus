"""Docker sandbox adapter — runs untrusted code in isolated containers.

Security guarantees:
  - tmpfs mount (no persistent state leakage)
  - --network none (no outbound access)
  - --read-only root filesystem
  - Non-root user (nobody)
  - CPU and memory caps
  - Automatic container cleanup
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

from nexus.domain.ports.sandbox import Sandbox


class DockerSandbox(Sandbox):
    """Runs code in ephemeral Docker containers with strict resource limits."""

    def __init__(
        self,
        image: str = "python:3.13-slim",
        cpu_period: int = 100_000,
        cpu_quota: int = 50_000,
        memory_limit: str = "256m",
        pids_limit: int = 64,
        timeout: int = 30,
    ) -> None:
        self._image = image
        self._cpu_period = cpu_period
        self._cpu_quota = cpu_quota
        self._memory_limit = memory_limit
        self._pids_limit = pids_limit
        self._default_timeout = timeout

    async def run(
        self, code: str, inputs: Dict[str, Any] = None, timeout: int | None = None
    ) -> Dict[str, Any]:
        started = time.monotonic()
        timeout = timeout or self._default_timeout
        inputs = inputs or {}

        script = (
            "import json, sys, traceback\n"
            "def solve(input_data):\n" + _indent(code, 4) + "\n"
            "try:\n"
            "    result = solve(json.loads(sys.argv[1]))\n"
            "    print(json.dumps({'ok': True, 'result': result}))\n"
            "except Exception:\n"
            "    print(json.dumps({'ok': False, 'error': traceback.format_exc()}))\n"
        )

        with tempfile.TemporaryDirectory(prefix="nexus-docker-") as tmp:
            script_path = Path(tmp) / "script.py"
            script_path.write_text(script, encoding="utf-8")

            cmd = [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--tmpfs",
                "/tmp:size=64m",
                "--user",
                "nobody",
                "--memory",
                self._memory_limit,
                "--cpus",
                str(self._cpu_quota / self._cpu_period),
                "--pids-limit",
                str(self._pids_limit),
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "-v",
                f"{script_path}:/code/script.py:ro",
                self._image,
                "python",
                "/code/script.py",
                json.dumps(inputs),
            ]

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return {"error": "sandbox timeout", "duration_ms": int((time.monotonic() - started) * 1000)}
            except FileNotFoundError:
                return {
                    "error": "docker not available",
                    "duration_ms": int((time.monotonic() - started) * 1000),
                }

        if stderr:
            return {"error": stderr.decode()[:2000], "duration_ms": int((time.monotonic() - started) * 1000)}

        try:
            result = json.loads(stdout.decode())
        except Exception:
            return {"error": stdout.decode()[:2000], "duration_ms": int((time.monotonic() - started) * 1000)}

        result["duration_ms"] = int((time.monotonic() - started) * 1000)
        return result

    async def run_project(
        self, files: Dict[str, str], test_command: str = "python -m pytest -q", timeout: int = 120
    ) -> Dict[str, Any]:
        started = time.monotonic()

        with tempfile.TemporaryDirectory(prefix="nexus-docker-proj-") as tmp:
            workdir = Path(tmp)
            for rel_path, content in files.items():
                target = workdir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

            cmd = [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--tmpfs",
                "/tmp:size=128m",
                "--user",
                "nobody",
                "--memory",
                "512m",
                "--cpus",
                "1.0",
                "--pids-limit",
                "128",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "-v",
                f"{workdir}:/code:ro",
                self._image,
                "sh",
                "-c",
                f"cd /code && {test_command}",
            ]

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return {"error": "sandbox timeout", "duration_ms": int((time.monotonic() - started) * 1000)}
            except FileNotFoundError:
                return {
                    "error": "docker not available",
                    "duration_ms": int((time.monotonic() - started) * 1000),
                }

            return {
                "output": stdout.decode()[-2000:],
                "error": (stderr.decode() or stdout.decode())[-2000:] if proc.returncode else "",
                "duration_ms": int((time.monotonic() - started) * 1000),
            }


def _indent(code: str, spaces: int) -> str:
    return "\n".join(" " * spaces + line if line.strip() else line for line in code.splitlines())
