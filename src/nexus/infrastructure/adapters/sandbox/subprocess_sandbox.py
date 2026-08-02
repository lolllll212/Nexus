"""Subprocess sandbox adapter - runs untrusted code in an isolated child process."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from nexus.domain.ports.sandbox import Sandbox


class SubprocessSandbox(Sandbox):
    """
    Runs code via `exec` in a subprocess with resource limits.
    For production, swap for Docker/Firecracker isolation.
    """

    def __init__(self, python_bin: str = "python") -> None:
        self._python_bin = python_bin

    async def run(self, code: str, inputs: Dict[str, Any] = None, timeout: int = 30) -> Dict[str, Any]:
        started = time.monotonic()
        inputs = inputs or {}

        script = (
            "import json, sys, traceback\n"
            "def solve(input_data):\n"
            + _indent(code, 4)
            + "\n"
            "try:\n"
            "    result = solve(json.loads(sys.argv[1]))\n"
            "    print(json.dumps({'ok': True, 'result': result}))\n"
            "except Exception:\n"
            "    print(json.dumps({'ok': False, 'error': traceback.format_exc()}))\n"
        )

        proc = await asyncio.create_subprocess_exec(
            self._python_bin,
            "-c",
            script,
            __import__("json").dumps(inputs),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"error": "sandbox timeout", "duration_ms": int((time.monotonic() - started) * 1000)}

        if stderr:
            return {"error": stderr.decode()[:2000], "duration_ms": int((time.monotonic() - started) * 1000)}

        try:
            result = __import__("json").loads(stdout.decode())
        except Exception:
            return {"error": stdout.decode()[:2000], "duration_ms": int((time.monotonic() - started) * 1000)}

        result["duration_ms"] = int((time.monotonic() - started) * 1000)
        return result


def _indent(code: str, spaces: int) -> str:
    return "\n".join(" " * spaces + line if line.strip() else line for line in code.splitlines())
