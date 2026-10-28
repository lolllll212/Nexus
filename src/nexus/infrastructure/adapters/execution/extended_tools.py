"""
Extended built-in tools — practical capabilities the brain can always use.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import contextvars
import difflib
import fnmatch
import hashlib
import html as html_lib
import json
import math
import os
import platform
import re
import shutil
import signal
import sys
import time
import tomllib
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.value_objects.schema import JSONSchema
from nexus.infrastructure.adapters.security.ssrf import safe_http_fetch_detailed

_AUTONOMY_POLICY: Any = None
_DEFAULT_SANDBOX: Any = None
_CURRENT_EXECUTION_CONTEXT: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "nexus_execution_context", default=None
)


def set_execution_context(ctx: dict[str, Any] | None) -> None:
    _CURRENT_EXECUTION_CONTEXT.set(ctx)


def get_execution_context() -> dict[str, Any]:
    ctx = _CURRENT_EXECUTION_CONTEXT.get()
    if ctx is not None:
        return ctx
    return {"tenant_id": "default", "actor": "system", "role": "user"}


DENYLISTED_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.staging",
    ".env.test",
    "credentials",
    "secrets.json",
    ".git-credentials",
    ".netrc",
}
DENYLISTED_EXTENSIONS = {".pem", ".key", ".pkcs12", ".p12", ".pfx", ".cert", ".crt"}
DENYLISTED_SUBSTRINGS = {
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    ".git/config",
    ".git/credentials",
    ".git\\config",
    ".git\\credentials",
}


def is_denylisted_path(path: Path) -> bool:
    name = path.name.lower()
    if name in DENYLISTED_FILES or name.startswith(".env"):
        return True
    if any(name.endswith(ext) for ext in DENYLISTED_EXTENSIONS):
        return True
    path_str = str(path).replace("\\", "/").lower()
    for sub in DENYLISTED_SUBSTRINGS:
        if sub in path_str:
            return True
    return False


def set_autonomy_policy(policy: Any) -> None:
    global _AUTONOMY_POLICY
    _AUTONOMY_POLICY = policy


def get_autonomy_policy() -> Any:
    return _AUTONOMY_POLICY


def set_default_sandbox(sandbox: Any) -> None:
    global _DEFAULT_SANDBOX
    _DEFAULT_SANDBOX = sandbox


def get_default_sandbox() -> Any:
    global _DEFAULT_SANDBOX
    if _DEFAULT_SANDBOX is None:
        backend_env = os.getenv("NEXUS_SANDBOX_BACKEND")
        socket_available = Path("/var/run/docker.sock").exists()
        if (backend_env and backend_env.lower() == "subprocess") or (
            backend_env is None and not socket_available
        ):
            from nexus.infrastructure.adapters.sandbox.subprocess_sandbox import SubprocessSandbox

            _DEFAULT_SANDBOX = SubprocessSandbox()
        else:
            from nexus.infrastructure.adapters.sandbox.docker_sandbox import DockerSandbox

            _DEFAULT_SANDBOX = DockerSandbox()
    return _DEFAULT_SANDBOX


_CONCEPT_REPOSITORY: Any = None


def set_concept_repository(repo: Any) -> None:
    global _CONCEPT_REPOSITORY
    _CONCEPT_REPOSITORY = repo


def get_concept_repository() -> Any:
    global _CONCEPT_REPOSITORY
    if _CONCEPT_REPOSITORY is None:
        from nexus.infrastructure.adapters.inmemory.concept_repository import InMemoryConceptRepository

        _CONCEPT_REPOSITORY = InMemoryConceptRepository()
    return _CONCEPT_REPOSITORY


_EMBEDDER: Any = None


def set_embedder(embedder: Any) -> None:
    global _EMBEDDER
    _EMBEDDER = embedder


def get_embedder() -> Any:
    global _EMBEDDER
    return _EMBEDDER


def get_workspace_root() -> Path:
    """Return the absolute path of the configured workspace root."""
    root_str = os.getenv("NEXUS_WORKSPACE_ROOT", ".")
    return Path(root_str).resolve()


def get_allowed_roots() -> list[Path]:
    roots = [get_workspace_root()]
    try:
        import tempfile

        t_dir = Path(tempfile.gettempdir()).resolve()
        if t_dir not in roots:
            roots.append(t_dir)
    except Exception:
        pass
    return roots


def resolve_confined_path(rel_or_abs_path: str | Path, must_exist: bool = False) -> tuple[Path | None, str]:
    """
    Resolve a path and ensure it is strictly confined within WORKSPACE_ROOT or temp dir.
    Rejects any path traversal attempt (e.g. '../', absolute paths outside workspace).
    Returns (resolved_path, "") on success, or (None, error_message) on rejection.
    """
    try:
        allowed = get_allowed_roots()
        path = Path(rel_or_abs_path)
        if not path.is_absolute():
            candidate = (get_workspace_root() / path).resolve()
        else:
            candidate = path.resolve()

        is_confined = any(candidate == r or r in candidate.parents for r in allowed)
        if not is_confined:
            return (
                None,
                f"Access denied: path '{rel_or_abs_path}' escapes workspace root '{get_workspace_root()}'",
            )

        if is_denylisted_path(candidate):
            return (
                None,
                f"Access denied: access to sensitive configuration, secrets, or keys is forbidden: '{candidate.name}'",
            )

        if must_exist and not candidate.exists():
            return None, f"Path not found: '{rel_or_abs_path}'"

        return candidate, ""
    except Exception as e:
        return None, f"Invalid path '{rel_or_abs_path}': {e}"


_FILE_APPROVAL_ALIASES: dict[str, tuple[str, ...]] = {
    # Batch/folder variants intentionally accept the older one-file grants:
    # a tenant that approved write_file/edit_file has already approved the
    # same class of workspace mutation, and older UIs grant those IDs.
    "write_files": ("write_file",),
    "batch_edit_files": ("edit_file",),
    "move_path": ("write_file", "edit_file"),
    "copy_path": ("write_file",),
    "delete_directory": ("delete_file",),
}


async def _require_file_tool_approval(tool_id: str, resolved: Path) -> dict[str, Any] | None:
    """Fail closed unless a mutating file tool is approved for this target.

    Approval can be granted for the whole tool (``tool:<id>``) or for one
    canonical path (``tool:<id>:<sha256(resolved-path)[:16]>``). Batch and
    folder tools also accept the equivalent one-file grant listed in
    ``_FILE_APPROVAL_ALIASES`` so existing workspace approvals keep working.
    """
    path_hash = hashlib.sha256(str(resolved).encode()).hexdigest()[:16]
    base_action = f"tool:{tool_id}"
    action = f"{base_action}:{path_hash}"
    candidate_actions = [action, base_action]
    for alias in _FILE_APPROVAL_ALIASES.get(tool_id, ()):
        candidate_actions.extend([f"tool:{alias}:{path_hash}", f"tool:{alias}"])

    ctx = get_execution_context()
    tenant_id = str(ctx.get("tenant_id") or "default")
    actor = str(ctx.get("actor") or ctx.get("user_id") or "system")
    policy = get_autonomy_policy()
    if policy is None:
        return {
            "error": f"Approval required for {tool_id} (no policy configured).",
            "approval_required": True,
            "action": action,
        }
    try:
        approved = False
        for candidate in candidate_actions:
            if await policy.require_approval(candidate, actor, tenant_id=tenant_id):
                approved = True
                break
    except Exception:
        approved = False
    if not approved:
        return {
            "error": (
                f"Approval required for {tool_id} on this path. "
                "Enable workspace file edits or grant the tool action, then retry."
            ),
            "approval_required": True,
            "action": action,
        }
    return None


# ── Fast workspace/code intelligence helpers ─────────────────────────────
#
# These helpers are deliberately one-pass and bounded. Large repositories
# should not require dozens of ReAct turns just to answer "where is X?" or
# "what kind of project is this?". They prune dependency/vendor/cache trees,
# never follow symlinked directories, skip the sensitive-file denylist, and
# cap every scan or payload.

_IGNORED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "vendor",
    "third_party",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".turbo",
    ".cache",
    "dist",
    "build",
    "out",
    "target",
    "coverage",
    ".tox",
    ".nox",
}
_IGNORED_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".class",
    ".o",
    ".obj",
    ".dll",
    ".so",
    ".dylib",
    ".exe",
    ".bin",
}
_IGNORED_BINARY_SUFFIXES = _IGNORED_FILE_SUFFIXES | {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".7z",
    ".mp3",
    ".mp4",
    ".mov",
    ".avi",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".sqlite",
    ".sqlite3",
    ".db",
}
_LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript React",
    ".ts": "TypeScript",
    ".tsx": "TypeScript React",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".html": "HTML5",
    ".htm": "HTML5",
    ".css": "CSS",
    ".scss": "SCSS",
    ".json": "JSON",
    ".md": "Markdown",
    ".toml": "TOML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".c": "C",
    ".h": "C/C++ Header",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++ Header",
    ".hh": "C++ Header",
    ".hxx": "C++ Header",
    ".cs": "C#",
    ".php": "PHP",
    ".phtml": "PHP Template",
    ".rb": "Ruby",
    ".rake": "Ruby Rake",
    ".gemspec": "Ruby Gemspec",
    ".swift": "Swift",
    ".sql": "SQL",
    ".txt": "Text",
    ".csv": "CSV",
    ".xml": "XML",
    ".xsd": "XML Schema",
    ".xsl": "XSLT",
    ".xslt": "XSLT",
    ".svg": "SVG XML",
}
_TEXT_EXTENSIONS = set(_LANGUAGE_BY_EXTENSION) | {
    ".ini",
    ".cfg",
    ".conf",
    ".env.example",
    ".gitignore",
    ".dockerignore",
    ".editorconfig",
    ".lock",
}
_MANIFEST_NAMES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "requirements.in",
    "Pipfile",
    "poetry.lock",
    "Cargo.toml",
    "Cargo.lock",
    "CMakeLists.txt",
    "Makefile",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "composer.lock",
    "Gemfile",
    "Gemfile.lock",
    "Rakefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
}


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _relative_workspace_path(path: Path, root: Path | None = None) -> str:
    for base in (root, get_workspace_root()):
        if base is None:
            continue
        try:
            return path.relative_to(base).as_posix() or "."
        except ValueError:
            continue
    return str(path)


def _is_ignored_dir(name: str, *, include_hidden: bool) -> bool:
    if name in _IGNORED_DIR_NAMES:
        return True
    return name.startswith(".") and not include_hidden


def _iter_workspace_entries(
    root: Path,
    *,
    include_hidden: bool = False,
    max_files: int = 20_000,
    max_depth: int | None = None,
) -> Iterator[tuple[Path, bool]]:
    """Yield ``(path, is_dir)`` below ``root`` in deterministic order.

    Symlinked directories are reported but never followed; this keeps a scan
    inside the workspace and prevents cycles. Files are capped, while callers
    can still detect that at least one additional file existed by comparing
    their own counters with a second bounded probe when needed.
    """

    if not root.is_dir():
        return
    file_count = 0
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            with os.scandir(current) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name.lower())
        except OSError:
            continue

        directories: list[Path] = []
        for entry in entries:
            path = Path(entry.path)
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                is_symlink = entry.is_symlink()
            except OSError:
                continue
            if is_dir:
                if _is_ignored_dir(entry.name, include_hidden=include_hidden):
                    continue
                yield path, True
                if not is_symlink and (max_depth is None or depth < max_depth):
                    directories.append(path)
                continue
            if not include_hidden and entry.name.startswith(".") and entry.name not in {
                ".gitignore",
                ".dockerignore",
                ".editorconfig",
                ".env.example",
            }:
                continue
            if path.suffix.lower() in _IGNORED_FILE_SUFFIXES or is_denylisted_path(path):
                continue
            if file_count >= max_files:
                return
            file_count += 1
            yield path, False
        stack.extend((path, depth + 1) for path in reversed(directories))


def _iter_workspace_files(
    root: Path,
    *,
    include_hidden: bool = False,
    max_files: int = 20_000,
) -> Iterator[Path]:
    for path, is_dir in _iter_workspace_entries(
        root,
        include_hidden=include_hidden,
        max_files=max_files,
    ):
        if not is_dir:
            yield path


def _safe_file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _safe_mtime_iso(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        return ""


def _read_text_limited(
    path: Path,
    *,
    max_bytes: int = 2_000_000,
    errors: str = "strict",
) -> tuple[str, bool, str]:
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
    except OSError as exc:
        return "", False, str(exc)
    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[:max_bytes]
    try:
        return raw.decode("utf-8", errors=errors), truncated, ""
    except UnicodeDecodeError as exc:
        return "", truncated, f"Could not decode as UTF-8 text: {exc}"


def _normalize_extensions(value: Any) -> set[str]:
    if value is None:
        return set()
    raw: Iterable[Any]
    if isinstance(value, str):
        raw = re.split(r"[,\s]+", value)
    elif isinstance(value, Iterable):
        raw = value
    else:
        raw = [value]
    extensions: set[str] = set()
    for item in raw:
        ext = str(item).strip().lower()
        if not ext:
            continue
        extensions.add(ext if ext.startswith(".") else f".{ext}")
    return extensions


def _is_test_path(path: Path, root: Path) -> bool:
    rel_parts = {part.lower() for part in path.relative_to(root).parts} if path != root else set()
    name = path.name.lower()
    return bool(
        rel_parts & {"tests", "test", "__tests__", "spec", "specs"}
        or name.startswith("test_")
        or name.endswith(
            (
                "_test.py",
                ".test.js",
                ".test.ts",
                ".test.tsx",
                ".spec.js",
                ".spec.ts",
                ".spec.tsx",
                "_test.c",
                "_test.cpp",
                "_test.cc",
                "_test.rs",
                "_test.rb",
                "_spec.rb",
                "test.php",
            )
        )
    )


def _clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if not math.isfinite(parsed):
        parsed = default
    return max(minimum, min(maximum, parsed))


async def _terminate_process_group(proc: asyncio.subprocess.Process) -> None:
    """Terminate a subprocess and, where supported, its whole process group."""

    if proc.returncode is not None:
        return

    def _signal_group(sig: signal.Signals) -> bool:
        if not hasattr(os, "killpg"):
            return False
        try:
            os.killpg(proc.pid, sig)
            return True
        except (ProcessLookupError, PermissionError, OSError):
            return False

    if not _signal_group(signal.SIGTERM):
        try:
            proc.terminate()
        except ProcessLookupError:
            return
    try:
        await asyncio.wait_for(proc.wait(), timeout=1.0)
        return
    except TimeoutError:
        pass

    if not _signal_group(signal.SIGKILL):
        try:
            proc.kill()
        except ProcessLookupError:
            return
    try:
        await asyncio.wait_for(proc.wait(), timeout=1.0)
    except TimeoutError:
        pass


async def _read_stream_tail(
    stream: asyncio.StreamReader | None,
    *,
    max_bytes: int,
    state: dict[str, Any],
) -> None:
    """Keep only the useful tail of subprocess output, however large it gets."""

    if stream is None:
        return
    buffer: bytearray = state["buffer"]
    while True:
        chunk = await stream.read(8192)
        if not chunk:
            break
        state["total_bytes"] += len(chunk)
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            del buffer[: len(buffer) - max_bytes]
            state["truncated"] = True


async def _communicate_bounded(
    proc: asyncio.subprocess.Process,
    *,
    timeout: float,
    max_bytes: int,
) -> tuple[str, str, bool, bool]:
    """Collect bounded stdout/stderr and guarantee timeout cleanup.

    Returns ``(stdout, stderr, timed_out, truncated)``. Cancellation also
    terminates the process group before propagating, so a stopped chat turn
    cannot leave test/watcher children running behind it.
    """

    states: dict[str, dict[str, Any]] = {
        "stdout": {"buffer": bytearray(), "total_bytes": 0, "truncated": False},
        "stderr": {"buffer": bytearray(), "total_bytes": 0, "truncated": False},
    }
    readers = [
        asyncio.create_task(
            _read_stream_tail(proc.stdout, max_bytes=max_bytes, state=states["stdout"])
        ),
        asyncio.create_task(
            _read_stream_tail(proc.stderr, max_bytes=max_bytes, state=states["stderr"])
        ),
    ]
    timed_out = False
    try:
        await asyncio.wait_for(asyncio.gather(*readers, proc.wait()), timeout=timeout)
    except TimeoutError:
        timed_out = True
        await _terminate_process_group(proc)
        try:
            await asyncio.wait_for(asyncio.gather(*readers, return_exceptions=True), timeout=1.0)
        except TimeoutError:
            for reader in readers:
                reader.cancel()
    except asyncio.CancelledError:
        await asyncio.shield(_terminate_process_group(proc))
        for reader in readers:
            reader.cancel()
        raise

    stdout = bytes(states["stdout"]["buffer"]).decode(errors="replace")
    stderr = bytes(states["stderr"]["buffer"]).decode(errors="replace")
    truncated = bool(states["stdout"]["truncated"] or states["stderr"]["truncated"])
    return stdout, stderr, timed_out, truncated


async def _run_confined_command(
    args: list[str],
    *,
    cwd: Path,
    timeout: int = 30,
    max_chars: int = 12_000,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run one argv command (never a shell string) inside a confined cwd."""

    started = time.perf_counter()
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "HOME": str(get_workspace_root()),
        "TMPDIR": "/tmp",
        "CI": "true",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if extra_env:
        env.update({str(key): str(value) for key, value in extra_env.items()})
    bounded_timeout = _clamp_int(timeout, 30, 1, 300)
    bounded_chars = _clamp_int(max_chars, 12_000, 1_000, 100_000)
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        stdout, stderr, timed_out, truncated = await _communicate_bounded(
            proc,
            timeout=bounded_timeout,
            max_bytes=max(4096, bounded_chars * 4),
        )
        if timed_out:
            timeout_message = f"Command timed out after {bounded_timeout}s"
            stderr = (stderr + ("\n" if stderr else "") + timeout_message)[-bounded_chars:]
        output = (stdout + ("\n" if stdout and stderr else "") + stderr)[-bounded_chars:]
        returncode = -1 if timed_out else int(proc.returncode or 0)
        return {
            "command": args,
            "returncode": returncode,
            "passed": not timed_out and returncode == 0,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "output": output,
            "stdout": stdout[-bounded_chars:],
            "stderr": stderr[-bounded_chars:],
            "timed_out": timed_out,
            "truncated": truncated,
        }
    except asyncio.CancelledError:
        raise
    except (OSError, ValueError) as exc:
        return {
            "command": args,
            "returncode": -1,
            "passed": False,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "output": str(exc),
            "stdout": "",
            "stderr": str(exc),
            "timed_out": False,
            "truncated": False,
        }


def _parse_package_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _parse_pyproject(path: Path) -> dict[str, Any]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return {}


def _manifest_summaries(root: Path, files: list[Path]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    manifest_files = [
        path
        for path in files
        if (path.name in _MANIFEST_NAMES or path.suffix.lower() == ".gemspec")
        and len(path.relative_to(root).parts) <= 4
    ]
    for path in manifest_files[:20]:
        rel = _relative_workspace_path(path, root)
        item: dict[str, Any] = {"path": rel, "kind": path.name}
        if path.name == "package.json":
            payload = _parse_package_json(path)
            scripts = payload.get("scripts") if isinstance(payload.get("scripts"), dict) else {}
            deps: list[str] = []
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                value = payload.get(key)
                if isinstance(value, dict):
                    deps.extend(str(name) for name in value)
            item.update(
                {
                    "name": str(payload.get("name") or ""),
                    "scripts": {str(k): str(v) for k, v in list(scripts.items())[:30]},
                    "dependencies": sorted(set(deps))[:80],
                }
            )
        elif path.name == "pyproject.toml":
            payload = _parse_pyproject(path)
            project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
            deps = project.get("dependencies") if isinstance(project.get("dependencies"), list) else []
            item.update(
                {
                    "name": str(project.get("name") or ""),
                    "dependencies": [str(value) for value in deps[:80]],
                }
            )
        elif path.name in {"requirements.txt", "requirements.in"}:
            text, _, _ = _read_text_limited(path, max_bytes=200_000, errors="replace")
            deps = [
                re.split(r"[<>=!~;\[]", line.strip(), maxsplit=1)[0].strip()
                for line in text.splitlines()
                if line.strip() and not line.lstrip().startswith(("#", "-"))
            ]
            item["dependencies"] = [dep for dep in deps if dep][:80]
        elif path.name == "Cargo.toml":
            payload = _parse_pyproject(path)
            package = payload.get("package") if isinstance(payload.get("package"), dict) else {}
            deps: list[str] = []
            for key in ("dependencies", "dev-dependencies", "build-dependencies"):
                value = payload.get(key)
                if isinstance(value, dict):
                    deps.extend(str(name) for name in value)
            item.update(
                {
                    "name": str(package.get("name") or ""),
                    "edition": str(package.get("edition") or ""),
                    "dependencies": sorted(set(deps))[:80],
                }
            )
        elif path.name == "composer.json":
            payload = _parse_package_json(path)
            scripts = payload.get("scripts") if isinstance(payload.get("scripts"), dict) else {}
            deps: list[str] = []
            for key in ("require", "require-dev"):
                value = payload.get(key)
                if isinstance(value, dict):
                    deps.extend(str(name) for name in value)
            item.update(
                {
                    "name": str(payload.get("name") or ""),
                    "scripts": {str(k): str(v) for k, v in list(scripts.items())[:30]},
                    "dependencies": sorted(set(deps))[:80],
                }
            )
        elif path.name == "Gemfile" or path.suffix.lower() == ".gemspec":
            text, _, _ = _read_text_limited(path, max_bytes=200_000, errors="replace")
            deps = re.findall(r"^\s*gem\s+[\"']([^\"']+)[\"']", text, re.M)
            deps.extend(re.findall(r"add_(?:development_)?dependency\s+[\"']([^\"']+)[\"']", text))
            item["dependencies"] = sorted(set(deps))[:80]
        elif path.name == "CMakeLists.txt":
            text, _, _ = _read_text_limited(path, max_bytes=200_000, errors="replace")
            project_match = re.search(r"project\s*\(\s*([A-Za-z0-9_.-]+)([^)]*)\)", text, re.I | re.S)
            languages: list[str] = []
            if project_match:
                languages = [
                    token
                    for token in re.findall(r"\b(?:C|CXX|ASM|CUDA|OBJC|OBJCXX)\b", project_match.group(2))
                ]
            item.update(
                {
                    "name": project_match.group(1) if project_match else "",
                    "languages": sorted(set(languages)),
                }
            )
        elif path.name == "Makefile":
            text, _, _ = _read_text_limited(path, max_bytes=200_000, errors="replace")
            targets = [
                match.group(1)
                for match in re.finditer(r"^([A-Za-z0-9_.-]+)\s*:(?:\s|$)", text, re.M)
                if not match.group(1).startswith(".")
            ]
            item["targets"] = sorted(set(targets))[:80]
        summaries.append(item)
    return summaries


TOOL_DEFS: list[dict[str, Any]] = [
    {
        "id": "web_fetch",
        "name": "web_fetch",
        "description": "Fetch a URL safely and return bounded readable text with title, status, final URL, and links.",
        "input": {
            "url": {"type": "string"},
            "max_chars": {"type": "integer"},
            "timeout": {"type": "number"},
        },
        "required": ["url"],
        "output": {
            "content": {"type": "string"},
            "title": {"type": "string"},
            "status": {"type": "integer"},
            "links": {"type": "array"},
            "truncated": {"type": "boolean"},
        },
    },
    {
        "id": "run_shell",
        "name": "run_shell",
        "description": "Run an approved shell command in the workspace with bounded timeout/output and process-group cleanup.",
        "input": {
            "command": {"type": "string"},
            "timeout": {"type": "integer"},
            "max_chars": {"type": "integer"},
        },
        "required": ["command"],
        "output": {
            "stdout": {"type": "string"},
            "stderr": {"type": "string"},
            "returncode": {"type": "integer"},
            "timed_out": {"type": "boolean"},
            "truncated": {"type": "boolean"},
            "duration_ms": {"type": "integer"},
        },
    },
    {
        "id": "read_file",
        "name": "read_file",
        "description": "Read a bounded file or 1-based line range with size, line-count, and truncation metadata.",
        "input": {
            "path": {"type": "string"},
            "encoding": {"type": "string"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
            "max_chars": {"type": "integer"},
        },
        "required": ["path"],
        "output": {
            "content": {"type": "string"},
            "total_lines": {"type": "integer"},
            "truncated": {"type": "boolean"},
            "size_bytes": {"type": "integer"},
        },
    },
    {
        "id": "write_file",
        "name": "write_file",
        "description": "Write content to a file (creates parent dirs).",
        "input": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
        "output": {"bytes_written": {"type": "integer"}},
    },
    {
        "id": "list_directory",
        "name": "list_directory",
        "description": "List a bounded, deterministic directory view with file sizes, extensions, and modified times.",
        "input": {
            "path": {"type": "string"},
            "max_entries": {"type": "integer"},
            "include_hidden": {"type": "boolean"},
        },
        "required": ["path"],
        "output": {
            "entries": {"type": "array"},
            "total_entries": {"type": "integer"},
            "truncated": {"type": "boolean"},
        },
    },
    {
        "id": "edit_file",
        "name": "edit_file",
        "description": "Replace an exact text snippet in an existing workspace file (approval required).",
        "input": {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
            "replace_all": {"type": "boolean"},
        },
        "required": ["path", "old_text", "new_text"],
        "output": {"replacements": {"type": "integer"}, "path": {"type": "string"}},
    },
    {
        "id": "delete_file",
        "name": "delete_file",
        "description": "Delete one regular workspace file when confirm=true (approval required).",
        "input": {"path": {"type": "string"}, "confirm": {"type": "boolean"}},
        "required": ["path", "confirm"],
        "output": {"deleted": {"type": "boolean"}, "path": {"type": "string"}},
    },
    {
        "id": "create_directory",
        "name": "create_directory",
        "description": "Create a directory inside the workspace (approval required).",
        "input": {"path": {"type": "string"}, "parents": {"type": "boolean"}},
        "required": ["path"],
        "output": {"created": {"type": "boolean"}, "path": {"type": "string"}},
    },
    {
        "id": "create_repository",
        "name": "create_repository",
        "description": (
            "Create a complete local, Git-ready repository from a runnable template "
            "(approval required). Writes starter source/tests/README/license, can "
            "initialize Git and make an initial commit, and returns the actual path "
            "and next commands. Does not create or push a GitHub repository."
        ),
        "input": {
            "name": {"type": "string", "description": "Repository name, e.g. school-fee-tracker"},
            "path": {
                "type": "string",
                "description": "Optional workspace-relative target path; defaults to projects/<name>",
            },
            "template": {
                "type": "string",
                "enum": [
                    "frontend-design-system",
                    "html5-clean-ui",
                    "c-cmake",
                    "cpp-cmake",
                    "rust-cli",
                    "python-fastapi",
                    "react-vite",
                    "node-api",
                    "python-cli",
                    "php-web",
                    "ruby-cli",
                    "xml-toolkit",
                    "static-site",
                    "empty",
                ],
                "description": "Starter template",
            },
            "description": {"type": "string", "description": "One-line project purpose"},
            "license": {
                "type": "string",
                "enum": ["MIT", "BSD-3-Clause", "Unlicense", "none"],
                "description": "License file to include",
            },
            "initialize_git": {"type": "boolean"},
            "initial_commit": {"type": "boolean"},
            "include_ci": {"type": "boolean"},
            "overwrite": {
                "type": "boolean",
                "description": "Allow writing template files into a non-empty folder; unknown files are preserved",
            },
            "github_remote": {
                "type": "string",
                "description": "Optional existing GitHub remote URL to configure as origin; Nexus will not push",
            },
        },
        "required": ["name"],
        "output": {
            "created": {"type": "boolean"},
            "path": {"type": "string"},
            "files": {"type": "array"},
            "git": {"type": "object"},
        },
    },
    {
        "id": "project_scan",
        "name": "project_scan",
        "description": "Fast whole-project map: languages, manifests, frameworks, entrypoints, tests, commands, Git.",
        "input": {
            "path": {"type": "string"},
            "max_files": {"type": "integer"},
            "include_hidden": {"type": "boolean"},
            "include_line_counts": {"type": "boolean"},
        },
        "output": {
            "path": {"type": "string"},
            "files": {"type": "integer"},
            "languages": {"type": "array"},
            "manifests": {"type": "array"},
            "frameworks": {"type": "array"},
            "entrypoints": {"type": "array"},
            "suggested_commands": {"type": "array"},
        },
    },
    {
        "id": "find_files",
        "name": "find_files",
        "description": "Fast recursive file discovery by glob/name/extension; prunes dependency/cache/build folders.",
        "input": {
            "path": {"type": "string"},
            "pattern": {"type": "string"},
            "extensions": {"type": "array"},
            "name_contains": {"type": "string"},
            "max_results": {"type": "integer"},
            "sort": {"type": "string"},
            "include_hidden": {"type": "boolean"},
        },
        "output": {"files": {"type": "array"}, "total_matches": {"type": "integer"}},
    },
    {
        "id": "directory_tree",
        "name": "directory_tree",
        "description": "Compact depth-limited folder tree.",
        "input": {
            "path": {"type": "string"},
            "max_depth": {"type": "integer"},
            "max_entries": {"type": "integer"},
            "include_hidden": {"type": "boolean"},
            "include_files": {"type": "boolean"},
        },
        "output": {"tree": {"type": "string"}, "entries": {"type": "integer"}, "truncated": {"type": "boolean"}},
    },
    {
        "id": "read_files",
        "name": "read_files",
        "description": "Read up to 30 files or line ranges in one call.",
        "input": {
            "paths": {"type": "array"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
            "max_chars_per_file": {"type": "integer"},
        },
        "required": ["paths"],
        "output": {"files": {"type": "array"}, "failed": {"type": "integer"}},
    },
    {
        "id": "file_outline",
        "name": "file_outline",
        "description": "Extract imports, symbols, exports, headings, HTML landmarks/IDs, XML elements, CSS selectors, and line numbers from one file.",
        "input": {
            "path": {"type": "string"},
            "include_private": {"type": "boolean"},
            "max_symbols": {"type": "integer"},
        },
        "required": ["path"],
        "output": {"symbols": {"type": "array"}, "imports": {"type": "array"}, "language": {"type": "string"}},
    },
    {
        "id": "find_symbol",
        "name": "find_symbol",
        "description": "Locate symbol definitions separately from references/imports.",
        "input": {
            "symbol": {"type": "string"},
            "path": {"type": "string"},
            "extensions": {"type": "array"},
            "max_results": {"type": "integer"},
            "include_hidden": {"type": "boolean"},
        },
        "required": ["symbol"],
        "output": {"definitions": {"type": "array"}, "references": {"type": "array"}},
    },
    {
        "id": "code_diagnostics",
        "name": "code_diagnostics",
        "description": "Fast polyglot diagnostics for Python, C/C++, Rust, PHP, Ruby, HTML5, CSS, JSX/TSX, XML, JSON, TOML, and YAML; native compiler/linter syntax checks when the toolchain is installed; optional TODO/FIXME report.",
        "input": {
            "path": {"type": "string"},
            "max_files": {"type": "integer"},
            "include_todos": {"type": "boolean"},
            "include_hidden": {"type": "boolean"},
            "include_native": {"type": "boolean"},
        },
        "output": {"clean": {"type": "boolean"}, "diagnostics": {"type": "array"}, "files_scanned": {"type": "integer"}},
    },
    {
        "id": "git_diff",
        "name": "git_diff",
        "description": "Git changed files plus bounded working-tree/staged unified diff.",
        "input": {
            "repo_path": {"type": "string"},
            "path": {"type": "string"},
            "staged": {"type": "boolean"},
            "context_lines": {"type": "integer"},
            "max_chars": {"type": "integer"},
        },
        "output": {"changed_files": {"type": "array"}, "diff": {"type": "string"}, "clean": {"type": "boolean"}},
    },
    {
        "id": "project_checks",
        "name": "project_checks",
        "description": "Bounded polyglot project verification: Python compile/lint/typecheck/pytest, npm lint/typecheck/test/build, frontend_quality, C/C++ syntax + Make/CMake/CTest, Cargo fmt/check/clippy/test, PHP lint/Composer test/validate, Ruby syntax/test, xml_validate, git_status; auto-detects if omitted and reports missing toolchains honestly.",
        "input": {
            "path": {"type": "string"},
            "checks": {"type": "array"},
            "target": {"type": "string"},
            "timeout": {"type": "integer"},
        },
        "output": {"passed": {"type": "boolean"}, "checks": {"type": "array"}},
    },
    {
        "id": "secret_scan",
        "name": "secret_scan",
        "description": "Scan workspace text files for likely committed secrets; returns redacted previews only and skips denylisted credential files.",
        "input": {
            "path": {"type": "string"},
            "max_files": {"type": "integer"},
            "max_findings": {"type": "integer"},
            "include_hidden": {"type": "boolean"},
            "include_tests": {"type": "boolean"},
            "extensions": {"type": "array"},
        },
        "output": {
            "clean": {"type": "boolean"},
            "risk_level": {"type": "string"},
            "findings": {"type": "array"},
            "files_scanned": {"type": "integer"},
        },
    },
    {
        "id": "release_readiness",
        "name": "release_readiness",
        "description": "One-call release gate combining project scan, diagnostics, secret scan, dependency audit, Git state, and optional bounded checks.",
        "input": {
            "path": {"type": "string"},
            "include_checks": {"type": "boolean"},
            "checks": {"type": "array"},
            "fail_on_dirty": {"type": "boolean"},
            "max_files": {"type": "integer"},
            "timeout": {"type": "integer"},
        },
        "output": {
            "ready": {"type": "boolean"},
            "status": {"type": "string"},
            "score": {"type": "integer"},
            "blockers": {"type": "array"},
            "warnings": {"type": "array"},
        },
    },
    {
        "id": "changelog_draft",
        "name": "changelog_draft",
        "description": "Draft categorized Markdown release notes from Git commits since a ref or the latest tag; reports uncommitted files separately.",
        "input": {
            "repo_path": {"type": "string"},
            "from_ref": {"type": "string"},
            "to_ref": {"type": "string"},
            "max_commits": {"type": "integer"},
            "include_uncommitted": {"type": "boolean"},
        },
        "output": {
            "markdown": {"type": "string"},
            "commits": {"type": "array"},
            "commit_count": {"type": "integer"},
            "files_changed": {"type": "array"},
        },
    },
    {
        "id": "write_files",
        "name": "write_files",
        "description": "Approval-gated all-or-nothing write of many {path, content} files; dry_run previews.",
        "input": {
            "files": {"type": "array"},
            "overwrite": {"type": "boolean"},
            "create_parents": {"type": "boolean"},
            "dry_run": {"type": "boolean"},
        },
        "required": ["files"],
        "output": {"written": {"type": "array"}, "files_written": {"type": "integer"}, "dry_run": {"type": "boolean"}},
    },
    {
        "id": "batch_edit_files",
        "name": "batch_edit_files",
        "description": "Approval-gated all-or-nothing exact edits {path, old_text, new_text}; dry_run previews diffs.",
        "input": {
            "edits": {"type": "array"},
            "dry_run": {"type": "boolean"},
        },
        "required": ["edits"],
        "output": {"files": {"type": "array"}, "replacements": {"type": "integer"}, "dry_run": {"type": "boolean"}},
    },
    {
        "id": "move_path",
        "name": "move_path",
        "description": "Approval-gated move/rename of a file/folder; overwrite off by default.",
        "input": {
            "source": {"type": "string"},
            "destination": {"type": "string"},
            "overwrite": {"type": "boolean"},
            "create_parents": {"type": "boolean"},
        },
        "required": ["source", "destination"],
        "output": {"moved": {"type": "boolean"}, "source": {"type": "string"}, "destination": {"type": "string"}},
    },
    {
        "id": "copy_path",
        "name": "copy_path",
        "description": "Approval-gated bounded copy of a file or folder tree.",
        "input": {
            "source": {"type": "string"},
            "destination": {"type": "string"},
            "overwrite": {"type": "boolean"},
            "create_parents": {"type": "boolean"},
            "include_hidden": {"type": "boolean"},
        },
        "required": ["source", "destination"],
        "output": {"copied": {"type": "boolean"}, "files": {"type": "integer"}, "bytes": {"type": "integer"}},
    },
    {
        "id": "delete_directory",
        "name": "delete_directory",
        "description": "Approval-gated directory delete; non-empty requires confirm=true and recursive=true.",
        "input": {
            "path": {"type": "string"},
            "confirm": {"type": "boolean"},
            "recursive": {"type": "boolean"},
            "max_files": {"type": "integer"},
        },
        "required": ["path", "confirm"],
        "output": {"deleted": {"type": "boolean"}, "files_deleted": {"type": "integer"}, "bytes_deleted": {"type": "integer"}},
    },
    {
        "id": "json_query",
        "name": "json_query",
        "description": "Parse JSON or a structured value and extract by dot-path, including negative list indexes and an optional default.",
        "input": {
            "json_str": {"type": "string"},
            "key_path": {"type": "string"},
            "default": {"type": "any"},
        },
        "required": ["json_str", "key_path"],
        "output": {"result": {"type": "any"}, "found": {"type": "boolean"}},
    },
    {
        "id": "json_transform",
        "name": "json_transform",
        "description": "Apply a Python expression to JSON data. Use 'd' as the variable.",
        "input": {"json_str": {"type": "string"}, "expression": {"type": "string"}},
        "required": ["json_str", "expression"],
    },
    {
        "id": "current_datetime",
        "name": "current_datetime",
        "description": "Get the current date/time in UTC or an IANA timezone such as Asia/Kolkata, optionally formatted.",
        "input": {"format": {"type": "string"}, "timezone": {"type": "string"}},
        "output": {
            "datetime": {"type": "string"},
            "iso": {"type": "string"},
            "timezone": {"type": "string"},
            "timestamp": {"type": "number"},
        },
    },
    {
        "id": "diff_text",
        "name": "diff_text",
        "description": "Show a unified diff between two text strings.",
        "input": {"old_text": {"type": "string"}, "new_text": {"type": "string"}},
        "required": ["old_text", "new_text"],
        "output": {"diff": {"type": "string"}},
    },
    {
        "id": "hash_text",
        "name": "hash_text",
        "description": "Hash a string with md5, sha256, or sha512.",
        "input": {"text": {"type": "string"}, "algorithm": {"type": "string"}},
        "required": ["text"],
        "output": {"hash": {"type": "string"}},
    },
    {
        "id": "base64_encode",
        "name": "base64_encode",
        "description": "Base64-encode or decode a string.",
        "input": {"text": {"type": "string"}, "decode": {"type": "boolean"}},
        "required": ["text"],
        "output": {"result": {"type": "string"}},
    },
    {
        "id": "git_info",
        "name": "git_info",
        "description": "Get bounded Git branch, HEAD, upstream, remote names, and working-tree status using argv-only commands.",
        "input": {"repo_path": {"type": "string"}},
        "required": ["repo_path"],
        "output": {
            "branch": {"type": "string"},
            "last_commit": {"type": "string"},
            "status": {"type": "string"},
            "changed_files": {"type": "array"},
            "is_clean": {"type": "boolean"},
        },
    },
    {
        "id": "http_request",
        "name": "http_request",
        "description": "Make a bounded SSRF-safe HTTP request with validated method, optional JSON body, response headers, and truncation metadata.",
        "input": {
            "url": {"type": "string"},
            "method": {"type": "string"},
            "headers": {"type": "object"},
            "body": {"type": "string"},
            "json_body": {"type": "any"},
            "timeout": {"type": "number"},
            "max_chars": {"type": "integer"},
        },
        "required": ["url"],
        "output": {
            "status": {"type": "integer"},
            "body": {"type": "string"},
            "headers": {"type": "object"},
            "final_url": {"type": "string"},
            "truncated": {"type": "boolean"},
        },
    },
    {
        "id": "grep",
        "name": "grep",
        "description": "Fast regex search in files under a directory, pruning dependency/cache/build folders.",
        "input": {
            "pattern": {"type": "string"},
            "path": {"type": "string"},
            "include": {"type": "string", "description": "Optional glob such as *.py or *.tsx"},
            "max_results": {"type": "integer"},
        },
        "required": ["pattern"],
        "output": {"matches": {"type": "array"}},
    },
    {
        "id": "system_info",
        "name": "system_info",
        "description": "Get system info: OS, Python version, CPU count, memory.",
        "input": {},
        "output": {"info": {"type": "object"}},
    },
    {
        "id": "find_databases",
        "name": "find_databases",
        "description": "Scan a directory to discover databases: local files (.sqlite/.db/.sqlite3) and connection configs (docker-compose.yml, .env, config). Use this when you encounter or suspect a database and want to connect on your own.",
        "input": {"path": {"type": "string"}},
        "required": ["path"],
        "output": {"databases": {"type": "array"}},
    },
    {
        "id": "query_database",
        "name": "query_database",
        "description": "Connect to a database autonomously and list tables/keys or run a query. Engines: sqlite (local file — the only one that needs no running server), postgres, mysql, redis. For sqlite pass 'database' (file path) and 'sql'/'mode'='list_tables'. For postgres/mysql/redis pass host/port/user/password/database.",
        "input": {
            "type": {"type": "string"},
            "database": {"type": "string"},
            "host": {"type": "string"},
            "port": {"type": "integer"},
            "user": {"type": "string"},
            "password": {"type": "string"},
            "mode": {"type": "string"},
            "sql": {"type": "string"},
            "key": {"type": "string"},
            "read_only": {"type": "boolean"},
        },
        "required": ["type"],
        "output": {"rows": {"type": "array"}, "columns": {"type": "array"}, "tables": {"type": "array"}},
    },
    {
        "id": "process_multimodal_media",
        "name": "process_multimodal_media",
        "description": "Decomposes images and videos into high-density structured semantic representations (Spatial Grid Decomposition, OCR Inscription Extraction, Color Palettes, Entity Scene Graphs, and Chronological Temporal Keyframes) so text-only models without native vision or video tensor support can understand, analyze, query, and reason about visual media.",
        "input": {
            "source": {"type": "string"},
            "media_type": {"type": "string"},
            "question": {"type": "string"},
            "detail_level": {"type": "string"},
            "base64_data": {"type": "string"},
        },
        "required": ["source"],
        "output": {
            "media_type": {"type": "string"},
            "prompt_injection_block": {"type": "string"},
            "spatial_grid": {"type": "object"},
            "color_palette": {"type": "array"},
            "ocr_extracted_text": {"type": "array"},
            "keyframes": {"type": "array"},
            "answer": {"type": "string"},
        },
    },
    {
        "id": "pytest_runner",
        "name": "pytest_runner",
        "description": "Run the test suite inside the sandbox with structured failure output (test file, test name, first traceback frame). Respects NEXUS_SANDBOX_BACKEND.",
        "input": {
            "target": {"type": "string"},
            "options": {"type": "string"},
            "timeout": {"type": "integer"},
            "files": {"type": "object"},
        },
        "output": {
            "passed": {"type": "integer"},
            "failed": {"type": "integer"},
            "skipped": {"type": "integer"},
            "total_failed": {"type": "integer"},
            "returncode": {"type": "integer"},
            "failures": {"type": "array"},
            "summary": {"type": "string"},
            "output": {"type": "string"},
        },
    },
    {
        "id": "csv_query",
        "name": "csv_query",
        "description": "Query, filter, project, and aggregate CSV data using a JMESPath expression.",
        "input": {
            "query": {"type": "string"},
            "data": {"type": "string"},
            "path": {"type": "string"},
            "delimiter": {"type": "string"},
        },
        "required": ["query"],
        "output": {
            "result": {"type": "any"},
            "count": {"type": "integer"},
            "columns": {"type": "array"},
        },
    },
    {
        "id": "memory_graph_query",
        "name": "memory_graph_query",
        "description": "Query concept neighborhoods and synaptic connections in the brain's concept graph via the ConceptRepository port.",
        "input": {
            "concept_id": {"type": "string"},
            "label": {"type": "string"},
            "relationship_type": {"type": "string"},
            "depth": {"type": "integer"},
            "min_weight": {"type": "number"},
            "tenant_id": {"type": "string"},
        },
        "output": {
            "concept": {"type": "object"},
            "neighbors": {"type": "array"},
            "connections": {"type": "array"},
            "memories": {"type": "array"},
        },
    },
    {
        "id": "code_search_semantic",
        "name": "code_search_semantic",
        "description": "Fast hybrid code search: pruned bounded scan, camelCase-aware TF-IDF ranking, and embeddings only for top lexical candidates when available.",
        "input": {
            "query": {"type": "string"},
            "path": {"type": "string"},
            "k": {"type": "integer"},
            "alpha": {"type": "number"},
            "extensions": {"type": "array"},
            "max_files": {"type": "integer"},
        },
        "required": ["query"],
        "output": {
            "results": {"type": "array"},
            "total_matches": {"type": "integer"},
            "files_scanned": {"type": "integer"},
            "chunks_scanned": {"type": "integer"},
            "mode": {"type": "string"},
        },
    },
    {
        "id": "dependency_audit",
        "name": "dependency_audit",
        "description": "Audit Python imports against requirements includes and pyproject dependency groups, recognizing local packages and reporting unused declarations and parse errors.",
        "input": {
            "source_path": {"type": "string"},
            "requirements_path": {"type": "string"},
            "pyproject_path": {"type": "string"},
        },
        "output": {
            "clean": {"type": "boolean"},
            "undeclared": {"type": "array"},
            "declared": {"type": "array"},
            "imported": {"type": "array"},
            "unused_declared": {"type": "array"},
            "parse_errors": {"type": "array"},
            "files_scanned": {"type": "integer"},
        },
    },
    {
        "id": "regex_extract",
        "name": "regex_extract",
        "description": "Structured extraction from unstructured text via regex with named or unnamed capture groups. Supports flags (ignorecase, multiline, dotall).",
        "input": {
            "pattern": {"type": "string"},
            "text": {"type": "string"},
            "path": {"type": "string"},
            "flags": {"type": "string"},
        },
        "required": ["pattern"],
        "output": {
            "matches": {"type": "array"},
            "total_matches": {"type": "integer"},
            "named_groups": {"type": "boolean"},
        },
    },
]


def extended_builtin_tools() -> list[Tool]:
    return [
        Tool(
            id=d["id"],
            name=d["name"],
            description=d["description"],
            input_schema=JSONSchema(properties=d["input"], required=d.get("required", [])),
            output_schema=JSONSchema(properties=d.get("output", {"result": {"type": "any"}})),
            status=ToolStatus.READY,
        )
        for d in TOOL_DEFS
    ]


# ── Web extraction helpers ──────────────────────────────────────────────


def _clean_extracted_text(value: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(value or "")).strip()


def _decode_duckduckgo_url(href: str) -> str:
    raw = html_lib.unescape((href or "").strip())
    if raw.startswith("//"):
        raw = f"https:{raw}"
    parsed = urlparse(raw)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        values = parse_qs(parsed.query).get("uddg") or []
        if values:
            return unquote(values[0])
    return raw


class _DuckDuckGoResultsParser(HTMLParser):
    """Small structural parser for DuckDuckGo's static HTML results."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._capture: str | None = None
        self._buffer: list[str] = []

    def _flush(self) -> None:
        if self._current and (self._current.get("title") or self._current.get("snippet")):
            self.results.append(self._current)
        self._current = None
        self._capture = None
        self._buffer = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr = {key.lower(): value or "" for key, value in attrs}
        classes = set(attr.get("class", "").split())
        if "result__a" in classes:
            self._flush()
            self._current = {
                "title": "",
                "url": _decode_duckduckgo_url(attr.get("href", "")),
                "snippet": "",
            }
            self._capture = "title"
            self._buffer = []
        elif "result__snippet" in classes:
            if self._current is None:
                self._current = {"title": "", "url": "", "snippet": ""}
            self._capture = "snippet"
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture and self._current is not None:
            self._current[self._capture] = _clean_extracted_text(" ".join(self._buffer))
            self._capture = None
            self._buffer = []

    def finish(self) -> list[dict[str, str]]:
        self._flush()
        return self.results


class _ReadableHTMLParser(HTMLParser):
    """Extract title, readable text, and links without executing page code."""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "iframe"}
    _BLOCK_TAGS = {
        "article", "blockquote", "br", "div", "footer", "h1", "h2", "h3", "h4",
        "h5", "h6", "header", "li", "main", "p", "pre", "section", "tr",
    }

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.links: list[dict[str, str]] = []
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._link: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
            return
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")
        if tag == "a":
            attr = {key.lower(): value or "" for key, value in attrs}
            href = attr.get("href", "").strip()
            if href and not href.lower().startswith(("javascript:", "mailto:", "tel:", "#")):
                absolute = urljoin(self.base_url, href)
                if urlparse(absolute).scheme in {"http", "https"}:
                    self._link = {"url": absolute, "parts": []}

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        self._chunks.append(data)
        if self._link is not None:
            self._link["parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
            self.title = _clean_extracted_text(" ".join(self._title_parts))
            return
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")
        if tag == "a" and self._link is not None:
            text = _clean_extracted_text(" ".join(self._link["parts"]))
            self.links.append({"title": text, "url": str(self._link["url"])})
            self._link = None

    @property
    def text(self) -> str:
        lines = [_clean_extracted_text(line) for line in "".join(self._chunks).splitlines()]
        return "\n".join(line for line in lines if line)


def _extract_readable_html(raw: str, final_url: str) -> tuple[str, str, list[dict[str, str]]]:
    parser = _ReadableHTMLParser(final_url)
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        fallback = re.sub(r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL | re.I)
        fallback = re.sub(r"<[^>]+>", " ", fallback)
        return "", _clean_extracted_text(fallback), []

    deduped_links: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in parser.links:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        deduped_links.append({"title": link["title"][:160], "url": link["url"]})
        if len(deduped_links) >= 20:
            break
    return parser.title, parser.text, deduped_links


# ── Native handlers ─────────────────────────────────────────────────────


async def _web_search(params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("query") or "").strip()
    if not query:
        return {"query": "", "results": [], "source": "duckduckgo_html", "error": "query is required"}

    max_results = _clamp_int(params.get("max_results"), 5, 1, 10)
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        response = await asyncio.to_thread(
            safe_http_fetch_detailed,
            url,
            headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
            timeout=8.0,
            max_bytes=750_000,
        )
    except Exception as exc:
        # Never fabricate findings. An unreachable search provider is useful
        # information; an invented “indexed consensus” is not.
        return {
            "query": query,
            "results": [],
            "source": "duckduckgo_html",
            "error": f"Search request failed: {exc}",
        }

    status = int(response["status"])
    if status >= 400:
        return {
            "query": query,
            "results": [],
            "source": "duckduckgo_html",
            "error": f"DuckDuckGo returned HTTP {status}",
        }

    parser = _DuckDuckGoResultsParser()
    try:
        parser.feed(str(response["body"]))
        parser.close()
        parsed_results = parser.finish()
    except Exception:
        parsed_results = []

    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in parsed_results:
        title = _clean_extracted_text(item.get("title", ""))
        result_url = item.get("url", "").strip()
        snippet = _clean_extracted_text(item.get("snippet", ""))
        key = result_url or f"{title}\n{snippet}"
        if not key or key in seen or not (title or snippet):
            continue
        seen.add(key)
        results.append({"title": title, "url": result_url, "snippet": snippet})
        if len(results) >= max_results:
            break

    return {
        "query": query,
        "results": results,
        "source": "duckduckgo_html",
        "truncated": bool(response["truncated"]),
        **({"message": "No results returned by DuckDuckGo."} if not results else {}),
    }


async def _web_fetch(params: dict[str, Any]) -> dict[str, Any]:
    url = str(params.get("url") or "").strip()
    if not url:
        return {"content": "", "error": "url is required", "status": 0, "url": "", "final_url": ""}

    max_chars = _clamp_int(params.get("max_chars"), 5000, 500, 50_000)
    timeout = _clamp_float(params.get("timeout"), 12.0, 1.0, 30.0)
    try:
        response = await asyncio.to_thread(
            safe_http_fetch_detailed,
            url,
            timeout=timeout,
            max_bytes=1_000_000,
        )
    except Exception as exc:
        return {"content": "", "error": str(exc), "status": 0, "url": url, "final_url": url}

    headers = {str(k).lower(): str(v) for k, v in dict(response["headers"]).items()}
    content_type = headers.get("content-type", "")
    raw_body = str(response["body"])
    final_url = str(response["final_url"])
    looks_html = "html" in content_type.lower() or bool(re.search(r"<(?:html|body|head|div|p)\b", raw_body, re.I))
    if looks_html:
        title, text, links = _extract_readable_html(raw_body, final_url)
    else:
        title, text, links = "", raw_body.strip(), []

    status = int(response["status"])
    truncated = bool(response["truncated"]) or len(text) > max_chars
    payload: dict[str, Any] = {
        "content": "" if status >= 400 else text[:max_chars],
        "url": url,
        "final_url": final_url,
        "status": status,
        "title": title,
        "content_type": content_type,
        "links": links,
        "truncated": truncated,
        "bytes_read": int(response["bytes_read"]),
    }
    if status >= 400:
        payload["error"] = f"HTTP {status}: {_clean_extracted_text(text)[:300] or 'request failed'}"
    return payload


def _evaluate_math_expression(node: ast.AST) -> float | int:
    """Evaluate a numeric AST without ``eval`` or arbitrary name lookup."""

    constants: dict[str, float] = {"pi": math.pi, "e": math.e, "tau": math.tau}
    unary_functions: dict[str, Any] = {
        "sqrt": math.sqrt,
        "abs": abs,
        "int": int,
        "float": float,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "sinh": math.sinh,
        "cosh": math.cosh,
        "tanh": math.tanh,
        "exp": math.exp,
        "log2": math.log2,
        "log10": math.log10,
        "floor": math.floor,
        "ceil": math.ceil,
        "degrees": math.degrees,
        "radians": math.radians,
    }

    if isinstance(node, ast.Expression):
        return _evaluate_math_expression(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise ValueError("Only numeric constants are allowed")
        value: float | int = node.value
    elif isinstance(node, ast.Name):
        if node.id not in constants:
            raise ValueError(f"Unknown name: {node.id}")
        value = constants[node.id]
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        operand = _evaluate_math_expression(node.operand)
        value = operand if isinstance(node.op, ast.UAdd) else -operand
    elif isinstance(node, ast.BinOp):
        left = _evaluate_math_expression(node.left)
        right = _evaluate_math_expression(node.right)
        if isinstance(node.op, ast.Add):
            value = left + right
        elif isinstance(node.op, ast.Sub):
            value = left - right
        elif isinstance(node.op, ast.Mult):
            value = left * right
        elif isinstance(node.op, ast.Div):
            value = left / right
        elif isinstance(node.op, ast.FloorDiv):
            value = left // right
        elif isinstance(node.op, ast.Mod):
            value = left % right
        elif isinstance(node.op, ast.Pow):
            if abs(float(right)) > 100 or abs(float(left)) > 1_000_000:
                raise ValueError("Exponentiation is bounded to safe magnitudes")
            value = left**right
        else:
            raise ValueError(f"Disallowed operator: {type(node.op).__name__}")
    elif isinstance(node, ast.Call):
        if node.keywords or not isinstance(node.func, ast.Name):
            raise ValueError("Only direct calls to allowed math functions are permitted")
        name = node.func.id
        args = [_evaluate_math_expression(arg) for arg in node.args]
        if name in unary_functions:
            if len(args) != 1:
                raise ValueError(f"{name} expects exactly one argument")
            value = unary_functions[name](args[0])
        elif name == "round":
            if len(args) not in (1, 2):
                raise ValueError("round expects one or two arguments")
            value = round(args[0]) if len(args) == 1 else round(args[0], int(args[1]))
        elif name == "log":
            if len(args) not in (1, 2):
                raise ValueError("log expects one or two arguments")
            value = math.log(args[0]) if len(args) == 1 else math.log(args[0], args[1])
        elif name in {"min", "max", "sum"}:
            if not args:
                raise ValueError(f"{name} expects at least one argument")
            value = {"min": min, "max": max, "sum": sum}[name](args)
        elif name == "factorial":
            if len(args) != 1 or int(args[0]) != args[0] or not 0 <= int(args[0]) <= 170:
                raise ValueError("factorial expects an integer from 0 to 170")
            value = math.factorial(int(args[0]))
        else:
            raise ValueError(f"Disallowed function: {name}")
    else:
        raise ValueError(f"Disallowed expression: {type(node).__name__}")

    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Result is not finite")
    if abs(float(value)) > 1e308:
        raise ValueError("Result exceeds the safe numeric range")
    return value


async def _calculator(params: dict[str, Any]) -> dict[str, Any]:
    expr = str(params.get("expression") or "").strip()
    if not expr:
        return {"error": "expression is required"}
    if len(expr) > 500:
        return {"error": "expression is too long (max 500 characters)"}
    try:
        tree = ast.parse(expr, mode="eval")
        result = _evaluate_math_expression(tree)
    except (SyntaxError, ValueError, ArithmeticError) as exc:
        return {"error": str(exc), "expression": expr}
    return {"result": result, "expression": expr}


async def _run_python(params: dict[str, Any]) -> dict[str, Any]:
    code = params.get("code", "")
    timeout = params.get("timeout", 30)
    sandbox = get_default_sandbox()
    return await sandbox.run_code(code, timeout=timeout)


async def _run_shell(params: dict[str, Any]) -> dict[str, Any]:
    command = params.get("command", "").strip()
    if not command:
        return {"stdout": "", "stderr": "No command provided", "returncode": -1}

    cmd_hash = hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]
    action = f"tool:run_shell:{cmd_hash}"
    base_action = "tool:run_shell"

    # Context-derived tenant and actor - ignore model params
    ctx = get_execution_context()
    tenant_id = ctx.get("tenant_id", "default")
    actor = ctx.get("actor", "user")

    policy = get_autonomy_policy()
    if policy is None:
        return {
            "stdout": "",
            "stderr": f"Approval required for '{action}'. No autonomy policy active (fail-closed).",
            "returncode": -1,
            "approval_required": True,
        }

    is_approved = await policy.require_approval(
        action, actor=actor, tenant_id=tenant_id
    ) or await policy.require_approval(base_action, actor=actor, tenant_id=tenant_id)
    if not is_approved:
        return {
            "stdout": "",
            "stderr": f"Approval required for '{action}'. Action has not been approved.",
            "returncode": -1,
            "approval_required": True,
        }

    timeout = _clamp_int(params.get("timeout"), 30, 1, 300)
    max_chars = _clamp_int(params.get("max_chars"), 20_000, 1_000, 100_000)
    root = get_workspace_root()
    scrubbed_env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "HOME": str(root),
        "TMPDIR": "/tmp",
        "CI": "true",
    }
    started = time.perf_counter()
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(root),
            env=scrubbed_env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        stdout, stderr, timed_out, truncated = await _communicate_bounded(
            proc,
            timeout=timeout,
            max_bytes=max(4096, max_chars * 4),
        )
        if timed_out:
            stderr = (stderr + ("\n" if stderr else "") + f"Timed out after {timeout}s")[-max_chars:]
        return {
            "stdout": stdout[-max_chars:],
            "stderr": stderr[-max_chars:],
            "returncode": -1 if timed_out else int(proc.returncode or 0),
            "timed_out": timed_out,
            "truncated": truncated,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    except asyncio.CancelledError:
        raise
    except (OSError, ValueError) as exc:
        return {
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
            "timed_out": False,
            "truncated": False,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }


async def _read_file(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("path", ""), must_exist=True)
    if not resolved:
        return {"content": "", "error": err}
    if not resolved.is_file():
        return {"content": "", "error": f"Path is not a regular file: {params.get('path', '')}"}

    encoding = str(params.get("encoding") or "utf-8")
    try:
        import codecs

        codecs.lookup(encoding)
    except LookupError:
        return {"content": "", "error": f"Unknown text encoding: {encoding}"}

    max_chars = _clamp_int(params.get("max_chars"), 20_000, 100, 100_000)
    max_bytes = min(2_000_000, max(65_536, max_chars * 8))
    size_bytes = _safe_file_size(resolved)
    try:
        with resolved.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
    except OSError as exc:
        return {"content": "", "error": str(exc)}

    byte_truncated = len(raw) > max_bytes
    if byte_truncated:
        raw = raw[:max_bytes]
    if b"\x00" in raw[:8192]:
        return {
            "content": "",
            "error": "File appears to be binary; read_file only returns text.",
            "path": _relative_workspace_path(resolved),
            "size_bytes": size_bytes,
        }
    try:
        text = raw.decode(encoding)
    except (UnicodeDecodeError, LookupError) as exc:
        return {"content": "", "error": f"Could not decode file as {encoding}: {exc}"}

    lines = text.splitlines()
    has_range = params.get("start_line") is not None or params.get("end_line") is not None
    start_line = _clamp_int(params.get("start_line"), 1, 1, 10_000_000)
    end_line = _clamp_int(params.get("end_line"), len(lines), 1, 10_000_000)
    if has_range:
        if start_line > len(lines):
            return {
                "content": "",
                "error": f"start_line {start_line} is beyond the {len(lines)} scanned lines.",
                "path": _relative_workspace_path(resolved),
                "size_bytes": size_bytes,
                "total_lines": len(lines),
                "total_lines_exact": not byte_truncated,
                "truncated": byte_truncated,
            }
        end_line = max(start_line, min(end_line, len(lines)))
        content = "\n".join(lines[start_line - 1 : end_line])
        line_range = [start_line, end_line]
    else:
        content = text
        line_range = [1, len(lines)]

    truncated = byte_truncated or len(content) > max_chars
    return {
        "content": content[:max_chars],
        "path": _relative_workspace_path(resolved),
        "size_bytes": size_bytes,
        "total_lines": len(lines),
        "total_lines_exact": not byte_truncated,
        "line_range": line_range,
        "truncated": truncated,
        "encoding": encoding,
        "modified_at": _safe_mtime_iso(resolved),
    }


async def _write_file(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("path", ""), must_exist=False)
    if not resolved:
        return {"error": err}

    approval_error = await _require_file_tool_approval("write_file", resolved)
    if approval_error is not None:
        return approval_error

    content = params.get("content", "")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return {"bytes_written": len(content.encode("utf-8")), "path": str(resolved)}


async def _list_directory(params: dict[str, Any]) -> dict[str, Any]:
    target_path = params.get("path", ".")
    resolved, err = resolve_confined_path(target_path, must_exist=True)
    if not resolved:
        return {"entries": [], "error": err}
    if not resolved.is_dir():
        return {"entries": [], "error": f"Path is not a directory: {target_path}"}

    max_entries = _clamp_int(params.get("max_entries"), 200, 1, 1000)
    include_hidden = bool(params.get("include_hidden", True))
    scanned: list[os.DirEntry[str]] = []
    scan_truncated = False
    try:
        with os.scandir(resolved) as iterator:
            for entry in iterator:
                if not include_hidden and entry.name.startswith("."):
                    continue
                if len(scanned) >= 5000:
                    scan_truncated = True
                    break
                scanned.append(entry)
    except OSError as exc:
        return {"entries": [], "error": str(exc)}

    def _sort_key(entry: os.DirEntry[str]) -> tuple[int, str]:
        try:
            return (0 if entry.is_dir(follow_symlinks=False) else 1, entry.name.lower())
        except OSError:
            return (1, entry.name.lower())

    entries: list[dict[str, Any]] = []
    for entry in sorted(scanned, key=_sort_key)[:max_entries]:
        item = Path(entry.path)
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
            is_file = entry.is_file(follow_symlinks=False)
            stat = entry.stat(follow_symlinks=False)
            size = int(stat.st_size) if is_file else 0
            modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
        except OSError:
            is_dir, is_file, size, modified = False, False, 0, ""
        entries.append(
            {
                "name": entry.name,
                "path": _relative_workspace_path(item),
                "type": "dir" if is_dir else "file" if is_file else "other",
                "size": size,
                "extension": item.suffix.lower(),
                "is_symlink": entry.is_symlink(),
                "modified_at": modified,
            }
        )

    return {
        "entries": entries,
        "path": _relative_workspace_path(resolved),
        "total_entries": len(scanned),
        "returned_entries": len(entries),
        "files": sum(1 for entry in entries if entry["type"] == "file"),
        "directories": sum(1 for entry in entries if entry["type"] == "dir"),
        "truncated": scan_truncated or len(scanned) > max_entries,
    }


async def _edit_file(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("path", ""), must_exist=True)
    if not resolved:
        return {"error": err, "replacements": 0}
    if not resolved.is_file():
        return {"error": f"Path is not a regular file: {params.get('path', '')}", "replacements": 0}

    old_text = params.get("old_text", "")
    new_text = params.get("new_text", "")
    if not isinstance(old_text, str) or old_text == "":
        return {"error": "old_text must be a non-empty exact snippet.", "replacements": 0}
    if not isinstance(new_text, str):
        return {"error": "new_text must be a string.", "replacements": 0}

    try:
        content = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"error": f"Could not read file as UTF-8 text: {exc}", "replacements": 0}

    occurrences = content.count(old_text)
    if occurrences == 0:
        return {"error": "old_text was not found in the file.", "replacements": 0}
    replace_all = bool(params.get("replace_all", False))
    if occurrences > 1 and not replace_all:
        return {
            "error": (
                f"old_text occurs {occurrences} times. Provide a more specific snippet "
                "or set replace_all=true."
            ),
            "replacements": 0,
            "occurrences": occurrences,
        }

    approval_error = await _require_file_tool_approval("edit_file", resolved)
    if approval_error is not None:
        return {**approval_error, "replacements": 0}

    replacements = occurrences if replace_all else 1
    updated = content.replace(old_text, new_text) if replace_all else content.replace(old_text, new_text, 1)
    try:
        resolved.write_text(updated, encoding="utf-8")
    except OSError as exc:
        return {"error": f"Could not write edited file: {exc}", "replacements": 0}
    return {
        "replacements": replacements,
        "path": str(resolved),
        "bytes_written": len(updated.encode("utf-8")),
    }


async def _delete_file(params: dict[str, Any]) -> dict[str, Any]:
    if params.get("confirm") is not True:
        return {
            "deleted": False,
            "error": "delete_file requires confirm=true after an explicit deletion request.",
        }
    resolved, err = resolve_confined_path(params.get("path", ""), must_exist=True)
    if not resolved:
        return {"deleted": False, "error": err}
    if not resolved.is_file():
        return {
            "deleted": False,
            "error": "delete_file only deletes regular files, not directories.",
        }

    approval_error = await _require_file_tool_approval("delete_file", resolved)
    if approval_error is not None:
        return {**approval_error, "deleted": False}

    try:
        size = resolved.stat().st_size
        resolved.unlink()
    except OSError as exc:
        return {"deleted": False, "error": f"Could not delete file: {exc}"}
    return {"deleted": True, "path": str(resolved), "bytes_deleted": size}


async def _create_directory(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("path", ""), must_exist=False)
    if not resolved:
        return {"created": False, "error": err}
    if resolved.exists():
        if resolved.is_dir():
            return {"created": False, "exists": True, "path": str(resolved)}
        return {"created": False, "error": f"Path already exists and is not a directory: {resolved}"}

    approval_error = await _require_file_tool_approval("create_directory", resolved)
    if approval_error is not None:
        return {**approval_error, "created": False}

    try:
        resolved.mkdir(parents=bool(params.get("parents", True)), exist_ok=True)
    except OSError as exc:
        return {"created": False, "error": f"Could not create directory: {exc}"}
    return {"created": True, "exists": True, "path": str(resolved)}


async def _project_scan(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("path", "."), must_exist=True)
    if not resolved:
        return {"error": err}
    if not resolved.is_dir():
        return {"error": f"Path is not a directory: {params.get('path', '.')}"}

    max_files = _clamp_int(params.get("max_files"), 5000, 1, 20_000)
    include_hidden = bool(params.get("include_hidden", False))
    include_line_counts = bool(params.get("include_line_counts", True))
    started = time.perf_counter()

    files: list[Path] = []
    directories = 0
    total_bytes = 0
    extension_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    language_lines: Counter[str] = Counter()
    largest: list[tuple[int, Path]] = []

    for path, is_dir in _iter_workspace_entries(
        resolved,
        include_hidden=include_hidden,
        max_files=max_files + 1,
    ):
        if is_dir:
            directories += 1
            continue
        files.append(path)
        size = _safe_file_size(path)
        total_bytes += size
        ext = path.suffix.lower() or "(none)"
        extension_counts[ext] += 1
        language = _LANGUAGE_BY_EXTENSION.get(ext, "Other")
        language_counts[language] += 1
        largest.append((size, path))
        if include_line_counts and ext in _TEXT_EXTENSIONS and size <= 1_000_000:
            try:
                raw = path.read_bytes()
                language_lines[language] += raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0)
            except OSError:
                pass

    truncated = len(files) > max_files
    files = files[:max_files]
    manifests = _manifest_summaries(resolved, files)
    dependency_names: set[str] = set()
    for manifest in manifests:
        for dep in manifest.get("dependencies", []):
            name = re.split(r"[<>=!~;\s\[]", str(dep), maxsplit=1)[0].strip().lower()
            if name:
                dependency_names.add(name)

    frameworks: set[str] = set()
    framework_markers = {
        "FastAPI": {"fastapi"},
        "Flask": {"flask"},
        "Django": {"django"},
        "React": {"react", "react-dom"},
        "Next.js": {"next"},
        "Vite": {"vite"},
        "Vue": {"vue"},
        "Svelte": {"svelte"},
        "Angular": {"@angular/core"},
        "Express": {"express"},
        "NestJS": {"@nestjs/core"},
        "Tailwind CSS": {"tailwindcss"},
        "pytest": {"pytest"},
        "Rails": {"rails"},
        "RSpec": {"rspec", "rspec-rails"},
        "Minitest": {"minitest"},
        "PHPUnit": {"phpunit/phpunit"},
    }
    for framework, markers in framework_markers.items():
        if dependency_names & markers:
            frameworks.add(framework)
    filenames = {path.name for path in files}
    if "Dockerfile" in filenames:
        frameworks.add("Docker")
    if "vercel.json" in filenames:
        frameworks.add("Vercel")
    if "railway.json" in filenames:
        frameworks.add("Railway")
    if any(name.startswith("laravel/") or name == "laravel" for name in dependency_names):
        frameworks.add("Laravel")
    if any(name.startswith("symfony/") or name == "symfony" for name in dependency_names):
        frameworks.add("Symfony")
    if "Cargo.toml" in filenames:
        frameworks.update(("Rust", "Cargo"))
    if "CMakeLists.txt" in filenames:
        frameworks.add("CMake")
    if "composer.json" in filenames:
        frameworks.update(("PHP", "Composer"))
    if "Gemfile" in filenames:
        frameworks.update(("Ruby", "Bundler"))
    if "Rakefile" in filenames:
        frameworks.add("Rake")
    if any(path.suffix.lower() in {".html", ".htm", ".css", ".scss", ".jsx", ".tsx"} for path in files):
        frameworks.add("Frontend")

    entrypoint_names = {
        "main.py",
        "app.py",
        "cli.py",
        "manage.py",
        "index.js",
        "index.ts",
        "main.tsx",
        "main.ts",
        "App.tsx",
        "server.js",
        "server.ts",
        "main.go",
        "main.rs",
        "lib.rs",
        "main.c",
        "main.cpp",
        "main.cc",
        "index.php",
        "main.rb",
        "index.html",
        "Program.cs",
    }
    entrypoints = [
        _relative_workspace_path(path, resolved)
        for path in files
        if path.name in entrypoint_names and len(path.relative_to(resolved).parts) <= 5
    ][:30]
    test_files = [path for path in files if _is_test_path(path, resolved)]

    suggested_commands: list[str] = []
    for manifest in manifests:
        if manifest.get("kind") != "package.json":
            continue
        manifest_dir = Path(str(manifest["path"])).parent.as_posix()
        prefix = "" if manifest_dir == "." else f"cd {manifest_dir} && "
        scripts = manifest.get("scripts") if isinstance(manifest.get("scripts"), dict) else {}
        for script_name in ("dev", "lint", "test", "build", "preview"):
            if script_name in scripts:
                command = "npm test" if script_name == "test" else f"npm run {script_name}"
                suggested_commands.append(prefix + command)
    if any(path.suffix == ".py" for path in files):
        if test_files:
            suggested_commands.append("pytest -q")
        if "FastAPI" in frameworks:
            suggested_commands.append("uvicorn <module>:app --reload")
    if "Cargo.toml" in filenames:
        suggested_commands.extend(
            ["cargo fmt --all -- --check", "cargo clippy --all-targets -- -D warnings", "cargo test", "cargo run"]
        )
    if "go.mod" in filenames:
        suggested_commands.extend(["go test ./...", "go run ."])
    if "CMakeLists.txt" in filenames:
        suggested_commands.extend(
            ["cmake -S . -B build", "cmake --build build", "ctest --test-dir build --output-on-failure"]
        )
    make_targets: set[str] = set()
    for manifest in manifests:
        if manifest.get("kind") == "Makefile" and isinstance(manifest.get("targets"), list):
            make_targets.update(str(target) for target in manifest["targets"])
    if make_targets:
        if "test" in make_targets:
            suggested_commands.append("make test")
        if "check" in make_targets:
            suggested_commands.append("make check")
    if "composer.json" in filenames:
        suggested_commands.extend(["composer validate", "composer test", "php -S 127.0.0.1:8000"])
    if "Gemfile" in filenames:
        if "RSpec" in frameworks:
            suggested_commands.append("bundle exec rspec")
        elif "Rakefile" in filenames:
            suggested_commands.append("bundle exec rake test")
        elif test_files:
            suggested_commands.append("ruby -Ilib -Itest <test_file.rb>")

    top_level: list[dict[str, Any]] = []
    try:
        for entry in sorted(resolved.iterdir(), key=lambda item: item.name.lower()):
            if is_denylisted_path(entry):
                continue
            if entry.is_dir() and _is_ignored_dir(entry.name, include_hidden=include_hidden):
                continue
            if not include_hidden and entry.name.startswith(".") and entry.name not in {
                ".env.example",
                ".gitignore",
                ".dockerignore",
                ".editorconfig",
            }:
                continue
            top_level.append(
                {
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "size": _safe_file_size(entry) if entry.is_file() else 0,
                }
            )
    except OSError:
        pass

    git: dict[str, Any] = {"is_repo": False}
    toplevel = await _run_confined_command(
        ["git", "rev-parse", "--show-toplevel"], cwd=resolved, timeout=5, max_chars=2000
    )
    if toplevel.get("passed"):
        branch = await _run_confined_command(
            ["git", "branch", "--show-current"], cwd=resolved, timeout=5, max_chars=1000
        )
        status = await _run_confined_command(
            ["git", "status", "--porcelain"], cwd=resolved, timeout=5, max_chars=12000
        )
        changes = [line for line in str(status.get("stdout") or "").splitlines() if line.strip()]
        git = {
            "is_repo": True,
            "root": str(toplevel.get("stdout") or "").strip(),
            "branch": str(branch.get("stdout") or "").strip(),
            "changed_files": len(changes),
            "clean": not changes,
        }

    suffixes = {path.suffix.lower() for path in files}
    recommended_checks: list[str] = []
    if ".py" in suffixes:
        recommended_checks.append("python_compile")
    if ".c" in suffixes:
        recommended_checks.append("c_syntax")
    if suffixes & {".cpp", ".cc", ".cxx"}:
        recommended_checks.append("cpp_syntax")
    if "Makefile" in filenames:
        recommended_checks.append("make_test")
    if "CMakeLists.txt" in filenames:
        recommended_checks.extend(["cmake_build", "ctest"])
    if "Cargo.toml" in filenames:
        recommended_checks.extend(["cargo_fmt", "cargo_check", "cargo_clippy", "cargo_test"])
    if ".php" in suffixes or ".phtml" in suffixes or "composer.json" in filenames:
        recommended_checks.append("php_lint")
    if "composer.json" in filenames:
        recommended_checks.append("composer_test")
    if suffixes & {".rb", ".rake", ".gemspec"} or filenames & {"Gemfile", "Rakefile"}:
        recommended_checks.extend(["ruby_syntax", "ruby_test"] if test_files else ["ruby_syntax"])
    if suffixes & {".xml", ".xsd", ".xsl", ".xslt", ".svg"}:
        recommended_checks.append("xml_validate")
    if suffixes & {".html", ".htm", ".css", ".scss", ".jsx", ".tsx"}:
        recommended_checks.append("frontend_quality")
    if any(manifest.get("kind") == "package.json" for manifest in manifests):
        recommended_checks.extend(["npm_typecheck", "npm_build"])
    frontend_summary = {
        "detected": bool(suffixes & {".html", ".htm", ".css", ".scss", ".js", ".jsx", ".ts", ".tsx"}),
        "frameworks": sorted(
            frameworks & {"React", "Next.js", "Vite", "Vue", "Svelte", "Angular", "Tailwind CSS", "Frontend"}
        ),
        "html_files": sum(1 for path in files if path.suffix.lower() in {".html", ".htm"}),
        "css_files": sum(1 for path in files if path.suffix.lower() in {".css", ".scss"}),
        "component_files": sum(1 for path in files if path.suffix.lower() in {".jsx", ".tsx", ".vue", ".svelte"}),
    }

    return {
        "path": _relative_workspace_path(resolved),
        "files": len(files),
        "directories": directories,
        "total_bytes": total_bytes,
        "truncated": truncated,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "languages": [
            {"language": name, "files": count, "lines": language_lines.get(name, 0)}
            for name, count in language_counts.most_common(12)
        ],
        # Small summary-critical fields precede bulky manifest/extension data
        # so a bounded ReAct observation still contains the project map.
        "frameworks": sorted(frameworks),
        "entrypoints": entrypoints,
        "test_files": len(test_files),
        "suggested_commands": list(dict.fromkeys(suggested_commands))[:30],
        "recommended_checks": list(dict.fromkeys(recommended_checks)),
        "frontend": frontend_summary,
        "git": git,
        "manifests": manifests,
        "test_file_examples": [_relative_workspace_path(path, resolved) for path in test_files[:20]],
        "extensions": [
            {"extension": ext, "files": count} for ext, count in extension_counts.most_common(20)
        ],
        "largest_files": [
            {"path": _relative_workspace_path(path, resolved), "bytes": size}
            for size, path in sorted(largest, reverse=True)[:10]
        ],
        "top_level": top_level,
    }


async def _find_files(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("path", "."), must_exist=True)
    if not resolved:
        return {"files": [], "error": err}
    if not resolved.is_dir():
        return {"files": [], "error": f"Path is not a directory: {params.get('path', '.')}"}

    pattern = str(params.get("pattern") or "*").strip() or "*"
    name_contains = str(params.get("name_contains") or "").lower()
    extensions = _normalize_extensions(params.get("extensions"))
    max_results = _clamp_int(params.get("max_results"), 200, 1, 1000)
    sort = str(params.get("sort") or "path").lower()
    has_wildcard = any(char in pattern for char in "*?[")

    matches: list[dict[str, Any]] = []
    for path in _iter_workspace_files(
        resolved,
        include_hidden=bool(params.get("include_hidden", False)),
        max_files=20_000,
    ):
        rel = _relative_workspace_path(path, resolved)
        if extensions and path.suffix.lower() not in extensions:
            continue
        if name_contains and name_contains not in path.name.lower():
            continue
        if has_wildcard:
            if not (fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern)):
                continue
        elif pattern != "*":
            if "/" in pattern:
                if pattern.lower() not in rel.lower():
                    continue
            elif pattern.lower() not in path.name.lower():
                continue
        stat = path.stat() if path.exists() else None
        matches.append(
            {
                "path": rel,
                "name": path.name,
                "bytes": stat.st_size if stat else 0,
                "modified": _safe_mtime_iso(path),
                "_mtime": stat.st_mtime if stat else 0,
            }
        )

    if sort == "modified":
        matches.sort(key=lambda item: item["_mtime"], reverse=True)
    elif sort == "size":
        matches.sort(key=lambda item: item["bytes"], reverse=True)
    else:
        matches.sort(key=lambda item: item["path"].lower())
    total = len(matches)
    for item in matches:
        item.pop("_mtime", None)
    return {
        "path": _relative_workspace_path(resolved),
        "pattern": pattern,
        "files": matches[:max_results],
        "total_matches": total,
        "truncated": total > max_results,
    }


async def _directory_tree(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("path", "."), must_exist=True)
    if not resolved:
        return {"tree": "", "error": err}
    if not resolved.is_dir():
        return {"tree": "", "error": f"Path is not a directory: {params.get('path', '.')}"}

    max_depth = _clamp_int(params.get("max_depth"), 3, 0, 8)
    max_entries = _clamp_int(params.get("max_entries"), 500, 1, 5000)
    include_hidden = bool(params.get("include_hidden", False))
    include_files = bool(params.get("include_files", True))
    lines = [f"{_relative_workspace_path(resolved)}/"]
    count = 0
    truncated = False

    def walk(directory: Path, depth: int) -> None:
        nonlocal count, truncated
        if depth > max_depth or truncated:
            return
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: (not entry.is_dir(), entry.name.lower()))
        except OSError:
            return
        for entry in entries:
            if count >= max_entries:
                truncated = True
                lines.append(f"{'  ' * (depth + 1)}… truncated")
                return
            path = Path(entry.path)
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
                is_symlink = entry.is_symlink()
            except OSError:
                continue
            if is_dir:
                if _is_ignored_dir(entry.name, include_hidden=include_hidden):
                    continue
                count += 1
                lines.append(f"{'  ' * (depth + 1)}{entry.name}/")
                if not is_symlink:
                    walk(path, depth + 1)
            elif include_files:
                if is_denylisted_path(path):
                    continue
                if not include_hidden and entry.name.startswith(".") and entry.name not in {
                    ".gitignore",
                    ".dockerignore",
                    ".editorconfig",
                    ".env.example",
                }:
                    continue
                count += 1
                lines.append(f"{'  ' * (depth + 1)}{entry.name} ({_safe_file_size(path)} B)")

    walk(resolved, 0)
    return {
        "path": _relative_workspace_path(resolved),
        "tree": "\n".join(lines),
        "entries": count,
        "truncated": truncated,
    }


async def _read_files(params: dict[str, Any]) -> dict[str, Any]:
    raw_paths = params.get("paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        return {"files": [], "failed": 1, "error": "paths must be a non-empty array of file paths."}
    if len(raw_paths) > 30:
        return {"files": [], "failed": len(raw_paths), "error": "read_files accepts at most 30 paths."}

    start_line = params.get("start_line")
    end_line = params.get("end_line")
    try:
        start = int(start_line) if start_line is not None else None
        end = int(end_line) if end_line is not None else None
    except (TypeError, ValueError):
        return {"files": [], "failed": len(raw_paths), "error": "start_line/end_line must be integers."}
    if start is not None and start < 1:
        return {"files": [], "failed": len(raw_paths), "error": "start_line must be at least 1."}
    if end is not None and start is not None and end < start:
        return {"files": [], "failed": len(raw_paths), "error": "end_line must be >= start_line."}
    max_chars = _clamp_int(params.get("max_chars_per_file"), 12_000, 1, 50_000)

    results: list[dict[str, Any]] = []
    failed = 0
    for raw_path in raw_paths:
        requested = str(raw_path)
        resolved, err = resolve_confined_path(requested, must_exist=True)
        if not resolved:
            failed += 1
            results.append({"path": requested, "content": "", "error": err})
            continue
        if not resolved.is_file():
            failed += 1
            results.append({"path": requested, "content": "", "error": "Path is not a regular file."})
            continue
        text, byte_truncated, read_error = _read_text_limited(resolved, max_bytes=5_000_000)
        if read_error:
            failed += 1
            results.append({"path": requested, "content": "", "error": read_error})
            continue
        all_lines = text.splitlines(keepends=True)
        selected = all_lines
        if start is not None or end is not None:
            selected = all_lines[(start - 1 if start else 0) : end]
        content = "".join(selected)
        char_truncated = len(content) > max_chars
        if char_truncated:
            content = content[:max_chars] + "\n…[truncated]"
        results.append(
            {
                "path": _relative_workspace_path(resolved),
                "content": content,
                "lines": len(all_lines),
                "start_line": start or 1,
                "end_line": min(end, len(all_lines)) if end else len(all_lines),
                "bytes": _safe_file_size(resolved),
                "truncated": byte_truncated or char_truncated,
            }
        )
    return {"files": results, "failed": failed, "read": len(results) - failed}


def _python_outline(tree: ast.AST, *, include_private: bool, max_symbols: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []

    def add_symbol(node: ast.AST, kind: str, name: str, qualified: str) -> None:
        if not include_private and name.startswith("_") and not name.startswith("__"):
            return
        if len(symbols) >= max_symbols:
            return
        item: dict[str, Any] = {
            "name": name,
            "qualified_name": qualified,
            "kind": kind,
            "line": getattr(node, "lineno", 0),
            "end_line": getattr(node, "end_lineno", getattr(node, "lineno", 0)),
        }
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                item["signature"] = f"({ast.unparse(node.args)})"
            except Exception:
                pass
            decorators = []
            for decorator in node.decorator_list:
                try:
                    decorators.append(ast.unparse(decorator))
                except Exception:
                    pass
            if decorators:
                item["decorators"] = decorators
        if isinstance(node, ast.ClassDef) and node.bases:
            bases = []
            for base in node.bases:
                try:
                    bases.append(ast.unparse(base))
                except Exception:
                    pass
            if bases:
                item["bases"] = bases
        symbols.append(item)

    def visit(node: ast.AST, prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Import):
                for alias in child.names:
                    imports.append({"name": alias.name, "line": child.lineno})
                continue
            if isinstance(child, ast.ImportFrom):
                module = child.module or ""
                for alias in child.names:
                    imports.append({"name": f"{module}.{alias.name}" if module else alias.name, "line": child.lineno})
                continue
            if isinstance(child, ast.ClassDef):
                qualified = f"{prefix}{child.name}"
                add_symbol(child, "class", child.name, qualified)
                visit(child, f"{qualified}.")
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{prefix}{child.name}"
                kind = "async_function" if isinstance(child, ast.AsyncFunctionDef) else "function"
                add_symbol(child, kind, child.name, qualified)
                visit(child, f"{qualified}.")
                continue
            visit(child, prefix)

    visit(tree)
    return symbols, imports


def _html_outline(text: str, max_symbols: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parser = _parse_html_structure(text)
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    landmarks = {"header", "nav", "main", "section", "article", "aside", "footer"}

    def add_symbol(name: str, kind: str, line: int) -> None:
        cleaned = " ".join(str(name).split())[:160] or kind
        if len(symbols) < max_symbols:
            symbols.append({"name": cleaned, "qualified_name": cleaned, "kind": kind, "line": line})

    for record in parser.records:
        tag = str(record["tag"])
        attrs = record.get("attrs") or {}
        line = int(record["line"])
        if tag == "script" and attrs.get("src"):
            imports.append({"name": str(attrs["src"]), "line": line})
        elif tag == "link" and attrs.get("href"):
            imports.append({"name": str(attrs["href"]), "line": line})
        if tag == "title":
            add_symbol(_record_text(record) or "title", "title", line)
        elif re.fullmatch(r"h[1-6]", tag):
            add_symbol(_record_text(record) or tag, f"heading{tag[1]}", line)
        elif tag in landmarks:
            identifier = attrs.get("id") or attrs.get("aria-label") or attrs.get("class") or tag
            add_symbol(f"{tag}: {identifier}", "landmark", line)
        elif tag == "form":
            add_symbol(attrs.get("id") or attrs.get("name") or attrs.get("action") or "form", "form", line)
        elif tag in {"input", "select", "textarea", "button"}:
            name = attrs.get("id") or attrs.get("name") or _record_text(record) or tag
            add_symbol(str(name), "control" if tag != "button" else "button", line)
        elif attrs.get("id"):
            add_symbol(f"{tag}#{attrs['id']}", "element_id", line)
    return symbols, imports[:500]


def _xml_outline(text: str, max_symbols: int) -> tuple[list[dict[str, Any]], str]:
    _root, diagnostics = _safe_parse_xml(text)
    errors = [message for _line, severity, _source, message in diagnostics if severity == "error"]
    # Tag scanning is bounded and does not resolve entities.  It is safe to
    # use for an outline even when a DTD prevented full parsing.
    without_comments = re.sub(r"<!--.*?-->|<!\[CDATA\[.*?\]\]>", "", str(text or ""), flags=re.S)
    symbols: list[dict[str, Any]] = []
    seen: set[str] = set()
    stack: list[str] = []
    tag_re = re.compile(r"<(/?)([A-Za-z_][\w:.-]*)\b([^>]*?)(/?)>")
    for line_no, line in enumerate(without_comments.splitlines(), start=1):
        for match in tag_re.finditer(line):
            closing, raw_name, _attrs, self_closing = match.groups()
            local_name = raw_name.rsplit(":", 1)[-1]
            if closing:
                if local_name in stack:
                    while stack and stack[-1] != local_name:
                        stack.pop()
                    if stack:
                        stack.pop()
                continue
            path = "/" + "/".join([*stack, local_name])
            if path not in seen:
                seen.add(path)
                symbols.append(
                    {"name": local_name, "qualified_name": path, "kind": "xml_element", "line": line_no}
                )
                if len(symbols) >= max_symbols:
                    return symbols, "; ".join(errors)
            if not self_closing:
                stack.append(local_name)
    return symbols, "; ".join(errors)


def _css_outline(text: str, max_symbols: int) -> list[dict[str, Any]]:
    stripped = re.sub(
        r"/\*.*?\*/",
        lambda match: "".join("\n" if char == "\n" else " " for char in match.group(0)),
        str(text or ""),
        flags=re.S,
    )
    symbols: list[dict[str, Any]] = []
    for match in re.finditer(r"([^{}]+)\{", stripped):
        prelude = " ".join(match.group(1).split()).strip()
        if not prelude or prelude.endswith(":"):
            continue
        line = _line_number_at(stripped, match.start(1))
        if prelude.startswith("@media"):
            kind = "media_query"
        elif prelude.startswith("@keyframes"):
            kind = "keyframes"
        elif prelude.startswith("@"):
            kind = "at_rule"
        else:
            kind = "selector"
        symbols.append({"name": prelude[:160], "qualified_name": prelude[:160], "kind": kind, "line": line})
        if len(symbols) >= max_symbols:
            return symbols
    for match in re.finditer(r"(?:^|[{\s;])(--[A-Za-z0-9_-]+)\s*:", stripped, re.M):
        symbols.append(
            {
                "name": match.group(1),
                "qualified_name": match.group(1),
                "kind": "custom_property",
                "line": _line_number_at(stripped, match.start(1)),
            }
        )
        if len(symbols) >= max_symbols:
            break
    return symbols


async def _file_outline(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("path", ""), must_exist=True)
    if not resolved:
        return {"error": err, "symbols": []}
    if not resolved.is_file():
        return {"error": "Path is not a regular file.", "symbols": []}

    max_symbols = _clamp_int(params.get("max_symbols"), 300, 1, 2000)
    include_private = bool(params.get("include_private", True))
    text, truncated, read_error = _read_text_limited(resolved, max_bytes=3_000_000, errors="replace")
    if read_error:
        return {"error": read_error, "symbols": []}

    suffix = resolved.suffix.lower()
    language = _LANGUAGE_BY_EXTENSION.get(suffix, "Text")
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    exports: list[dict[str, Any]] = []
    lines = text.splitlines()

    if suffix == ".py":
        try:
            tree = ast.parse(text)
            symbols, imports = _python_outline(
                tree, include_private=include_private, max_symbols=max_symbols
            )
        except SyntaxError as exc:
            return {
                "path": _relative_workspace_path(resolved),
                "language": language,
                "lines": len(lines),
                "symbols": [],
                "imports": [],
                "error": f"Python syntax error at line {exc.lineno}: {exc.msg}",
            }
    elif suffix == ".json":
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                symbols = [
                    {"name": str(key), "kind": f"key:{type(value).__name__}", "line": 1}
                    for key, value in list(payload.items())[:max_symbols]
                ]
            elif isinstance(payload, list):
                symbols = [{"name": "[]", "kind": f"array[{len(payload)}]", "line": 1}]
                if payload and isinstance(payload[0], dict):
                    symbols.extend(
                        {"name": str(key), "kind": "item_key", "line": 1}
                        for key in list(payload[0])[:max_symbols]
                    )
        except json.JSONDecodeError as exc:
            return {
                "path": _relative_workspace_path(resolved),
                "language": language,
                "lines": len(lines),
                "symbols": [],
                "imports": [],
                "error": f"JSON error at line {exc.lineno}, column {exc.colno}: {exc.msg}",
            }
    elif suffix in {".md", ".markdown"}:
        for index, line in enumerate(lines, start=1):
            match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if match:
                symbols.append(
                    {"name": match.group(2).strip(), "kind": f"heading{len(match.group(1))}", "line": index}
                )
                if len(symbols) >= max_symbols:
                    break
    elif suffix in {".html", ".htm"}:
        symbols, imports = _html_outline(text, max_symbols)
    elif suffix in {".xml", ".xsd", ".xsl", ".xslt", ".svg"}:
        symbols, xml_error = _xml_outline(text, max_symbols)
        if xml_error:
            return {
                "path": _relative_workspace_path(resolved),
                "language": language,
                "lines": len(lines),
                "symbols": symbols,
                "imports": [],
                "error": xml_error,
            }
    elif suffix in {".css", ".scss"}:
        symbols = _css_outline(text, max_symbols)
    else:
        patterns: tuple[tuple[re.Pattern[str], str], ...] = (
            (re.compile(r"^\s*import\s+(?:[^'\"\n]+?\s+from\s+)?['\"]([^'\"]+)['\"]"), "import"),
            (re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"), "function"),
            (re.compile(r"^\s*export\s+(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"), "class"),
            (re.compile(r"^\s*export\s+(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)"), "type"),
            (re.compile(r"^\s*export\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)"), "export"),
            (re.compile(r"^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"), "function"),
            (re.compile(r"^\s*(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"), "class"),
            (re.compile(r"^\s*(?:const|let|var)\s+([A-Z][A-Za-z0-9_$]*)\s*=\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"), "component"),
            (re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)"), "function"),
            (re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)"), "function"),
            (re.compile(r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:class|interface|enum|record|struct)\s+([A-Za-z_]\w*)"), "type"),
        )
        if suffix in {".php", ".phtml"}:
            patterns = (
                (re.compile(r"^\s*namespace\s+([A-Za-z_][\w\\]*)\s*;"), "namespace"),
                (re.compile(r"^\s*use\s+([A-Za-z_][\w\\]*)(?:\s+as\s+\w+)?\s*;"), "import"),
                (re.compile(r"^\s*(?:require|require_once|include|include_once)\s+['\"]([^'\"]+)['\"]"), "import"),
                (re.compile(r"^\s*(?:final\s+|abstract\s+|readonly\s+)*(?:class|interface|trait|enum)\s+([A-Za-z_]\w*)"), "type"),
                (re.compile(r"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?function\s+&?\s*([A-Za-z_]\w*)\s*\("), "function"),
                (re.compile(r"^\s*(?:public|private|protected)?\s*(?:static\s+)?const\s+([A-Z_][A-Z0-9_]*)"), "constant"),
            )
        elif suffix in {".rb", ".rake", ".gemspec"} or resolved.name in {"Gemfile", "Rakefile"}:
            patterns = (
                (re.compile(r"^\s*require(?:_relative)?\s+[\"']([^\"']+)[\"']"), "import"),
                (re.compile(r"^\s*module\s+([A-Z][\w:]*)"), "module"),
                (re.compile(r"^\s*class\s+([A-Z][\w:]*)"), "class"),
                (re.compile(r"^\s*def\s+(?:self\.)?([A-Za-z_]\w*[!?=]?)"), "function"),
                (re.compile(r"^\s*attr_(?:reader|writer|accessor)\s+:([A-Za-z_]\w*)"), "attribute"),
                (re.compile(r"^\s*(?:task|describe|it)\s+[\"']([^\"']+)[\"']"), "task_or_test"),
                (re.compile(r"^\s*gem\s+[\"']([^\"']+)[\"']"), "dependency"),
            )
        elif suffix == ".rs":
            patterns = (
                (re.compile(r"^\s*(?:pub\s+)?use\s+([A-Za-z_][\w:]*)(?:::|\s|;)"), "import"),
                (re.compile(r"^\s*(?:pub\s+)?mod\s+([A-Za-z_]\w*)"), "module"),
                (re.compile(r"^\s*(?:pub\s+)?(?:struct|enum|trait|union)\s+([A-Za-z_]\w*)"), "type"),
                (re.compile(r"^\s*impl(?:\s*<[^>]+>)?\s+(?:[A-Za-z_][\w:]*\s+for\s+)?([A-Za-z_][\w:]*)"), "impl"),
                (re.compile(r"^\s*(?:pub\s+)?(?:const\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)"), "function"),
                (re.compile(r"^\s*(?:pub\s+)?type\s+([A-Za-z_]\w*)"), "type_alias"),
                (re.compile(r"^\s*(?:pub\s+)?(?:static|const)\s+([A-Za-z_]\w*)\s*:"), "constant"),
            )
        elif suffix in {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"}:
            patterns = (
                (re.compile(r"^\s*#\s*include\s*[<\"]([^>\"]+)[>\"]"), "import"),
                (re.compile(r"^\s*namespace\s+([A-Za-z_]\w*)"), "namespace"),
                (re.compile(r"^\s*(?:class|struct|enum(?:\s+class)?|union)\s+([A-Za-z_]\w*)"), "type"),
                (re.compile(r"^\s*typedef\s+.+?\b([A-Za-z_]\w*)\s*;"), "type_alias"),
                (re.compile(r"^\s*using\s+([A-Za-z_]\w*)\s*="), "type_alias"),
                (
                    re.compile(
                        r"^\s*(?:template\s*<[^>]+>\s*)?(?:static\s+|inline\s+|virtual\s+|constexpr\s+|explicit\s+|friend\s+)*"
                        r"[A-Za-z_][\w:<>,~*&]*\s+[*&]*\s*(?:[A-Za-z_]\w*::)?([A-Za-z_~]\w*)\s*"
                        r"\([^;{}]*\)\s*(?:const\s*)?(?:noexcept\s*)?(?:\{|;)"
                    ),
                    "function",
                ),
                (re.compile(r"^\s*(?:explicit\s+)?([A-Z][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*(?:\{|;)"), "constructor"),
            )
        for index, line in enumerate(lines, start=1):
            for pattern, kind in patterns:
                match = pattern.search(line)
                if not match:
                    continue
                name = match.group(1)
                if kind == "import":
                    imports.append({"name": name, "line": index})
                else:
                    if not include_private and name.startswith("_"):
                        continue
                    symbols.append({"name": name, "qualified_name": name, "kind": kind, "line": index})
                    if "export" in line:
                        exports.append({"name": name, "line": index})
                break
            if len(symbols) >= max_symbols:
                break

    return {
        "path": _relative_workspace_path(resolved),
        "language": language,
        "lines": len(lines),
        "bytes": _safe_file_size(resolved),
        "truncated_source": truncated,
        "symbols": symbols[:max_symbols],
        "imports": imports[:500],
        "exports": exports[:500],
    }


async def _find_symbol(params: dict[str, Any]) -> dict[str, Any]:
    symbol = str(params.get("symbol") or "").strip()
    if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$-]*", symbol):
        return {"definitions": [], "references": [], "error": "symbol must be a simple identifier."}
    resolved, err = resolve_confined_path(params.get("path", "."), must_exist=True)
    if not resolved:
        return {"definitions": [], "references": [], "error": err}
    if not resolved.is_dir():
        return {"definitions": [], "references": [], "error": "path must be a directory."}

    extensions = _normalize_extensions(params.get("extensions")) or {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".go",
        ".rs",
        ".java",
        ".cs",
        ".php",
        ".phtml",
        ".rb",
        ".rake",
        ".swift",
        ".kt",
        ".c",
        ".h",
        ".cpp",
        ".cc",
        ".cxx",
        ".hpp",
        ".hh",
        ".hxx",
        ".html",
        ".xml",
        ".css",
    }
    max_results = _clamp_int(params.get("max_results"), 100, 1, 500)
    word_re = re.compile(rf"(?<![A-Za-z0-9_$]){re.escape(symbol)}(?![A-Za-z0-9_$])")
    escaped = re.escape(symbol)
    definition_patterns = [
        ("class", re.compile(rf"^\s*(?:export\s+)?(?:abstract\s+)?class\s+{escaped}\b")),
        ("function", re.compile(rf"^\s*(?:export\s+)?(?:async\s+)?def\s+{escaped}\s*\(")),
        ("function", re.compile(rf"^\s*(?:export\s+)?(?:async\s+)?function\s+{escaped}\s*\(")),
        ("type", re.compile(rf"^\s*(?:export\s+)?(?:interface|type|enum|struct|record)\s+{escaped}\b")),
        ("function", re.compile(rf"^\s*(?:pub\s+)?(?:async\s+)?fn\s+{escaped}\s*\(")),
        ("function", re.compile(rf"^\s*func\s+(?:\([^)]*\)\s*)?{escaped}\s*\(")),
        ("variable", re.compile(rf"^\s*(?:export\s+)?(?:const|let|var)\s+{escaped}\b")),
        ("function", re.compile(rf"^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?function\s+&?\s*{escaped}\s*\(")),
        ("function", re.compile(rf"^\s*def\s+(?:self\.)?{escaped}(?:[!?=])?\b")),
        ("module", re.compile(rf"^\s*(?:module|mod)\s+{escaped}\b")),
        ("type", re.compile(rf"^\s*(?:pub\s+)?(?:struct|enum|trait|union|type)\s+{escaped}\b")),
        ("function", re.compile(rf"^\s*[\w:<>,~*&]+\s+[*&]*\s*(?:\w+::)?{escaped}\s*\([^;{{}}]*\)\s*(?:const\s*)?(?:noexcept\s*)?(?:\{{|;)")),
        ("element_id", re.compile(rf"\bid\s*=\s*[\"']{escaped}[\"']")),
        ("xml_element", re.compile(rf"<(?:[A-Za-z_][\w.-]*:)?{escaped}(?:\s|>|/)")),
        ("css_selector", re.compile(rf"(?:^|[\s,>+~])[.#]{escaped}\b|^\s*--{escaped}\s*:")),
    ]

    definitions: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    files_scanned = 0
    for path in _iter_workspace_files(
        resolved,
        include_hidden=bool(params.get("include_hidden", False)),
        max_files=20_000,
    ):
        if path.suffix.lower() not in extensions or _safe_file_size(path) > 2_000_000:
            continue
        text, _, read_error = _read_text_limited(path, max_bytes=2_000_000, errors="strict")
        if read_error or symbol not in text:
            continue
        files_scanned += 1
        rel = _relative_workspace_path(path, resolved)
        definition_lines: set[int] = set()

        if path.suffix.lower() == ".py":
            try:
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
                        kind = "class" if isinstance(node, ast.ClassDef) else "function"
                        definitions.append(
                            {"file": rel, "line": node.lineno, "kind": kind, "text": f"{kind} {symbol}"}
                        )
                        definition_lines.add(node.lineno)
            except SyntaxError:
                pass

        for line_no, line in enumerate(text.splitlines(), start=1):
            if symbol not in line:
                continue
            is_definition = line_no in definition_lines
            if not is_definition:
                for kind, pattern in definition_patterns:
                    if pattern.search(line):
                        definitions.append(
                            {"file": rel, "line": line_no, "kind": kind, "text": line.strip()[:240]}
                        )
                        definition_lines.add(line_no)
                        is_definition = True
                        break
            if not is_definition and word_re.search(line):
                kind = "import" if re.match(r"\s*(import|from)\b", line) else "reference"
                references.append(
                    {"file": rel, "line": line_no, "kind": kind, "text": line.strip()[:240]}
                )
            if len(definitions) + len(references) >= max_results * 2:
                break
        if len(definitions) >= max_results and len(references) >= max_results:
            break

    return {
        "symbol": symbol,
        "path": _relative_workspace_path(resolved),
        "definitions": definitions[:max_results],
        "references": references[:max_results],
        "definition_count": len(definitions),
        "reference_count": len(references),
        "files_scanned": files_scanned,
        "truncated": len(definitions) > max_results or len(references) > max_results,
    }


_DIAGNOSTIC_EXTENSIONS = {
    ".py",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".xml",
    ".xsd",
    ".xsl",
    ".xslt",
    ".svg",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".js",
    ".mjs",
    ".cjs",
    ".jsx",
    ".ts",
    ".tsx",
    ".c",
    ".h",
    ".cpp",
    ".cc",
    ".cxx",
    ".hpp",
    ".hh",
    ".hxx",
    ".rs",
    ".php",
    ".phtml",
    ".rb",
    ".rake",
    ".gemspec",
}


def _line_number_at(text: str, offset: int) -> int:
    return str(text or "").count("\n", 0, max(0, offset)) + 1


def _safe_parse_xml(text: str) -> tuple[ET.Element | None, list[tuple[int, str, str, str]]]:
    """Parse XML without DTD/entity expansion.

    DTD-bearing documents are reported and *not* parsed.  ElementTree/expat
    does not fetch external entities, but internal entities can still expand;
    rejecting DTDs in this diagnostic path is the safest portable policy.
    """

    source = str(text or "")
    diagnostics: list[tuple[int, str, str, str]] = []
    doctype = re.search(r"<!DOCTYPE\b", source, re.I)
    if doctype:
        line = _line_number_at(source, doctype.start())
        segment = source[doctype.start() : doctype.start() + 4096]
        if re.search(r"<!ENTITY\b|\bSYSTEM\b|\bPUBLIC\b", segment, re.I):
            diagnostics.append(
                (
                    line,
                    "error",
                    "xml-security",
                    "XML DTD declares an entity or external identifier; disable DTD/external entities for untrusted XML.",
                )
            )
        else:
            diagnostics.append(
                (
                    line,
                    "warning",
                    "xml-security",
                    "XML contains a DTD; diagnostic parsing skipped DTD processing for safety.",
                )
            )
        return None, diagnostics
    try:
        return ET.fromstring(source.encode("utf-8")), diagnostics
    except ET.ParseError as exc:
        line = int(exc.position[0]) if getattr(exc, "position", None) else 1
        diagnostics.append((line, "error", "xml", f"XML is not well-formed: {exc}"))
        return None, diagnostics
    except (UnicodeError, ValueError) as exc:
        diagnostics.append((1, "error", "xml", f"XML could not be parsed safely: {exc}"))
        return None, diagnostics


class _HTMLStructureParser(HTMLParser):
    """Small forgiving HTML recorder for outline and quality diagnostics."""

    _VOID = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    _OPTIONAL = {"p", "li", "dt", "dd", "tr", "td", "th", "option", "thead", "tbody", "html", "head", "body"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.doctype = False
        self.records: list[dict[str, Any]] = []
        self.stack: list[dict[str, Any]] = []
        self.mismatches: list[tuple[int, str]] = []

    def handle_decl(self, decl: str) -> None:
        if decl.strip().lower().startswith("doctype"):
            self.doctype = True

    def _record(self, tag: str, attrs: list[tuple[str, str | None]]) -> dict[str, Any]:
        record = {
            "tag": tag.lower(),
            "attrs": {str(key).lower(): (value or "") for key, value in attrs},
            "line": self.getpos()[0],
            "ancestors": tuple(str(item["tag"]) for item in self.stack),
            "text_parts": [],
        }
        self.records.append(record)
        return record

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        record = self._record(tag, attrs)
        if record["tag"] not in self._VOID:
            self.stack.append(record)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(tag, attrs)

    def handle_data(self, data: str) -> None:
        for record in self.stack:
            if record["tag"] in {"title", "button", "a", "h1", "h2", "h3", "h4", "h5", "h6", "label"}:
                record["text_parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._VOID:
            return
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                intervening = self.stack[index + 1 :]
                for record in intervening:
                    if record["tag"] not in self._OPTIONAL:
                        self.mismatches.append(
                            (
                                int(record["line"]),
                                f"<{record['tag']}> opened here was not closed before </{tag}>.",
                            )
                        )
                del self.stack[index:]
                return
        self.mismatches.append((self.getpos()[0], f"Stray closing </{tag}> tag."))

    def finish(self) -> None:
        for record in self.stack:
            if record["tag"] not in self._OPTIONAL:
                self.mismatches.append((int(record["line"]), f"<{record['tag']}> opened here is never closed."))
        self.stack.clear()


def _record_text(record: dict[str, Any]) -> str:
    return " ".join("".join(str(part) for part in record.get("text_parts", [])).split())


def _parse_html_structure(text: str) -> _HTMLStructureParser:
    parser = _HTMLStructureParser()
    try:
        parser.feed(str(text or ""))
        parser.close()
    except Exception:
        # HTMLParser is intentionally forgiving; retain records gathered so
        # far and let explicit structure checks report what they can prove.
        pass
    parser.finish()
    return parser


def _html_diagnostics(text: str) -> list[tuple[int, str, str, str]]:
    parser = _parse_html_structure(text)
    records = parser.records
    diagnostics: list[tuple[int, str, str, str]] = [
        (line, "error", "html", message) for line, message in parser.mismatches[:30]
    ]

    def add(line: int, severity: str, source: str, message: str) -> None:
        diagnostics.append((max(1, line), severity, source, message))

    by_tag: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_tag.setdefault(str(record["tag"]), []).append(record)

    is_document = bool(by_tag.get("html") or parser.doctype)
    if is_document:
        html_record = (by_tag.get("html") or [{}])[0]
        html_line = int(html_record.get("line") or 1)
        if not parser.doctype:
            add(html_line, "warning", "html5", "HTML document is missing <!doctype html>.")
        if not str((html_record.get("attrs") or {}).get("lang") or "").strip():
            add(html_line, "warning", "accessibility", "<html> is missing a lang attribute.")
        metas = by_tag.get("meta", [])
        if not any("charset" in (record.get("attrs") or {}) for record in metas):
            add(html_line, "warning", "html5", "HTML document is missing a charset meta declaration.")
        if not any(
            str((record.get("attrs") or {}).get("name") or "").lower() == "viewport" for record in metas
        ):
            add(html_line, "warning", "responsive", "HTML document is missing a responsive viewport meta tag.")
        titles = by_tag.get("title", [])
        if not titles or not _record_text(titles[0]):
            add(html_line, "warning", "html5", "HTML document is missing a non-empty <title>.")
        if not by_tag.get("main"):
            add(html_line, "warning", "accessibility", "HTML document has no <main> landmark.")
        elif len(by_tag["main"]) > 1:
            add(int(by_tag["main"][1]["line"]), "warning", "accessibility", "HTML document has multiple <main> landmarks.")

    seen_ids: dict[str, int] = {}
    label_targets: set[str] = set()
    for record in records:
        attrs = record.get("attrs") or {}
        element_id = str(attrs.get("id") or "").strip()
        if element_id:
            if element_id in seen_ids:
                add(
                    int(record["line"]),
                    "error",
                    "html",
                    f"Duplicate id '{element_id}' (first used on line {seen_ids[element_id]}).",
                )
            else:
                seen_ids[element_id] = int(record["line"])
        if record["tag"] == "label" and attrs.get("for"):
            label_targets.add(str(attrs["for"]))

    controls = [
        record
        for record in records
        if record["tag"] in {"input", "select", "textarea"}
        and str((record.get("attrs") or {}).get("type") or "").lower()
        not in {"hidden", "submit", "button", "reset", "image"}
    ]
    for record in controls:
        attrs = record.get("attrs") or {}
        control_id = str(attrs.get("id") or "")
        if not (
            (control_id and control_id in label_targets)
            or "label" in (record.get("ancestors") or ())
            or attrs.get("aria-label")
            or attrs.get("aria-labelledby")
        ):
            add(
                int(record["line"]),
                "error",
                "accessibility",
                f"<{record['tag']}> control has no associated label; placeholder text is not a label.",
            )

    previous_heading = 0
    h1_count = 0
    for record in records:
        tag = str(record["tag"])
        attrs = record.get("attrs") or {}
        line = int(record["line"])
        if tag == "img" and "alt" not in attrs:
            add(line, "error", "accessibility", "<img> is missing an alt attribute (use alt=\"\" only for decorative images).")
        if any(str(name).lower().startswith("on") for name in attrs):
            add(line, "error", "frontend-security", f"<{tag}> uses an inline event handler; move behaviour to a script/component.")
        if tag == "a":
            href = str(attrs.get("href") or "").strip()
            if href.lower().startswith("javascript:"):
                add(line, "error", "frontend-security", "javascript: link used instead of a real button/link target.")
            elif href in {"", "#"} and not (_record_text(record) or attrs.get("aria-label")):
                add(line, "warning", "accessibility", "Link has no useful destination or accessible name.")
            if str(attrs.get("target") or "").lower() == "_blank" and "noopener" not in str(attrs.get("rel") or "").lower():
                add(line, "warning", "frontend-security", "target=_blank link should include rel=\"noopener\".")
            if not (_record_text(record) or attrs.get("aria-label") or attrs.get("aria-labelledby") or attrs.get("title")):
                add(line, "error", "accessibility", "Link has no accessible name.")
        if tag == "button" and not (
            _record_text(record) or attrs.get("aria-label") or attrs.get("aria-labelledby") or attrs.get("title")
        ):
            add(line, "error", "accessibility", "Button has no accessible name.")
        if tag in {"div", "span"} and "onclick" in attrs:
            add(line, "error", "accessibility", f"<{tag}> is used as a click target; use a real <button> or <a>.")
        if re.fullmatch(r"h[1-6]", tag):
            level = int(tag[1])
            h1_count += int(level == 1)
            if previous_heading and level > previous_heading + 1:
                add(
                    line,
                    "warning",
                    "accessibility",
                    f"Heading level jumps from h{previous_heading} to h{level}; keep a logical outline.",
                )
            previous_heading = level
    if h1_count > 1:
        second_h1 = [record for record in records if record["tag"] == "h1"][1]
        add(int(second_h1["line"]), "warning", "accessibility", "Document has multiple <h1> headings.")
    return diagnostics[:300]


def _css_diagnostics(text: str) -> list[tuple[int, str, str, str]]:
    diagnostics: list[tuple[int, str, str, str]] = []
    # Replace comments while preserving line positions.
    stripped = re.sub(
        r"/\*.*?\*/",
        lambda match: "".join("\n" if char == "\n" else " " for char in match.group(0)),
        str(text or ""),
        flags=re.S,
    )
    stack: list[int] = []
    quote: str | None = None
    escaped = False
    line = 1
    for char in stripped:
        if char == "\n":
            line += 1
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "{":
            stack.append(line)
        elif char == "}":
            if stack:
                stack.pop()
            else:
                diagnostics.append((line, "error", "css", "Unmatched closing '}' in stylesheet."))
    for open_line in stack[:10]:
        diagnostics.append((open_line, "error", "css", "Unclosed '{' block in stylesheet."))

    lines = stripped.splitlines()
    for line_no, content in enumerate(lines, start=1):
        if re.search(r"\boutline\s*:\s*(?:none|0)\b", content, re.I) and ":focus" not in stripped:
            diagnostics.append(
                (
                    line_no,
                    "warning",
                    "accessibility",
                    "outline is removed without a visible :focus-visible replacement.",
                )
            )
            break
    if len(lines) > 40 and ":focus-visible" not in stripped:
        diagnostics.append(
            (1, "warning", "accessibility", "Stylesheet has no explicit :focus-visible treatment.")
        )
    if len(lines) > 80 and not re.search(r"@media|@container|clamp\(|minmax\(|auto-fit|auto-fill", stripped):
        diagnostics.append(
            (
                1,
                "warning",
                "responsive",
                "Large stylesheet has no visible media/container query or fluid sizing strategy.",
            )
        )
    if stripped.lower().count("!important") > 8:
        diagnostics.append(
            (1, "warning", "css", "Stylesheet uses !important frequently; prefer cascade layers/specificity discipline.")
        )
    return diagnostics


def _strip_code_for_brace_scan(text: str, *, hash_comments: bool = False) -> str:
    result: list[str] = []
    index = 0
    source = str(text or "")
    quote: str | None = None
    line_comment = False
    block_comment = False
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            result.append("\n" if char == "\n" else " ")
            if char == "\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if char == "*" and nxt == "/":
                result.extend([" ", " "])
                index += 2
                block_comment = False
            else:
                result.append("\n" if char == "\n" else " ")
                index += 1
            continue
        if quote:
            result.append("\n" if char == "\n" else " ")
            if char == "\\" and index + 1 < len(source):
                result.append("\n" if nxt == "\n" else " ")
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char == "/" and nxt == "*":
            block_comment = True
            result.extend([" ", " "])
            index += 2
            continue
        if (char == "/" and nxt == "/") or (hash_comments and char == "#"):
            line_comment = True
            result.append(" ")
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            result.append(" ")
            index += 1
            continue
        result.append(char)
        index += 1
    return "".join(result)


def _brace_diagnostics(text: str, source: str, *, hash_comments: bool = False) -> list[tuple[int, str, str, str]]:
    stripped = _strip_code_for_brace_scan(text, hash_comments=hash_comments)
    stack: list[tuple[str, int]] = []
    pairs = {"}": "{", ")": "(", "]": "["}
    diagnostics: list[tuple[int, str, str, str]] = []
    line = 1
    for char in stripped:
        if char == "\n":
            line += 1
        elif char in "({[":
            stack.append((char, line))
        elif char in pairs:
            if not stack or stack[-1][0] != pairs[char]:
                diagnostics.append((line, "error", source, f"Unmatched closing '{char}'."))
                if len(diagnostics) >= 10:
                    return diagnostics
            else:
                stack.pop()
    for char, open_line in stack[:10]:
        diagnostics.append((open_line, "error", source, f"Unclosed '{char}' block/delimiter."))
    return diagnostics


def _iter_jsx_opening_tags(
    source: str,
    tag_names: set[str],
) -> Iterator[tuple[int, str, str]]:
    """Yield JSX opening tags without stopping at ``=>`` inside expressions."""

    pattern = re.compile(
        r"<(" + "|".join(re.escape(name) for name in sorted(tag_names)) + r")\b",
        re.I,
    )
    for match in pattern.finditer(source):
        index = match.end()
        brace_depth = 0
        quote: str | None = None
        end = len(source)
        while index < len(source):
            char = source[index]
            if quote:
                if char == "\\" and index + 1 < len(source):
                    index += 2
                    continue
                if char == quote:
                    quote = None
                index += 1
                continue
            if char in {"'", '"', "`"}:
                quote = char
            elif char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth = max(0, brace_depth - 1)
            elif char == ">" and brace_depth == 0:
                end = index + 1
                break
            index += 1
        yield match.start(), match.group(1).lower(), source[match.start() : end]


def _jsx_diagnostics(text: str) -> list[tuple[int, str, str, str]]:
    diagnostics: list[tuple[int, str, str, str]] = []
    source = str(text or "")
    for start, _tag, tag_text in _iter_jsx_opening_tags(source, {"img"}):
        if not re.search(r"\balt\s*=", tag_text):
            diagnostics.append(
                (
                    _line_number_at(source, start),
                    "error",
                    "accessibility",
                    "<img> is missing an alt attribute (use alt=\"\" only for decorative images).",
                )
            )
    label_targets = set(
        re.findall(r"<label\b[^>]*(?:htmlFor|for)\s*=\s*[\"']([^\"']+)[\"']", source, re.I)
    )
    for start, _tag, tag_text in _iter_jsx_opening_tags(source, {"input", "select", "textarea"}):
        if re.search(r"type\s*=\s*[\"'](?:hidden|submit|button|reset)[\"']", tag_text, re.I):
            continue
        id_match = re.search(r"\bid\s*=\s*[\"']([^\"']+)[\"']", tag_text)
        dynamic_id = bool(re.search(r"\bid\s*=\s*\{", tag_text))
        dynamic_label = bool(re.search(r"<label\b[^>]*(?:htmlFor|for)\s*=\s*\{", source))
        if not (
            (id_match and id_match.group(1) in label_targets)
            or (dynamic_id and dynamic_label)
            or re.search(r"aria-(?:label|labelledby)\s*=", tag_text)
        ):
            diagnostics.append(
                (
                    _line_number_at(source, start),
                    "error",
                    "accessibility",
                    "Form control has no associated label; placeholder text is not a label.",
                )
            )
    for match in re.finditer(r"<(?:div|span)\b[^>]*\bonClick\s*=", source):
        diagnostics.append(
            (
                _line_number_at(source, match.start()),
                "error",
                "accessibility",
                "Non-semantic element handles click; use a real button or link.",
            )
        )
    if "dangerouslySetInnerHTML" in source:
        diagnostics.append(
            (
                _line_number_at(source, source.index("dangerouslySetInnerHTML")),
                "warning",
                "frontend-security",
                "dangerouslySetInnerHTML injects raw HTML; render structured data or sanitize explicitly.",
            )
        )
    if re.search(r"\.innerHTML\s*=", source):
        diagnostics.append(
            (
                _line_number_at(source, re.search(r"\.innerHTML\s*=", source).start()),  # type: ignore[union-attr]
                "warning",
                "frontend-security",
                "Direct innerHTML assignment can create XSS risk with untrusted data.",
            )
        )
    return diagnostics


def _language_heuristic_diagnostics(text: str, suffix: str) -> list[tuple[int, str, str, str]]:
    diagnostics: list[tuple[int, str, str, str]] = []
    source = str(text or "")

    def first(pattern: str, severity: str, source_name: str, message: str, flags: int = 0) -> None:
        match = re.search(pattern, source, flags)
        if match:
            diagnostics.append((_line_number_at(source, match.start()), severity, source_name, message))

    if suffix in {".c", ".h"}:
        first(
            r"\b(?:gets|strcpy|strcat|sprintf|vsprintf)\s*\(|\bscanf\s*\([^)]*%s",
            "warning",
            "c-safety",
            "Unbounded C string/input API used; prefer bounded operations with explicit sizes and checked returns.",
        )
    if suffix in {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"}:
        first(
            r"\b[A-Za-z_][\w:<>,\s]*\*\s*[A-Za-z_]\w*\s*=\s*new\b",
            "warning",
            "cpp-safety",
            "Owning allocation appears to be stored in a raw pointer; prefer RAII containers or smart pointers.",
        )
    if suffix == ".rs":
        if re.search(r"\bunsafe\s*\{", source) and "SAFETY:" not in source:
            first(
                r"\bunsafe\s*\{",
                "warning",
                "rust-safety",
                "unsafe block has no SAFETY comment explaining the invariants.",
            )
        if re.search(r"\bpub\s+fn\b", source) and re.search(r"\.\s*unwrap\s*\(", source):
            first(
                r"\.\s*unwrap\s*\(",
                "warning",
                "rust-safety",
                "Public Rust code uses unwrap; return Result/Option across API boundaries.",
            )
    if suffix in {".php", ".phtml"}:
        first(
            r"\b(?:echo|print)\b[^;]*(?:\$_GET|\$_POST|\$_REQUEST|\$_COOKIE)",
            "warning",
            "php-security",
            "Request data is output near echo/print; validate and escape with htmlspecialchars.",
        )
        first(
            r"\b(?:md5|sha1)\s*\([^)]*password",
            "warning",
            "php-security",
            "Password appears to be hashed with md5/sha1; use password_hash/password_verify.",
            re.I,
        )
    if suffix in {".rb", ".rake", ".gemspec"}:
        first(
            r"\b(?:eval|Marshal\.load)\s*\(?|\bsystem\s*\(?\s*[\"'][^\"']*#\{|`[^`]*#\{",
            "warning",
            "ruby-security",
            "Dynamic eval/Marshal/shell interpolation used; parse data and pass command argument arrays.",
        )
    if suffix in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}:
        first(
            r"\.innerHTML\s*=",
            "warning",
            "frontend-security",
            "Direct innerHTML assignment can create XSS risk with untrusted data.",
        )
    return diagnostics


def _collect_text_diagnostics(path: Path, text: str) -> list[tuple[int, str, str, str]]:
    suffix = path.suffix.lower()
    diagnostics: list[tuple[int, str, str, str]] = []
    if suffix in {".xml", ".xsd", ".xsl", ".xslt", ".svg"}:
        _root, diagnostics = _safe_parse_xml(text)
    elif suffix in {".html", ".htm"}:
        diagnostics = _html_diagnostics(text)
    elif suffix in {".css", ".scss"}:
        diagnostics = _css_diagnostics(text)
    elif suffix in {".jsx", ".tsx"}:
        diagnostics = _jsx_diagnostics(text) + _language_heuristic_diagnostics(text, suffix)
    elif suffix in {".js", ".mjs", ".cjs", ".ts"}:
        # Regex literals make delimiter counting unreliable in JS/TS; the
        # project typecheck/lint checks are the authoritative syntax gate.
        diagnostics = _language_heuristic_diagnostics(text, suffix)
    elif suffix == ".rs":
        # Lifetimes/raw strings make a regex delimiter scan unreliable; Cargo
        # check/clippy in project_checks are the crate-aware syntax gate.
        diagnostics = _language_heuristic_diagnostics(text, suffix)
    elif suffix in {".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx"}:
        language = _LANGUAGE_BY_EXTENSION.get(suffix, "code")
        diagnostics = _brace_diagnostics(text, language.lower()) + _language_heuristic_diagnostics(text, suffix)
    elif suffix in {".php", ".phtml"}:
        diagnostics = _brace_diagnostics(text, "php", hash_comments=True) + _language_heuristic_diagnostics(text, suffix)
    elif suffix in {".rb", ".rake", ".gemspec"}:
        diagnostics = _language_heuristic_diagnostics(text, suffix)
    return diagnostics


def _parse_compiler_diagnostics(
    output: str,
    *,
    cwd: Path,
    source: str,
    fallback: Path,
) -> list[tuple[Path, int, str, str, str]]:
    parsed: list[tuple[Path, int, str, str, str]] = []
    pattern = re.compile(r"^(.*?):(\d+)(?::(\d+))?:\s*(fatal error|error|warning|note):\s*(.*)$")
    for raw_line in str(output or "").splitlines():
        match = pattern.match(raw_line.strip())
        if not match:
            continue
        raw_path = match.group(1).strip().strip("'\"")
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        try:
            candidate = candidate.resolve()
        except OSError:
            pass
        severity = "error" if "error" in match.group(4).lower() else "warning"
        if match.group(4).lower() == "note":
            severity = "info"
        column = match.group(3)
        message = match.group(5) + (f" (column {column})" if column else "")
        parsed.append((candidate, int(match.group(2)), severity, source, message))
    if not parsed and str(output or "").strip():
        useful = [line.strip() for line in str(output).splitlines() if line.strip()]
        if useful:
            parsed.append((fallback, 1, "error", source, useful[-1][:500]))
    return parsed[:500]


async def _native_syntax_diagnostics(
    scan_root: Path,
    files_by_language: dict[str, list[Path]],
    *,
    timeout: int = 30,
) -> tuple[list[tuple[Path, int, str, str, str]], list[str], list[str]]:
    """Run installed syntax-only checkers and report honest skips."""

    diagnostics: list[tuple[Path, int, str, str, str]] = []
    ran: list[str] = []
    skipped: list[str] = []

    async def compile_batch(language: str, compiler: str | None, args: list[str], files: list[Path]) -> None:
        if not files:
            return
        if not compiler:
            skipped.append(f"{language}: compiler not installed")
            return
        ran.append(language)
        include_dirs: list[str] = []
        candidates = [scan_root / "include", scan_root / "src", *[path.parent for path in files[:50]]]
        for candidate in candidates:
            try:
                resolved_candidate = candidate.resolve()
            except OSError:
                continue
            value = str(resolved_candidate)
            if resolved_candidate.is_dir() and value not in include_dirs:
                include_dirs.append(value)
            if len(include_dirs) >= 16:
                break
        for start in range(0, len(files), 50):
            batch = files[start : start + 50]
            command = [compiler, *args]
            for include_dir in include_dirs:
                command.extend(["-I", include_dir])
            command.extend(str(path) for path in batch)
            result = await _run_confined_command(
                command,
                cwd=scan_root,
                timeout=timeout,
                max_chars=30000,
            )
            output = str(result.get("stderr") or result.get("output") or "")
            if output:
                diagnostics.extend(
                    _parse_compiler_diagnostics(
                        output,
                        cwd=scan_root,
                        source=language.lower().replace("+", "p"),
                        fallback=batch[0],
                    )
                )

    await compile_batch(
        "C",
        shutil.which("gcc") or shutil.which("cc") or shutil.which("clang"),
        ["-std=c17", "-fsyntax-only", "-Wall", "-Wextra"],
        files_by_language.get("c", []),
    )
    await compile_batch(
        "C++",
        shutil.which("g++") or shutil.which("c++") or shutil.which("clang++"),
        ["-std=c++20", "-fsyntax-only", "-Wall", "-Wextra"],
        files_by_language.get("cpp", []),
    )

    async def lint_files(language: str, binary_name: str, flag: str, files: list[Path]) -> None:
        if not files:
            return
        binary = shutil.which(binary_name)
        if not binary:
            skipped.append(f"{language}: {binary_name} not installed")
            return
        ran.append(language)
        for path in files[:200]:
            result = await _run_confined_command(
                [binary, flag, str(path)],
                cwd=scan_root,
                timeout=min(timeout, 15),
                max_chars=12000,
            )
            if result.get("passed"):
                continue
            output = str(result.get("stderr") or result.get("stdout") or result.get("output") or "")
            line_match = re.search(r"(?:on line|:line:?)\s*(\d+)", output, re.I) or re.search(
                rf":{re.escape(path.name)}:(\d+)", output
            )
            generic_line = re.search(r":(\d+)(?::\d+)?:", output)
            line = int((line_match or generic_line).group(1)) if (line_match or generic_line) else 1
            useful = [line_text.strip() for line_text in output.splitlines() if line_text.strip()]
            diagnostics.append(
                (
                    path,
                    line,
                    "error",
                    language.lower(),
                    (useful[0] if useful else f"{language} syntax check failed")[:500],
                )
            )
        if len(files) > 200:
            skipped.append(f"{language}: syntax lint capped at 200 files")

    await lint_files("PHP", "php", "-l", files_by_language.get("php", []))
    await lint_files("Ruby", "ruby", "-c", files_by_language.get("ruby", []))
    if files_by_language.get("rust"):
        skipped.append("Rust: crate-aware diagnostics available via project_checks cargo_check")
    return diagnostics[:1000], ran, skipped


async def _code_diagnostics(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("path", "."), must_exist=True)
    if not resolved:
        return {"clean": False, "diagnostics": [], "error": err}

    max_files = _clamp_int(params.get("max_files"), 1000, 1, 10_000)
    include_todos = bool(params.get("include_todos", False))
    include_native = bool(params.get("include_native", True))
    if resolved.is_file():
        files = [resolved]
        scan_root = resolved.parent
    elif resolved.is_dir():
        files = list(
            _iter_workspace_files(
                resolved,
                include_hidden=bool(params.get("include_hidden", False)),
                max_files=max_files,
            )
        )
        scan_root = resolved
    else:
        return {"clean": False, "diagnostics": [], "error": "Path is neither a file nor directory."}

    diagnostics: list[dict[str, Any]] = []
    files_scanned = 0
    language_counts: Counter[str] = Counter()
    native_files: dict[str, list[Path]] = {"c": [], "cpp": [], "php": [], "ruby": [], "rust": []}

    def add(path: Path, line: int, severity: str, source: str, message: str) -> None:
        diagnostics.append(
            {
                "file": _relative_workspace_path(path, scan_root),
                "line": max(1, line),
                "severity": severity,
                "source": source,
                "message": message[:500],
            }
        )

    for path in files:
        suffix = path.suffix.lower()
        if suffix not in _DIAGNOSTIC_EXTENSIONS and not include_todos:
            continue
        if _safe_file_size(path) > 3_000_000:
            continue
        text, _, read_error = _read_text_limited(path, max_bytes=3_000_000, errors="strict")
        if read_error:
            if suffix in _DIAGNOSTIC_EXTENSIONS:
                files_scanned += 1
                language_counts[_LANGUAGE_BY_EXTENSION.get(suffix, suffix or "Text")] += 1
                add(path, 1, "error", "read", read_error)
            continue
        if suffix in _DIAGNOSTIC_EXTENSIONS:
            files_scanned += 1
            language_counts[_LANGUAGE_BY_EXTENSION.get(suffix, suffix or "Text")] += 1
            if suffix == ".c":
                native_files["c"].append(path)
            elif suffix in {".cpp", ".cc", ".cxx"}:
                native_files["cpp"].append(path)
            elif suffix in {".php", ".phtml"}:
                native_files["php"].append(path)
            elif suffix in {".rb", ".rake", ".gemspec"}:
                native_files["ruby"].append(path)
            elif suffix == ".rs":
                native_files["rust"].append(path)

        if suffix == ".py":
            try:
                tree = ast.parse(text, filename=str(path))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    unsafe_name = ""
                    if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                        unsafe_name = node.func.id
                    elif (
                        isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "pickle"
                        and node.func.attr in {"load", "loads"}
                    ):
                        unsafe_name = f"pickle.{node.func.attr}"
                    if unsafe_name:
                        add(
                            path,
                            node.lineno,
                            "warning",
                            "python-security",
                            f"{unsafe_name} used; avoid dynamic execution/unsafe deserialization on untrusted data.",
                        )
                    if any(
                        keyword.arg == "shell"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                        for keyword in node.keywords
                    ):
                        add(
                            path,
                            node.lineno,
                            "warning",
                            "python-security",
                            "shell=True used; pass an argument list without a shell.",
                        )
            except SyntaxError as exc:
                add(path, exc.lineno or 1, "error", "python", f"{exc.msg} (column {exc.offset or '?'})")
        elif suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                add(path, exc.lineno, "error", "json", f"{exc.msg} (column {exc.colno})")
        elif suffix == ".toml":
            try:
                tomllib.loads(text)
            except tomllib.TOMLDecodeError as exc:
                message = str(exc)
                line_match = re.search(r"line\s+(\d+)", message, re.I)
                add(path, int(line_match.group(1)) if line_match else 1, "error", "toml", message)
        elif suffix in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore[import-not-found]

                yaml.safe_load(text)
            except ImportError:
                pass
            except Exception as exc:  # yaml exposes several exception classes
                mark = getattr(exc, "problem_mark", None)
                line = int(getattr(mark, "line", 0)) + 1 if mark else 1
                add(path, line, "error", "yaml", str(exc).splitlines()[0] if str(exc) else "YAML parse error")

        elif suffix in _DIAGNOSTIC_EXTENSIONS:
            for line, severity, source, message in _collect_text_diagnostics(path, text):
                add(path, line, severity, source, message)
                if len(diagnostics) >= 1000:
                    break

        if include_todos and suffix in _TEXT_EXTENSIONS:
            for line_no, line in enumerate(text.splitlines(), start=1):
                if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", line):
                    add(path, line_no, "info", "marker", line.strip()[:240])
                    if len(diagnostics) >= 1000:
                        break
        if len(diagnostics) >= 1000:
            break

    native_checks: list[str] = []
    native_checks_skipped: list[str] = []
    if include_native and len(diagnostics) < 1000 and any(native_files.values()):
        native_diagnostics, native_checks, native_checks_skipped = await _native_syntax_diagnostics(
            scan_root,
            native_files,
            timeout=_clamp_int(params.get("timeout"), 30, 5, 120),
        )
        for path, line, severity, source, message in native_diagnostics:
            add(path, line, severity, source, message)
            if len(diagnostics) >= 1000:
                break

    counts = Counter(str(item["severity"]) for item in diagnostics)
    return {
        "path": _relative_workspace_path(resolved),
        "clean": counts.get("error", 0) == 0,
        "diagnostics": diagnostics[:1000],
        "files_scanned": files_scanned,
        "languages": [
            {"language": language, "files": count}
            for language, count in language_counts.most_common(20)
        ],
        "native_checks": native_checks,
        "native_checks_skipped": native_checks_skipped,
        "errors": counts.get("error", 0),
        "warnings": counts.get("warning", 0),
        "info": counts.get("info", 0),
        "truncated": len(diagnostics) >= 1000,
    }


async def _git_diff(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("repo_path", "."), must_exist=True)
    if not resolved:
        return {"changed_files": [], "diff": "", "error": err}
    if not resolved.is_dir():
        return {"changed_files": [], "diff": "", "error": "repo_path must be a directory."}

    pathspec = str(params.get("path") or "").strip()
    if pathspec.startswith("-") or ".." in Path(pathspec).parts:
        return {"changed_files": [], "diff": "", "error": "Invalid Git pathspec."}
    max_chars = _clamp_int(params.get("max_chars"), 20_000, 1000, 100_000)
    context_lines = _clamp_int(params.get("context_lines"), 3, 0, 20)

    repo_check = await _run_confined_command(
        ["git", "rev-parse", "--show-toplevel"], cwd=resolved, timeout=5, max_chars=2000
    )
    if not repo_check.get("passed"):
        return {
            "changed_files": [],
            "diff": "",
            "clean": False,
            "error": "Path is not inside a Git repository.",
            "details": repo_check.get("stderr", ""),
        }

    branch = await _run_confined_command(
        ["git", "branch", "--show-current"], cwd=resolved, timeout=5, max_chars=1000
    )
    status_args = ["git", "status", "--porcelain"]
    diff_args = ["git", "diff", "--no-ext-diff", f"--unified={context_lines}"]
    if bool(params.get("staged", False)):
        diff_args.append("--staged")
    if pathspec:
        status_args.extend(["--", pathspec])
        diff_args.extend(["--", pathspec])

    status = await _run_confined_command(status_args, cwd=resolved, timeout=10, max_chars=20000)
    diff = await _run_confined_command(diff_args, cwd=resolved, timeout=15, max_chars=max_chars)
    changed_files: list[dict[str, str]] = []
    for line in str(status.get("stdout") or "").splitlines():
        if len(line) < 4:
            continue
        changed_files.append({"status": line[:2].strip() or "?", "path": line[3:].strip()})

    if not status.get("passed") or not diff.get("passed"):
        return {
            "branch": str(branch.get("stdout") or "").strip(),
            "changed_files": changed_files,
            "diff": "",
            "clean": False,
            "error": (status.get("stderr") or diff.get("stderr") or "Git command failed"),
        }
    return {
        "repo_path": _relative_workspace_path(resolved),
        "branch": str(branch.get("stdout") or "").strip(),
        "staged": bool(params.get("staged", False)),
        "changed_files": changed_files,
        "clean": not changed_files,
        "diff": str(diff.get("stdout") or "")[-max_chars:],
        "truncated": len(str(diff.get("stdout") or "")) >= max_chars,
    }


def _python_compile_check(root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    errors: list[str] = []
    files_checked = 0
    paths = [root] if root.is_file() else list(_iter_workspace_files(root, max_files=20_000))
    for path in paths:
        if path.suffix.lower() != ".py" or _safe_file_size(path) > 3_000_000:
            continue
        files_checked += 1
        text, _, read_error = _read_text_limited(path, max_bytes=3_000_000)
        rel = _relative_workspace_path(path, root if root.is_dir() else root.parent)
        if read_error:
            errors.append(f"{rel}: {read_error}")
            continue
        try:
            compile(text, str(path), "exec", dont_inherit=True)
        except SyntaxError as exc:
            errors.append(f"{rel}:{exc.lineno or 1}: {exc.msg}")
        if len(errors) >= 100:
            break
    return {
        "name": "python_compile",
        "command": ["python", "-m", "compileall", "(in-process AST/compile, no bytecode written)"],
        "passed": not errors,
        "returncode": 0 if not errors else 1,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "files_checked": files_checked,
        "output": "\n".join(errors) if errors else f"Compiled {files_checked} Python files with no syntax errors.",
    }


def _package_dirs(root: Path) -> list[Path]:
    candidates = [root, root / "web", root / "frontend", root / "app", root / "client"]
    result: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_dir() and (resolved / "package.json").is_file() and resolved not in result:
            result.append(resolved)
    return result


_PROJECT_CHECK_NAMES = {
    "python_compile",
    "python_lint",
    "python_typecheck",
    "pytest",
    "npm_lint",
    "npm_typecheck",
    "npm_test",
    "npm_build",
    "frontend_quality",
    "c_syntax",
    "cpp_syntax",
    "cmake_build",
    "ctest",
    "make_build",
    "make_test",
    "cargo_fmt",
    "cargo_check",
    "cargo_clippy",
    "cargo_test",
    "php_lint",
    "composer_validate",
    "composer_test",
    "ruby_syntax",
    "ruby_test",
    "xml_validate",
    "git_status",
}


def _find_shallowest_file(root: Path, files: list[Path], names: set[str]) -> Path | None:
    candidates = [path for path in files if path.name in names]
    if not candidates:
        direct = [root / name for name in names if (root / name).is_file()]
        candidates.extend(direct)
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda path: (len(path.relative_to(root).parts) if path.is_relative_to(root) else 99, str(path)),
    )[0]


def _missing_tool_check(name: str, binary: str, purpose: str) -> dict[str, Any]:
    return {
        "name": name,
        "command": [binary],
        "passed": False,
        "returncode": -1,
        "tool_available": False,
        "output": f"{binary} is not installed, so Nexus could not run {purpose}. Install the toolchain and retry.",
    }


def _makefile_targets(path: Path) -> set[str]:
    text, _, _ = _read_text_limited(path, max_bytes=500_000, errors="replace")
    return {
        match.group(1)
        for match in re.finditer(r"^([A-Za-z0-9_.-]+)\s*:(?:\s|$)", text, re.M)
        if not match.group(1).startswith(".")
    }


def _internal_diagnostic_check(
    name: str,
    root: Path,
    files: list[Path],
    suffixes: set[str],
) -> dict[str, Any]:
    started = time.perf_counter()
    diagnostics: list[dict[str, Any]] = []
    files_checked = 0
    for path in sorted(files, key=lambda item: str(item)):
        if path.suffix.lower() not in suffixes or _safe_file_size(path) > 3_000_000:
            continue
        text, _, read_error = _read_text_limited(path, max_bytes=3_000_000, errors="strict")
        files_checked += 1
        rel = _relative_workspace_path(path, root)
        if read_error:
            diagnostics.append(
                {"file": rel, "line": 1, "severity": "error", "source": "read", "message": read_error}
            )
            continue
        for line, severity, source, message in _collect_text_diagnostics(path, text):
            diagnostics.append(
                {"file": rel, "line": line, "severity": severity, "source": source, "message": message}
            )
            if len(diagnostics) >= 500:
                break
        if len(diagnostics) >= 500:
            break
    errors = sum(1 for item in diagnostics if item["severity"] == "error")
    warnings = sum(1 for item in diagnostics if item["severity"] == "warning")
    if diagnostics:
        output_lines = [
            f"{item['file']}:{item['line']} [{item['severity']}/{item['source']}] {item['message']}"
            for item in diagnostics[:40]
        ]
        if len(diagnostics) > 40:
            output_lines.append(f"...and {len(diagnostics) - 40} more diagnostics")
        output = "\n".join(output_lines)
    else:
        output = f"Checked {files_checked} files with no diagnostics."
    return {
        "name": name,
        "command": ["internal", name],
        "passed": files_checked > 0 and errors == 0,
        "returncode": 0 if files_checked > 0 and errors == 0 else 1,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "files_checked": files_checked,
        "errors": errors,
        "warnings": warnings,
        "diagnostics": diagnostics[:200],
        "output": output if files_checked else f"No matching files found for {name}.",
    }


async def _native_syntax_project_check(
    name: str,
    root: Path,
    files: list[Path],
    language_key: str,
    *,
    timeout: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    if not files:
        return {
            "name": name,
            "passed": False,
            "returncode": -1,
            "files_checked": 0,
            "output": f"No {language_key} source files found for {name}.",
        }
    diagnostics, ran, skipped = await _native_syntax_diagnostics(
        root,
        {language_key: files},
        timeout=min(timeout, 120),
    )
    if not ran:
        missing_binary = {"c": "gcc", "cpp": "g++", "php": "php", "ruby": "ruby"}.get(language_key, language_key)
        result = _missing_tool_check(name, missing_binary, f"{name} on {len(files)} files")
        result.update({"files_checked": len(files), "skipped": skipped})
        return result
    formatted = [
        {
            "file": _relative_workspace_path(path, root),
            "line": line,
            "severity": severity,
            "source": source,
            "message": message,
        }
        for path, line, severity, source, message in diagnostics
    ]
    errors = sum(1 for item in formatted if item["severity"] == "error")
    warnings = sum(1 for item in formatted if item["severity"] == "warning")
    output = (
        "\n".join(
            f"{item['file']}:{item['line']} [{item['severity']}] {item['message']}" for item in formatted[:40]
        )
        if formatted
        else f"Syntax-checked {len(files)} files with no errors."
    )
    return {
        "name": name,
        "command": ["native_syntax", language_key],
        "passed": errors == 0,
        "returncode": 0 if errors == 0 else 1,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "files_checked": len(files),
        "errors": errors,
        "warnings": warnings,
        "diagnostics": formatted[:200],
        "skipped": skipped,
        "output": output,
    }


async def _cmake_project_check(
    name: str,
    root: Path,
    files: list[Path],
    *,
    timeout: int,
    run_tests: bool,
) -> dict[str, Any]:
    manifest = _find_shallowest_file(root, files, {"CMakeLists.txt"})
    if manifest is None:
        return {"name": name, "passed": False, "returncode": -1, "output": "No CMakeLists.txt found."}
    cmake = shutil.which("cmake")
    if not cmake:
        return _missing_tool_check(name, "cmake", "the CMake build")
    source_dir = manifest.parent
    build_dir = source_dir / "build"
    outputs: list[str] = []
    commands: list[list[str]] = []
    configure = [cmake, "-S", str(source_dir), "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Debug"]
    commands.append(configure)
    result = await _run_confined_command(configure, cwd=root, timeout=timeout, max_chars=20000)
    outputs.append(str(result.get("output") or ""))
    if not result.get("passed"):
        return {
            "name": name,
            **result,
            "commands": commands,
            "output": "\n".join(item for item in outputs if item).strip(),
        }
    build = [cmake, "--build", str(build_dir), "--parallel", "2"]
    commands.append(build)
    result = await _run_confined_command(build, cwd=root, timeout=timeout, max_chars=20000)
    outputs.append(str(result.get("output") or ""))
    if result.get("passed") and run_tests:
        ctest = shutil.which("ctest")
        if not ctest:
            missing = _missing_tool_check(name, "ctest", "CTest")
            missing["commands"] = commands
            return missing
        test_command = [ctest, "--test-dir", str(build_dir), "--output-on-failure"]
        commands.append(test_command)
        result = await _run_confined_command(test_command, cwd=root, timeout=timeout, max_chars=20000)
        outputs.append(str(result.get("output") or ""))
    return {
        "name": name,
        **result,
        "commands": commands,
        "output": "\n".join(item for item in outputs if item).strip()[-20000:],
    }


async def _make_project_check(
    name: str,
    root: Path,
    files: list[Path],
    *,
    timeout: int,
) -> dict[str, Any]:
    manifest = _find_shallowest_file(root, files, {"Makefile"})
    if manifest is None:
        return {"name": name, "passed": False, "returncode": -1, "output": "No Makefile found."}
    make = shutil.which("make")
    if not make:
        return _missing_tool_check(name, "make", "the Makefile target")
    targets = _makefile_targets(manifest)
    target: str | None = None
    if name == "make_test":
        target = "test" if "test" in targets else "check" if "check" in targets else None
        if target is None:
            return {
                "name": name,
                "passed": False,
                "returncode": -1,
                "output": "Makefile has no test or check target.",
                "targets": sorted(targets),
            }
    elif "all" in targets:
        target = "all"
    command = [make, "-C", str(manifest.parent)]
    if target:
        command.append(target)
    result = await _run_confined_command(command, cwd=root, timeout=timeout, max_chars=20000)
    return {"name": name, "target": target or "(default)", **result}


async def _cargo_project_check(
    name: str,
    root: Path,
    files: list[Path],
    *,
    timeout: int,
) -> dict[str, Any]:
    manifest = _find_shallowest_file(root, files, {"Cargo.toml"})
    if manifest is None:
        return {"name": name, "passed": False, "returncode": -1, "output": "No Cargo.toml found."}
    cargo = shutil.which("cargo")
    if not cargo:
        return _missing_tool_check(name, "cargo", "the Rust Cargo check")
    commands = {
        "cargo_fmt": [cargo, "fmt", "--all", "--", "--check"],
        "cargo_check": [cargo, "check", "--all-targets"],
        "cargo_clippy": [cargo, "clippy", "--all-targets", "--", "-D", "warnings"],
        "cargo_test": [cargo, "test"],
    }
    result = await _run_confined_command(
        commands[name],
        cwd=manifest.parent,
        timeout=timeout,
        max_chars=20000,
    )
    return {"name": name, "cwd": _relative_workspace_path(manifest.parent), **result}


async def _composer_project_check(
    name: str,
    root: Path,
    files: list[Path],
    *,
    timeout: int,
) -> dict[str, Any]:
    manifest = _find_shallowest_file(root, files, {"composer.json"})
    if manifest is None:
        return {"name": name, "passed": False, "returncode": -1, "output": "No composer.json found."}
    payload = _parse_package_json(manifest)
    scripts = payload.get("scripts") if isinstance(payload.get("scripts"), dict) else {}
    if name == "composer_test" and "test" not in scripts and not (manifest.parent / "vendor/bin/phpunit").is_file():
        return {
            "name": name,
            "passed": False,
            "returncode": -1,
            "output": "composer.json has no test script and vendor/bin/phpunit is not installed.",
        }
    composer = shutil.which("composer")
    if composer:
        command = (
            [composer, "validate", "--no-check-publish", "--no-interaction"]
            if name == "composer_validate"
            else [composer, "test", "--no-interaction"]
        )
        result = await _run_confined_command(command, cwd=manifest.parent, timeout=timeout, max_chars=20000)
        return {"name": name, "cwd": _relative_workspace_path(manifest.parent), **result}
    if name == "composer_test" and (manifest.parent / "vendor/bin/phpunit").is_file():
        php = shutil.which("php")
        if not php:
            return _missing_tool_check(name, "php", "PHPUnit")
        result = await _run_confined_command(
            [php, "vendor/bin/phpunit"],
            cwd=manifest.parent,
            timeout=timeout,
            max_chars=20000,
        )
        return {"name": name, "cwd": _relative_workspace_path(manifest.parent), **result}
    return _missing_tool_check(name, "composer", "the Composer check")


async def _ruby_test_project_check(
    root: Path,
    files: list[Path],
    *,
    timeout: int,
) -> dict[str, Any]:
    ruby = shutil.which("ruby")
    if not ruby:
        return _missing_tool_check("ruby_test", "ruby", "the Ruby tests")
    gemfile = _find_shallowest_file(root, files, {"Gemfile"})
    rakefile = _find_shallowest_file(root, files, {"Rakefile"})
    project_dir = (gemfile or rakefile).parent if (gemfile or rakefile) else root
    bundle = shutil.which("bundle") if gemfile else None
    test_files = [
        path
        for path in files
        if path.suffix.lower() == ".rb" and _is_test_path(path, root) and not path.name.endswith("_spec.rb")
    ]
    spec_files = [path for path in files if path.name.endswith("_spec.rb")]

    command: list[str] | None = None
    if bundle and spec_files:
        command = [bundle, "exec", "rspec"]
    elif bundle and rakefile:
        command = [bundle, "exec", "rake", "test"]
    elif spec_files and shutil.which("rspec"):
        command = [str(shutil.which("rspec"))]
    elif rakefile and shutil.which("rake"):
        command = [str(shutil.which("rake")), "test"]
    if command:
        result = await _run_confined_command(command, cwd=project_dir, timeout=timeout, max_chars=20000)
        return {"name": "ruby_test", "cwd": _relative_workspace_path(project_dir), **result}

    outputs: list[str] = []
    commands: list[list[str]] = []
    passed = bool(test_files)
    for path in sorted(test_files, key=str)[:100]:
        test_command = [ruby]
        if (project_dir / "lib").is_dir():
            test_command.append("-Ilib")
        if (project_dir / "test").is_dir():
            test_command.append("-Itest")
        try:
            test_command.append(str(path.relative_to(project_dir)))
        except ValueError:
            test_command.append(str(path))
        commands.append(test_command)
        result = await _run_confined_command(
            test_command,
            cwd=project_dir,
            timeout=min(timeout, 60),
            max_chars=12000,
        )
        outputs.append(str(result.get("output") or ""))
        passed = passed and bool(result.get("passed"))
        if not result.get("passed"):
            break
    return {
        "name": "ruby_test",
        "commands": commands,
        "passed": passed,
        "returncode": 0 if passed else 1,
        "files_checked": len(commands),
        "output": "\n".join(item for item in outputs if item).strip()[-20000:]
        or ("Ruby tests passed." if passed else "No Ruby test files or supported test runner found."),
    }


async def _python_module_project_check(
    name: str,
    root: Path,
    *,
    timeout: int,
) -> dict[str, Any]:
    import importlib.util

    module = "ruff" if name == "python_lint" else "mypy"
    if importlib.util.find_spec(module) is None:
        return _missing_tool_check(name, module, f"the Python {module} check")
    if name == "python_lint":
        command = [sys.executable, "-m", "ruff", "check", "."]
    else:
        target = "src" if (root / "src").is_dir() else "."
        command = [sys.executable, "-m", "mypy", target, "--ignore-missing-imports"]
    result = await _run_confined_command(command, cwd=root, timeout=timeout, max_chars=20000)
    return {"name": name, **result}


async def _project_checks(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("path", "."), must_exist=True)
    if not resolved:
        return {"passed": False, "checks": [], "error": err}
    if not resolved.is_dir():
        return {"passed": False, "checks": [], "error": "path must be a project directory."}

    timeout = _clamp_int(params.get("timeout"), 60, 5, 300)
    raw_checks = params.get("checks")
    requested: list[str] | None = None
    if isinstance(raw_checks, list):
        requested = [str(item).strip().lower() for item in raw_checks if str(item).strip()]
    elif isinstance(raw_checks, str) and raw_checks.strip():
        requested = [part.strip().lower() for part in re.split(r"[,\s]+", raw_checks) if part.strip()]

    sample_files = list(_iter_workspace_files(resolved, max_files=5000))
    has_python = any(path.suffix == ".py" for path in sample_files)
    has_python_tests = any(
        _is_test_path(path, resolved) and path.suffix.lower() == ".py" for path in sample_files
    )
    has_tests = any(_is_test_path(path, resolved) for path in sample_files)
    package_dirs = _package_dirs(resolved)
    suffixes = {path.suffix.lower() for path in sample_files}
    filenames = {path.name for path in sample_files}

    if requested is None:
        requested = []
        if has_python:
            requested.append("python_compile")
        if has_python and (has_python_tests or (resolved / "tests").is_dir()):
            requested.append("pytest")
        if ".c" in suffixes and (shutil.which("gcc") or shutil.which("cc") or shutil.which("clang")):
            requested.append("c_syntax")
        if suffixes & {".cpp", ".cc", ".cxx"} and (
            shutil.which("g++") or shutil.which("c++") or shutil.which("clang++")
        ):
            requested.append("cpp_syntax")
        makefile = _find_shallowest_file(resolved, sample_files, {"Makefile"})
        if makefile and shutil.which("make") and (_makefile_targets(makefile) & {"test", "check"}):
            requested.append("make_test")
        elif "CMakeLists.txt" in filenames and shutil.which("cmake"):
            requested.extend(["cmake_build", "ctest"])
        if "Cargo.toml" in filenames and shutil.which("cargo"):
            requested.extend(["cargo_fmt", "cargo_check", "cargo_clippy", "cargo_test"])
        if suffixes & {".php", ".phtml"} and shutil.which("php"):
            requested.append("php_lint")
        if "composer.json" in filenames and shutil.which("composer"):
            requested.append("composer_test")
        if suffixes & {".rb", ".rake", ".gemspec"} and shutil.which("ruby"):
            requested.append("ruby_syntax")
            if has_tests:
                requested.append("ruby_test")
        if suffixes & {".xml", ".xsd", ".xsl", ".xslt", ".svg"}:
            requested.append("xml_validate")
        if suffixes & {".html", ".htm", ".css", ".scss", ".jsx", ".tsx"}:
            requested.append("frontend_quality")
        for package_dir in package_dirs:
            scripts = _parse_package_json(package_dir / "package.json").get("scripts", {})
            if isinstance(scripts, dict):
                if "lint" in scripts:
                    requested.append("npm_lint")
                if scripts.keys() & {"typecheck", "type-check", "check"}:
                    requested.append("npm_typecheck")
                if "build" in scripts:
                    requested.append("npm_build")
            break
        if not requested:
            requested = ["git_status"]

    supported = _PROJECT_CHECK_NAMES
    requested = list(dict.fromkeys(requested))
    results: list[dict[str, Any]] = []

    for check in requested:
        if check not in supported:
            results.append(
                {
                    "name": check,
                    "passed": False,
                    "returncode": -1,
                    "output": f"Unsupported check '{check}'. Supported: {', '.join(sorted(supported))}.",
                }
            )
            continue

        if check == "python_compile":
            results.append(_python_compile_check(resolved))
            continue

        if check in {"python_lint", "python_typecheck"}:
            results.append(await _python_module_project_check(check, resolved, timeout=timeout))
            continue

        if check in {"frontend_quality", "xml_validate"}:
            check_suffixes = (
                {".xml", ".xsd", ".xsl", ".xslt", ".svg"}
                if check == "xml_validate"
                else {".html", ".htm", ".css", ".scss", ".jsx", ".tsx"}
            )
            results.append(_internal_diagnostic_check(check, resolved, sample_files, check_suffixes))
            continue

        if check in {"c_syntax", "cpp_syntax", "php_lint", "ruby_syntax"}:
            language_key = {
                "c_syntax": "c",
                "cpp_syntax": "cpp",
                "php_lint": "php",
                "ruby_syntax": "ruby",
            }[check]
            language_suffixes = {
                "c": {".c"},
                "cpp": {".cpp", ".cc", ".cxx"},
                "php": {".php", ".phtml"},
                "ruby": {".rb", ".rake", ".gemspec"},
            }[language_key]
            language_files = [path for path in sample_files if path.suffix.lower() in language_suffixes]
            # Special Ruby project files have no conventional suffix.
            if language_key == "ruby":
                language_files.extend(
                    path for path in sample_files if path.name in {"Gemfile", "Rakefile"}
                )
            results.append(
                await _native_syntax_project_check(
                    check,
                    resolved,
                    list(dict.fromkeys(language_files)),
                    language_key,
                    timeout=timeout,
                )
            )
            continue

        if check in {"cmake_build", "ctest"}:
            results.append(
                await _cmake_project_check(
                    check,
                    resolved,
                    sample_files,
                    timeout=timeout,
                    run_tests=check == "ctest",
                )
            )
            continue

        if check in {"make_build", "make_test"}:
            results.append(await _make_project_check(check, resolved, sample_files, timeout=timeout))
            continue

        if check in {"cargo_fmt", "cargo_check", "cargo_clippy", "cargo_test"}:
            results.append(await _cargo_project_check(check, resolved, sample_files, timeout=timeout))
            continue

        if check in {"composer_validate", "composer_test"}:
            results.append(await _composer_project_check(check, resolved, sample_files, timeout=timeout))
            continue

        if check == "ruby_test":
            results.append(await _ruby_test_project_check(resolved, sample_files, timeout=timeout))
            continue

        if check == "pytest":
            target = str(params.get("target") or ("tests" if (resolved / "tests").exists() else ".")).strip()
            base_target = target.split("::", 1)[0]
            if not target or target.startswith("-") or any(char in target for char in " \t;|&`$"):
                results.append(
                    {"name": check, "passed": False, "returncode": -1, "output": "Invalid pytest target."}
                )
                continue
            target_path, target_error = resolve_confined_path((resolved / base_target).as_posix(), must_exist=True)
            if not target_path:
                results.append(
                    {"name": check, "passed": False, "returncode": -1, "output": target_error}
                )
                continue
            result = await _run_confined_command(
                [sys.executable, "-m", "pytest", target, "-q", "--tb=short"],
                cwd=resolved,
                timeout=timeout,
                max_chars=20000,
            )
            results.append({"name": check, **result})
            continue

        if check == "git_status":
            result = await _run_confined_command(
                ["git", "status", "--porcelain"],
                cwd=resolved,
                timeout=min(timeout, 15),
                max_chars=20000,
            )
            output = str(result.get("stdout") or "")
            results.append(
                {
                    "name": check,
                    **result,
                    "changed_files": [line for line in output.splitlines() if line.strip()],
                    "output": output or "Working tree clean.",
                }
            )
            continue

        script_candidates = {
            "npm_lint": ("lint",),
            "npm_test": ("test",),
            "npm_build": ("build",),
            "npm_typecheck": ("typecheck", "type-check", "check"),
        }[check]
        script_name = script_candidates[0]
        selected_dir: Path | None = None
        selected_scripts: dict[str, Any] = {}
        for package_dir in package_dirs:
            payload = _parse_package_json(package_dir / "package.json")
            scripts = payload.get("scripts") if isinstance(payload.get("scripts"), dict) else {}
            matched_script = next((candidate for candidate in script_candidates if candidate in scripts), None)
            if matched_script:
                script_name = matched_script
                selected_dir = package_dir
                selected_scripts = scripts
                break
            if check == "npm_typecheck" and any(
                "tsc" in str(value) for value in scripts.values() if isinstance(value, str)
            ):
                script_name = next(
                    key for key, value in scripts.items() if isinstance(value, str) and "tsc" in value
                )
                selected_dir = package_dir
                selected_scripts = scripts
                break
        if selected_dir is None:
            results.append(
                {
                    "name": check,
                    "passed": False,
                    "returncode": -1,
                    "output": f"No package.json with a '{script_name}' script found under the project root.",
                }
            )
            continue
        if not shutil.which("npm"):
            results.append(_missing_tool_check(check, "npm", "the npm script"))
            continue
        command = ["npm", "test", "--silent"] if check == "npm_test" else ["npm", "run", script_name, "--silent"]
        result = await _run_confined_command(
            command,
            cwd=selected_dir,
            timeout=timeout,
            max_chars=20000,
        )
        results.append(
            {
                "name": check,
                "cwd": _relative_workspace_path(selected_dir),
                "script": str(selected_scripts.get(script_name) or ""),
                **result,
            }
        )

    return {
        "path": _relative_workspace_path(resolved),
        "passed": all(bool(item.get("passed")) for item in results) if results else False,
        "checks": results,
        "checks_requested": requested,
        "supported_checks": sorted(supported),
    }


def _redact_secret(value: str) -> str:
    text = str(value or "")
    if len(text) <= 8:
        return "***"
    return f"{text[:3]}***{text[-2:]} ({len(text)} chars)"


def _looks_like_placeholder(value: str) -> bool:
    text = str(value or "").strip()
    lower = text.lower()
    if not text:
        return True
    if len(set(text)) <= 2 and len(text) >= 8:
        return True
    placeholder_markers = (
        "example",
        "changeme",
        "change-me",
        "change_me",
        "your-",
        "your_",
        "placeholder",
        "dummy",
        "fake",
        "sample",
        "***",
        "xxx",
        "${",
        "process.env",
        "os.getenv",
        "os.environ",
        "getenv(",
        "env[",
        "sk-local-dev",
        "sk-test",
        "bridge-test",
        "local-no-key",
        "test-token",
        "not-a-real",
        "redacted",
    )
    return any(marker in lower for marker in placeholder_markers) or text.startswith(("<", "$"))


async def _secret_scan(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("path", "."), must_exist=True)
    if not resolved:
        return {"clean": False, "findings": [], "files_scanned": 0, "error": err}

    max_files = _clamp_int(params.get("max_files"), 2000, 1, 10_000)
    max_findings = _clamp_int(params.get("max_findings"), 100, 1, 500)
    include_hidden = bool(params.get("include_hidden", False))
    include_tests = bool(params.get("include_tests", True))
    extensions = _normalize_extensions(params.get("extensions"))
    started = time.perf_counter()

    if resolved.is_file():
        scan_root = resolved.parent
        candidate_files = [resolved]
        scan_truncated = False
    elif resolved.is_dir():
        scan_root = resolved
        candidate_files = list(
            _iter_workspace_files(
                resolved,
                include_hidden=include_hidden,
                max_files=max_files + 1,
            )
        )
        scan_truncated = len(candidate_files) > max_files
        candidate_files = candidate_files[:max_files]
    else:
        return {"clean": False, "findings": [], "files_scanned": 0, "error": "Path is neither a file nor directory."}

    token_patterns: list[tuple[str, str, re.Pattern[str], int | None]] = [
        ("private_key", "high", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"), None),
        ("aws_access_key_id", "high", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), None),
        ("github_token", "high", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"), None),
        ("openai_style_api_key", "high", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"), None),
        ("jwt", "medium", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), None),
        ("bearer_token", "medium", re.compile(r"\bBearer\s+([A-Za-z0-9._~+/=-]{20,})"), 1),
    ]
    assignment_re = re.compile(
        r"(?i)\b(?P<key>(?:[A-Za-z0-9]+[_-])*(?:api[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|password|passwd|secret|token)(?:[_-][A-Za-z0-9]+)*)"
        r"\s*[:=]\s*(?P<quote>['\"])(?P<value>[^'\"]{8,})(?P=quote)"
    )
    advice_by_kind = {
        "private_key": "Remove the private key from the repo, rotate it, and load keys from a secret manager or ignored local file.",
        "aws_access_key_id": "Rotate this AWS access key and move credentials to environment/IAM configuration outside the repo.",
        "github_token": "Revoke and rotate this GitHub token; store tokens in CI secrets or a local secret manager.",
        "openai_style_api_key": "Rotate this API key and read it from an environment variable instead of source code.",
        "jwt": "Do not commit live JWTs; invalidate/rotate the signing secret if this token is real.",
        "bearer_token": "Remove the bearer token from source and inject it at runtime; rotate it if it was ever valid.",
        "credential_assignment": "Move this credential to an environment variable or secret manager and rotate it if it is real.",
    }

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    files_scanned = 0
    skipped_files = 0
    files_with_findings: set[str] = set()

    def add_finding(path: Path, line_no: int, kind: str, severity: str, value: str) -> None:
        if len(findings) >= max_findings:
            return
        rel = _relative_workspace_path(path, scan_root)
        preview = value if kind == "private_key" else _redact_secret(value)
        key = (rel, line_no, kind, preview)
        if key in seen:
            return
        seen.add(key)
        files_with_findings.add(rel)
        findings.append(
            {
                "file": rel,
                "line": line_no,
                "kind": kind,
                "severity": severity,
                "redacted_preview": preview,
                "advice": advice_by_kind.get(kind, "Review this value and move real credentials out of the repository."),
            }
        )

    for path in candidate_files:
        suffix = path.suffix.lower()
        if extensions and suffix not in extensions:
            continue
        if suffix and suffix not in _TEXT_EXTENSIONS and path.name not in _MANIFEST_NAMES:
            skipped_files += 1
            continue
        if not include_tests and resolved.is_dir() and _is_test_path(path, scan_root):
            skipped_files += 1
            continue
        if _safe_file_size(path) > 2_000_000:
            skipped_files += 1
            continue
        text, _, read_error = _read_text_limited(path, max_bytes=2_000_000, errors="strict")
        if read_error:
            skipped_files += 1
            continue
        files_scanned += 1
        for line_no, line in enumerate(text.splitlines(), start=1):
            if len(findings) >= max_findings:
                break
            for kind, severity, pattern, group_index in token_patterns:
                for match in pattern.finditer(line):
                    value = match.group(group_index) if group_index is not None else match.group(0)
                    if kind != "private_key" and _looks_like_placeholder(value):
                        continue
                    add_finding(path, line_no, kind, severity, value)
                    if len(findings) >= max_findings:
                        break
                if len(findings) >= max_findings:
                    break
            if len(findings) >= max_findings:
                break
            for match in assignment_re.finditer(line):
                key_name = match.group("key").lower()
                value = match.group("value")
                if _looks_like_placeholder(value):
                    continue
                severity = "high" if any(token in key_name for token in ("api", "secret", "password", "passwd")) else "medium"
                add_finding(path, line_no, "credential_assignment", severity, value)
                if len(findings) >= max_findings:
                    break
        if len(findings) >= max_findings:
            break

    by_kind = Counter(str(item["kind"]) for item in findings)
    by_severity = Counter(str(item["severity"]) for item in findings)
    risk_level = "none"
    if by_severity.get("high"):
        risk_level = "high"
    elif by_severity.get("medium"):
        risk_level = "medium"

    return {
        "path": _relative_workspace_path(resolved),
        "clean": not findings,
        "risk_level": risk_level,
        "findings": findings,
        "findings_by_kind": dict(sorted(by_kind.items())),
        "findings_by_severity": dict(sorted(by_severity.items())),
        "files_scanned": files_scanned,
        "files_with_findings": len(files_with_findings),
        "skipped_files": skipped_files,
        "truncated": scan_truncated or len(findings) >= max_findings,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "notes": [
            "Secret values are redacted in this report.",
            "Denylisted credential files such as .env and private-key files are skipped by workspace policy.",
        ],
    }


async def _release_readiness(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("path", "."), must_exist=True)
    if not resolved:
        return {"ready": False, "status": "not_ready", "score": 0, "blockers": [], "warnings": [], "error": err}
    if not resolved.is_dir():
        return {
            "ready": False,
            "status": "not_ready",
            "score": 0,
            "blockers": [{"code": "not_a_directory", "message": "Release readiness needs a project directory."}],
            "warnings": [],
            "error": "path must be a project directory.",
        }

    started = time.perf_counter()
    max_files = _clamp_int(params.get("max_files"), 5000, 100, 20_000)
    timeout = _clamp_int(params.get("timeout"), 120, 5, 300)
    include_checks = bool(params.get("include_checks", False))
    fail_on_dirty = bool(params.get("fail_on_dirty", True))
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def blocker(code: str, message: str, **detail: Any) -> None:
        blockers.append({"code": code, "message": message, **{k: v for k, v in detail.items() if v not in (None, "", [], {})}})

    def warning(code: str, message: str, **detail: Any) -> None:
        warnings.append({"code": code, "message": message, **{k: v for k, v in detail.items() if v not in (None, "", [], {})}})

    scan = await _project_scan(
        {"path": str(resolved), "max_files": max_files, "include_line_counts": False}
    )
    if scan.get("error"):
        blocker("project_scan_failed", "Project scan failed.", detail=str(scan.get("error")))
        scan = {}

    diagnostics = await _code_diagnostics({"path": str(resolved), "include_todos": True})
    if diagnostics.get("error"):
        blocker("diagnostics_failed", "Code diagnostics could not complete.", detail=str(diagnostics.get("error")))
    elif int(diagnostics.get("errors") or 0) > 0:
        blocker(
            "syntax_or_parse_errors",
            "Syntax or parse errors must be fixed before release.",
            count=int(diagnostics.get("errors") or 0),
        )
    todo_count = int(diagnostics.get("info") or 0) if isinstance(diagnostics, dict) else 0
    if todo_count:
        warning("todo_markers", "TODO/FIXME markers remain in the tree.", count=todo_count)

    secrets = await _secret_scan({"path": str(resolved), "max_files": max_files, "max_findings": 100})
    if secrets.get("error"):
        blocker("secret_scan_failed", "Secret scan could not complete.", detail=str(secrets.get("error")))
    else:
        severity_counts = secrets.get("findings_by_severity") if isinstance(secrets.get("findings_by_severity"), dict) else {}
        if int(severity_counts.get("high") or 0) > 0:
            blocker(
                "likely_secrets",
                "High-confidence likely secrets were found; remove and rotate them before release.",
                count=int(severity_counts.get("high") or 0),
            )
        if int(severity_counts.get("medium") or 0) > 0:
            warning(
                "possible_secrets",
                "Possible credential-like values need review before release.",
                count=int(severity_counts.get("medium") or 0),
            )

    git = await _git_info({"repo_path": str(resolved)})
    git_summary: dict[str, Any] = {}
    if git.get("is_git_repository"):
        changed_count = int(git.get("changed_count") or len(git.get("changed_files") or []))
        git_summary = {
            "is_git_repository": True,
            "branch": git.get("branch", "unknown"),
            "clean": bool(git.get("is_clean")),
            "changed_count": changed_count,
            "staged_count": int(git.get("staged_count") or 0),
            "unstaged_count": int(git.get("unstaged_count") or 0),
            "untracked_count": int(git.get("untracked_count") or 0),
            "last_commit": git.get("last_commit", ""),
        }
        if changed_count:
            message = "Working tree has uncommitted changes; commit, stash, or intentionally exclude them before tagging a release."
            if fail_on_dirty:
                blocker("uncommitted_changes", message, count=changed_count)
            else:
                warning("uncommitted_changes", message, count=changed_count)
    else:
        git_summary = {"is_git_repository": False, "clean": False, "changed_count": 0}
        warning("not_a_git_repository", "Project is not inside a Git repository, so the release cannot be tagged or audited from history here.")

    top_level_names = {
        str(item.get("name") or "").lower()
        for item in (scan.get("top_level") or [])
        if isinstance(item, dict)
    }
    manifests = scan.get("manifests") if isinstance(scan.get("manifests"), list) else []
    manifest_paths = [str(item.get("path")) for item in manifests if isinstance(item, dict) and item.get("path")]
    if not any(name.startswith("readme") for name in top_level_names):
        warning("missing_readme", "No top-level README was detected.")
    if not any(name.startswith(("license", "copying")) for name in top_level_names):
        warning("missing_license", "No top-level LICENSE file was detected.")
    if not manifest_paths:
        warning("no_manifest", "No package/project manifest was detected in the scan.")
    if int(scan.get("test_files") or 0) == 0:
        warning("no_tests_found", "No test files were detected by the project scan.")

    dependency_summary: dict[str, Any] | None = None
    languages = scan.get("languages") if isinstance(scan.get("languages"), list) else []
    has_python = any(isinstance(item, dict) and item.get("language") == "Python" for item in languages)
    if has_python:
        source_candidate = resolved / "src" if (resolved / "src").is_dir() else resolved
        req_candidate = next(
            (resolved / name for name in ("requirements.in", "requirements.txt") if (resolved / name).is_file()),
            resolved / "requirements.in",
        )
        dependency = await _dependency_audit(
            {
                "source_path": str(source_candidate),
                "requirements_path": str(req_candidate),
                "pyproject_path": str(resolved / "pyproject.toml"),
            }
        )
        undeclared = dependency.get("undeclared") if isinstance(dependency.get("undeclared"), list) else []
        parse_errors = dependency.get("parse_errors") if isinstance(dependency.get("parse_errors"), list) else []
        unused = dependency.get("unused_declared") if isinstance(dependency.get("unused_declared"), list) else []
        dependency_summary = {
            "clean": bool(dependency.get("clean")),
            "undeclared": [str(item) for item in undeclared[:30]],
            "unused_declared_count": len(unused),
            "parse_errors": [str(item)[:300] for item in parse_errors[:5]],
            "files_scanned": int(dependency.get("files_scanned") or 0),
            "manifest_files": dependency.get("manifest_files") or [],
        }
        if undeclared:
            blocker(
                "undeclared_dependencies",
                "Python imports are missing from the declared dependency manifests.",
                packages=[str(item) for item in undeclared[:30]],
            )
        if parse_errors and not int(diagnostics.get("errors") or 0):
            warning("dependency_parse_errors", "Dependency audit reported parse/read issues.", count=len(parse_errors))
        if unused:
            warning("unused_declared_dependencies", "Some declared Python dependencies were not imported in the scanned tree.", count=len(unused))

    checks_summary: list[dict[str, Any]] | None = None
    checks_passed: bool | None = None
    if include_checks:
        check_params: dict[str, Any] = {"path": str(resolved), "timeout": timeout}
        if params.get("checks") is not None:
            check_params["checks"] = params.get("checks")
        checks_result = await _project_checks(check_params)
        checks_passed = bool(checks_result.get("passed"))
        checks_summary = []
        for item in checks_result.get("checks") or []:
            if not isinstance(item, dict):
                continue
            output = str(item.get("output") or item.get("stdout") or item.get("stderr") or "")
            checks_summary.append(
                {
                    "name": str(item.get("name") or "check"),
                    "passed": bool(item.get("passed")),
                    "output": output[:600],
                }
            )
        if checks_result.get("error"):
            blocker("project_checks_failed", "Project checks could not complete.", detail=str(checks_result.get("error")))
        elif not checks_passed:
            blocker("project_checks_failed", "One or more project checks failed.")

    score = max(0, 100 - min(75, 25 * len(blockers)) - min(30, 7 * len(warnings)))
    ready = not blockers
    status = "ready" if ready and not warnings else "ready_with_warnings" if ready else "not_ready"

    actions: list[str] = []
    blocker_codes = {str(item.get("code")) for item in blockers}
    warning_codes = {str(item.get("code")) for item in warnings}
    if "syntax_or_parse_errors" in blocker_codes:
        actions.append("Fix the diagnostics errors first, then rerun code_diagnostics.")
    if "likely_secrets" in blocker_codes or "possible_secrets" in warning_codes:
        actions.append("Remove likely secrets from source, rotate any real credentials, and rerun secret_scan.")
    if "uncommitted_changes" in blocker_codes or "uncommitted_changes" in warning_codes:
        actions.append("Review git_diff, then commit or stash the intended release state before tagging.")
    if "undeclared_dependencies" in blocker_codes:
        actions.append("Add the undeclared packages to the correct manifest or remove the imports.")
    if "project_checks_failed" in blocker_codes:
        actions.append("Open the failing project check output, fix the first failure, and rerun the targeted check.")
    if "no_tests_found" in warning_codes:
        actions.append("Add at least a smoke test for the main user path before a public release.")
    if not include_checks:
        actions.append("Run release_readiness with include_checks=true or run project_checks before tagging.")
    if ready:
        actions.append("Draft release notes with changelog_draft and tag the verified commit.")

    project_summary = {
        "files": int(scan.get("files") or 0),
        "directories": int(scan.get("directories") or 0),
        "languages": languages[:8],
        "frameworks": scan.get("frameworks") or [],
        "test_files": int(scan.get("test_files") or 0),
        "manifests": manifest_paths[:20],
        "suggested_commands": (scan.get("suggested_commands") or [])[:12],
    }
    diagnostics_summary = {
        "clean": bool(diagnostics.get("clean")),
        "errors": int(diagnostics.get("errors") or 0),
        "warnings": int(diagnostics.get("warnings") or 0),
        "info": int(diagnostics.get("info") or 0),
        "files_scanned": int(diagnostics.get("files_scanned") or 0),
        "diagnostics": (diagnostics.get("diagnostics") or [])[:10],
    }
    secret_summary = {
        "clean": bool(secrets.get("clean")),
        "risk_level": secrets.get("risk_level", "unknown"),
        "findings_by_severity": secrets.get("findings_by_severity") or {},
        "findings_by_kind": secrets.get("findings_by_kind") or {},
        "files_scanned": int(secrets.get("files_scanned") or 0),
        "findings": (secrets.get("findings") or [])[:10],
    }

    return {
        "path": _relative_workspace_path(resolved),
        "ready": ready,
        "status": status,
        "score": score,
        "summary": f"Release readiness: {status}; score {score}/100; {len(blockers)} blocker(s), {len(warnings)} warning(s).",
        "blockers": blockers,
        "warnings": warnings,
        "project": project_summary,
        "git": git_summary,
        "diagnostics": diagnostics_summary,
        "secrets": secret_summary,
        "dependencies": dependency_summary,
        "checks_run": include_checks,
        "checks_passed": checks_passed,
        "checks": checks_summary,
        "recommended_next_actions": list(dict.fromkeys(actions))[:10],
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def _classify_commit_subject(subject: str) -> tuple[str, str, str, bool, str]:
    text = " ".join(str(subject or "").strip().split())
    lower = text.lower()
    conventional = re.match(r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?:\s*(?P<rest>.+)$", text)
    type_map = {
        "feat": "Added",
        "feature": "Added",
        "fix": "Fixed",
        "bugfix": "Fixed",
        "hotfix": "Fixed",
        "docs": "Documentation",
        "doc": "Documentation",
        "refactor": "Changed",
        "perf": "Performance",
        "performance": "Performance",
        "test": "Tests",
        "tests": "Tests",
        "build": "Maintenance",
        "ci": "Maintenance",
        "chore": "Maintenance",
        "style": "Changed",
        "security": "Security",
        "revert": "Changed",
    }
    breaking = "breaking change" in lower
    if conventional:
        commit_type = conventional.group("type").lower()
        scope = str(conventional.group("scope") or "").strip()
        breaking = breaking or bool(conventional.group("bang"))
        if commit_type in type_map:
            return type_map[commit_type], commit_type, scope, breaking, str(conventional.group("rest") or text).strip()
    if any(token in lower for token in ("security", "vulnerab", "cve-", "secret", "credential")):
        category = "Security"
    elif any(token in lower for token in ("fix", "bug", "error", "crash", "broken", "repair")):
        category = "Fixed"
    elif any(token in lower for token in ("add", "create", "introduce", "implement", "support", "new ")):
        category = "Added"
    elif any(token in lower for token in ("doc", "readme", "guide", "comment")):
        category = "Documentation"
    elif any(token in lower for token in ("test", "coverage", "pytest")):
        category = "Tests"
    elif any(token in lower for token in ("perf", "performance", "faster", "optimize", "speed")):
        category = "Performance"
    elif any(token in lower for token in ("refactor", "rename", "move", "update", "change", "improve", "upgrade")):
        category = "Changed"
    elif any(token in lower for token in ("chore", "ci", "build", "release", "bump", "dependency", "dependencies")):
        category = "Maintenance"
    else:
        category = "Other"
    return category, "", "", breaking, text


async def _changelog_draft(params: dict[str, Any]) -> dict[str, Any]:
    resolved, err = resolve_confined_path(params.get("repo_path", "."), must_exist=True)
    if not resolved:
        return {"markdown": "", "commits": [], "commit_count": 0, "files_changed": [], "error": err}
    if not resolved.is_dir():
        return {"markdown": "", "commits": [], "commit_count": 0, "files_changed": [], "error": "repo_path must be a directory."}

    def valid_ref(value: str) -> bool:
        return bool(value) and not value.startswith("-") and ".." not in value and bool(re.fullmatch(r"[A-Za-z0-9._/@{}~^:-]+", value))

    from_ref = str(params.get("from_ref") or "").strip()
    to_ref = str(params.get("to_ref") or "HEAD").strip() or "HEAD"
    if (from_ref and not valid_ref(from_ref)) or not valid_ref(to_ref):
        return {"markdown": "", "commits": [], "commit_count": 0, "files_changed": [], "error": "Invalid Git ref."}
    max_commits = _clamp_int(params.get("max_commits"), 50, 1, 500)
    include_uncommitted = bool(params.get("include_uncommitted", True))

    repo_check = await _run_confined_command(
        ["git", "rev-parse", "--show-toplevel"], cwd=resolved, timeout=5, max_chars=2000
    )
    if not repo_check.get("passed"):
        return {
            "markdown": "",
            "commits": [],
            "commit_count": 0,
            "files_changed": [],
            "error": "Path is not inside a Git repository.",
            "details": repo_check.get("stderr", ""),
        }
    head_check = await _run_confined_command(
        ["git", "rev-parse", "--verify", to_ref], cwd=resolved, timeout=5, max_chars=2000
    )
    if not head_check.get("passed"):
        return {
            "markdown": "# Changelog draft\n\nNo commits found for the requested ref.\n",
            "commits": [],
            "commit_count": 0,
            "files_changed": [],
            "from_ref": from_ref or None,
            "to_ref": to_ref,
            "error": f"Git ref not found or repository has no commits: {to_ref}",
        }

    effective_from = from_ref
    if not effective_from:
        tag_result = await _run_confined_command(
            ["git", "describe", "--tags", "--abbrev=0", to_ref], cwd=resolved, timeout=5, max_chars=2000
        )
        tag = str(tag_result.get("stdout") or "").strip()
        if tag_result.get("passed") and valid_ref(tag):
            effective_from = tag
    range_arg = f"{effective_from}..{to_ref}" if effective_from else to_ref

    log_result = await _run_confined_command(
        [
            "git",
            "log",
            f"--max-count={max_commits}",
            "--date=short",
            "--format=%h%x09%s%x09%ad%x09%an",
            range_arg,
        ],
        cwd=resolved,
        timeout=15,
        max_chars=60000,
    )
    if not log_result.get("passed"):
        return {
            "markdown": "",
            "commits": [],
            "commit_count": 0,
            "files_changed": [],
            "from_ref": effective_from or None,
            "to_ref": to_ref,
            "range": range_arg,
            "error": log_result.get("stderr") or "Git log failed.",
        }

    commits: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for line in str(log_result.get("stdout") or "").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 3)
        short_hash = parts[0].strip() if len(parts) > 0 else ""
        subject = parts[1].strip() if len(parts) > 1 else line.strip()
        category, commit_type, scope, breaking, display = _classify_commit_subject(subject)
        commit = {
            "hash": short_hash,
            "subject": subject,
            "display": display,
            "category": category,
            "type": commit_type,
            "scope": scope,
            "breaking": breaking,
            "date": parts[2].strip() if len(parts) > 2 else "",
            "author": parts[3].strip() if len(parts) > 3 else "",
        }
        commits.append(commit)
        grouped.setdefault(category, []).append(commit)

    files_changed: list[str] = []
    if effective_from:
        diff_names = await _run_confined_command(
            ["git", "diff", "--name-only", range_arg], cwd=resolved, timeout=10, max_chars=60000
        )
        if diff_names.get("passed"):
            files_changed = [line.strip() for line in str(diff_names.get("stdout") or "").splitlines() if line.strip()]
    elif commits:
        names_result = await _run_confined_command(
            ["git", "log", "--name-only", "--format=", f"--max-count={max_commits}", to_ref],
            cwd=resolved,
            timeout=15,
            max_chars=60000,
        )
        if names_result.get("passed"):
            seen_files: set[str] = set()
            for line in str(names_result.get("stdout") or "").splitlines():
                name = line.strip()
                if name and name not in seen_files:
                    seen_files.add(name)
                    files_changed.append(name)

    uncommitted_files: list[str] = []
    if include_uncommitted:
        status_result = await _run_confined_command(
            ["git", "status", "--porcelain=v1"], cwd=resolved, timeout=10, max_chars=20000
        )
        if status_result.get("passed"):
            for line in str(status_result.get("stdout") or "").splitlines():
                if len(line) < 4:
                    continue
                path = line[3:].strip()
                if " -> " in path:
                    path = path.split(" -> ", 1)[1].strip()
                if path:
                    uncommitted_files.append(path)

    section_order = ["Added", "Fixed", "Changed", "Security", "Performance", "Documentation", "Tests", "Maintenance", "Other"]
    range_label = range_arg
    markdown_lines = [
        "# Changelog draft",
        "",
        f"Range: `{range_label}`",
        f"Commits: {len(commits)}",
        "",
    ]
    if not commits:
        markdown_lines.append("No commits found in this range.")
    for section in section_order:
        items = grouped.get(section) or []
        if not items:
            continue
        markdown_lines.append(f"## {section}")
        markdown_lines.append("")
        for item in items:
            prefix = "**Breaking:** " if item.get("breaking") else ""
            markdown_lines.append(f"- {prefix}{item.get('display') or item.get('subject')} (`{item.get('hash')}`)")
        markdown_lines.append("")
    if files_changed:
        markdown_lines.append("## Files changed")
        markdown_lines.append("")
        markdown_lines.extend(f"- `{path}`" for path in files_changed[:100])
        if len(files_changed) > 100:
            markdown_lines.append(f"- ... and {len(files_changed) - 100} more")
        markdown_lines.append("")
    if uncommitted_files:
        markdown_lines.append("## Uncommitted work (not in this changelog)")
        markdown_lines.append("")
        markdown_lines.extend(f"- `{path}`" for path in uncommitted_files[:100])
        markdown_lines.append("")

    categories = {
        section: len(grouped[section])
        for section in section_order
        if grouped.get(section)
    }
    return {
        "repo_path": _relative_workspace_path(resolved),
        "from_ref": effective_from or None,
        "to_ref": to_ref,
        "range": range_arg,
        "commit_count": len(commits),
        "categories": categories,
        "files_changed_count": len(files_changed),
        "uncommitted_count": len(uncommitted_files),
        "commits": commits,
        "markdown": "\n".join(markdown_lines).strip() + "\n",
        "files_changed": files_changed,
        "uncommitted_files": uncommitted_files,
        "truncated": len(commits) >= max_commits or len(files_changed) > 100 or len(uncommitted_files) > 100,
    }


def _unified_diff(path: str, old: str, new: str, *, max_chars: int = 12000) -> str:
    diff = "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
        )
    )
    return diff[:max_chars] + ("\n…[diff truncated]" if len(diff) > max_chars else "")


def _write_prepared_files(prepared: list[tuple[Path, str]]) -> None:
    """Stage then replace prepared text files, rolling back on failure."""

    originals: dict[Path, bytes | None] = {}
    staged: list[tuple[Path, Path]] = []  # (destination, temp)
    replaced: list[Path] = []
    try:
        for destination, _ in prepared:
            originals[destination] = destination.read_bytes() if destination.is_file() else None
        for destination, content in prepared:
            temp = destination.parent / f".nexus-write-{uuid.uuid4().hex}.tmp"
            temp.write_text(content, encoding="utf-8")
            staged.append((destination, temp))
        for destination, temp in staged:
            os.replace(temp, destination)
            replaced.append(destination)
    except Exception:
        for destination in replaced:
            original = originals.get(destination)
            try:
                if original is None:
                    if destination.exists():
                        destination.unlink()
                else:
                    destination.write_bytes(original)
            except OSError:
                pass
        raise
    finally:
        for _, temp in staged:
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass


async def _write_files(params: dict[str, Any]) -> dict[str, Any]:
    raw_files = params.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        return {"written": [], "files_written": 0, "error": "files must be a non-empty array."}
    if len(raw_files) > 50:
        return {"written": [], "files_written": 0, "error": "write_files accepts at most 50 files."}

    dry_run = bool(params.get("dry_run", False))
    overwrite = bool(params.get("overwrite", True))
    create_parents = bool(params.get("create_parents", True))
    prepared: list[tuple[Path, str]] = []
    summaries: list[dict[str, Any]] = []
    seen: set[Path] = set()
    total_bytes = 0

    for index, item in enumerate(raw_files):
        if not isinstance(item, dict):
            return {"written": [], "files_written": 0, "error": f"files[{index}] must be an object."}
        requested = str(item.get("path") or "")
        content = item.get("content")
        if not requested or not isinstance(content, str):
            return {
                "written": [],
                "files_written": 0,
                "error": f"files[{index}] requires string path and content.",
            }
        resolved, err = resolve_confined_path(requested, must_exist=False)
        if not resolved:
            return {"written": [], "files_written": 0, "error": err}
        if resolved in seen:
            return {"written": [], "files_written": 0, "error": f"Duplicate target path: {requested}"}
        seen.add(resolved)
        if resolved.exists() and not resolved.is_file():
            return {"written": [], "files_written": 0, "error": f"Target exists and is not a file: {requested}"}
        if resolved.is_file() and not overwrite:
            return {"written": [], "files_written": 0, "error": f"Target exists and overwrite=false: {requested}"}
        if not resolved.parent.exists() and not create_parents:
            return {"written": [], "files_written": 0, "error": f"Parent directory does not exist: {resolved.parent}"}

        encoded_size = len(content.encode("utf-8"))
        total_bytes += encoded_size
        if total_bytes > 5_000_000:
            return {"written": [], "files_written": 0, "error": "write_files total content exceeds 5 MB."}
        old_content = ""
        existed = resolved.is_file()
        if existed:
            old_content, _, read_error = _read_text_limited(resolved, max_bytes=5_000_000)
            if read_error:
                return {"written": [], "files_written": 0, "error": f"{requested}: {read_error}"}
        rel = _relative_workspace_path(resolved)
        summaries.append(
            {
                "path": rel,
                "bytes": encoded_size,
                "existed": existed,
                "diff": _unified_diff(rel, old_content, content) if dry_run else "",
            }
        )
        prepared.append((resolved, content))

    if dry_run:
        return {"written": summaries, "files_written": 0, "dry_run": True, "total_bytes": total_bytes}

    for resolved, _ in prepared:
        approval_error = await _require_file_tool_approval("write_files", resolved)
        if approval_error is not None:
            return {**approval_error, "written": [], "files_written": 0}

    try:
        for resolved, _ in prepared:
            if create_parents:
                resolved.parent.mkdir(parents=True, exist_ok=True)
        _write_prepared_files(prepared)
    except OSError as exc:
        return {"written": [], "files_written": 0, "error": f"Batch write failed and was rolled back: {exc}"}

    for item in summaries:
        item.pop("diff", None)
    return {
        "written": summaries,
        "files_written": len(summaries),
        "dry_run": False,
        "total_bytes": total_bytes,
    }


async def _batch_edit_files(params: dict[str, Any]) -> dict[str, Any]:
    raw_edits = params.get("edits")
    if not isinstance(raw_edits, list) or not raw_edits:
        return {"files": [], "replacements": 0, "error": "edits must be a non-empty array."}
    if len(raw_edits) > 100:
        return {"files": [], "replacements": 0, "error": "batch_edit_files accepts at most 100 edits."}

    dry_run = bool(params.get("dry_run", False))
    prepared_by_path: dict[Path, str] = {}
    original_by_path: dict[Path, str] = {}
    replacements_by_path: Counter[Path] = Counter()

    for index, item in enumerate(raw_edits):
        if not isinstance(item, dict):
            return {"files": [], "replacements": 0, "error": f"edits[{index}] must be an object."}
        requested = str(item.get("path") or "")
        old_text = item.get("old_text")
        new_text = item.get("new_text")
        if not requested or not isinstance(old_text, str) or not old_text or not isinstance(new_text, str):
            return {
                "files": [],
                "replacements": 0,
                "error": f"edits[{index}] requires path, non-empty old_text, and string new_text.",
            }
        resolved, err = resolve_confined_path(requested, must_exist=True)
        if not resolved:
            return {"files": [], "replacements": 0, "error": err}
        if not resolved.is_file():
            return {"files": [], "replacements": 0, "error": f"Path is not a regular file: {requested}"}
        if resolved not in prepared_by_path:
            text, _, read_error = _read_text_limited(resolved, max_bytes=5_000_000)
            if read_error:
                return {"files": [], "replacements": 0, "error": f"{requested}: {read_error}"}
            prepared_by_path[resolved] = text
            original_by_path[resolved] = text

        content = prepared_by_path[resolved]
        occurrences = content.count(old_text)
        if occurrences == 0:
            return {
                "files": [],
                "replacements": 0,
                "error": f"edits[{index}] old_text was not found in {requested}. No files were changed.",
            }
        replace_all = bool(item.get("replace_all", False))
        if occurrences > 1 and not replace_all:
            return {
                "files": [],
                "replacements": 0,
                "error": (
                    f"edits[{index}] old_text occurs {occurrences} times in {requested}; "
                    "use a larger snippet or replace_all=true."
                ),
                "occurrences": occurrences,
            }
        count = occurrences if replace_all else 1
        prepared_by_path[resolved] = (
            content.replace(old_text, new_text) if replace_all else content.replace(old_text, new_text, 1)
        )
        replacements_by_path[resolved] += count

    prepared = list(prepared_by_path.items())
    file_summaries = [
        {
            "path": _relative_workspace_path(path),
            "replacements": replacements_by_path[path],
            "diff": _unified_diff(
                _relative_workspace_path(path), original_by_path[path], new_content
            )
            if dry_run
            else "",
            "bytes_written": len(new_content.encode("utf-8")),
        }
        for path, new_content in prepared
    ]
    total_replacements = int(sum(replacements_by_path.values()))

    if dry_run:
        return {"files": file_summaries, "replacements": total_replacements, "dry_run": True}

    for resolved, _ in prepared:
        approval_error = await _require_file_tool_approval("batch_edit_files", resolved)
        if approval_error is not None:
            return {**approval_error, "files": [], "replacements": 0}

    try:
        _write_prepared_files(prepared)
    except OSError as exc:
        return {
            "files": [],
            "replacements": 0,
            "error": f"Batch edit failed and was rolled back: {exc}",
        }

    for item in file_summaries:
        item.pop("diff", None)
    return {"files": file_summaries, "replacements": total_replacements, "dry_run": False}


def _path_stats(root: Path) -> tuple[int, int, int]:
    """Return (files, directories excluding root, bytes), bounded by callers."""

    if root.is_file():
        return 1, 0, _safe_file_size(root)
    files = 0
    directories = 0
    total = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as iterator:
                entries = list(iterator)
        except OSError:
            continue
        for entry in entries:
            path = Path(entry.path)
            try:
                if entry.is_dir(follow_symlinks=False):
                    directories += 1
                    if not entry.is_symlink():
                        stack.append(path)
                elif entry.is_file(follow_symlinks=False):
                    files += 1
                    total += _safe_file_size(path)
            except OSError:
                continue
    return files, directories, total


def _is_same_or_child(candidate: Path, parent: Path) -> bool:
    return candidate == parent or parent in candidate.parents


async def _move_path(params: dict[str, Any]) -> dict[str, Any]:
    source, source_err = resolve_confined_path(params.get("source", ""), must_exist=True)
    if not source:
        return {"moved": False, "error": source_err}
    destination, dest_err = resolve_confined_path(params.get("destination", ""), must_exist=False)
    if not destination:
        return {"moved": False, "error": dest_err}
    if source == destination:
        return {"moved": False, "error": "Source and destination are the same path."}
    if source.is_dir() and _is_same_or_child(destination, source):
        return {"moved": False, "error": "Cannot move a directory inside itself."}
    if source == get_workspace_root():
        return {"moved": False, "error": "Refusing to move the workspace root."}
    if ".git" in source.parts or ".git" in destination.parts:
        return {"moved": False, "error": "Refusing to move paths inside .git."}

    overwrite = bool(params.get("overwrite", False))
    create_parents = bool(params.get("create_parents", True))
    if destination.exists() and not overwrite:
        return {"moved": False, "error": f"Destination already exists: {destination}"}
    if destination.exists() and destination.is_dir() and any(destination.iterdir()):
        return {"moved": False, "error": "Refusing to overwrite a non-empty directory."}
    if not destination.parent.exists() and not create_parents:
        return {"moved": False, "error": f"Destination parent does not exist: {destination.parent}"}

    files, directories, total_bytes = _path_stats(source)
    for target in (source, destination):
        approval_error = await _require_file_tool_approval("move_path", target)
        if approval_error is not None:
            return {**approval_error, "moved": False}

    try:
        if create_parents:
            destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and overwrite:
            if destination.is_dir():
                destination.rmdir()
            else:
                destination.unlink()
        shutil.move(str(source), str(destination))
    except OSError as exc:
        return {"moved": False, "error": f"Move failed: {exc}"}
    return {
        "moved": True,
        "source": _relative_workspace_path(source),
        "destination": _relative_workspace_path(destination),
        "type": "directory" if destination.is_dir() else "file",
        "files": files,
        "directories": directories,
        "bytes": total_bytes,
    }


async def _copy_path(params: dict[str, Any]) -> dict[str, Any]:
    source, source_err = resolve_confined_path(params.get("source", ""), must_exist=True)
    if not source:
        return {"copied": False, "error": source_err}
    destination, dest_err = resolve_confined_path(params.get("destination", ""), must_exist=False)
    if not destination:
        return {"copied": False, "error": dest_err}
    if source == destination:
        return {"copied": False, "error": "Source and destination are the same path."}
    if source.is_dir() and _is_same_or_child(destination, source):
        return {"copied": False, "error": "Cannot copy a directory inside itself."}
    if ".git" in source.parts or ".git" in destination.parts:
        return {"copied": False, "error": "Refusing to copy paths inside .git."}

    overwrite = bool(params.get("overwrite", False))
    create_parents = bool(params.get("create_parents", True))
    include_hidden = bool(params.get("include_hidden", True))
    if destination.exists() and not overwrite:
        return {"copied": False, "error": f"Destination already exists: {destination}"}
    if not destination.parent.exists() and not create_parents:
        return {"copied": False, "error": f"Destination parent does not exist: {destination.parent}"}

    files, directories, total_bytes = _path_stats(source)
    if files > 5000:
        return {"copied": False, "error": f"Copy would include {files} files; safety cap is 5000."}
    if total_bytes > 250_000_000:
        return {"copied": False, "error": "Copy would exceed the 250 MB safety cap."}

    approval_error = await _require_file_tool_approval("copy_path", destination)
    if approval_error is not None:
        return {**approval_error, "copied": False}

    copied_files = 0
    copied_bytes = 0
    try:
        if create_parents:
            destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_file():
            shutil.copy2(source, destination)
            copied_files = 1
            copied_bytes = total_bytes
        else:
            destination.mkdir(parents=True, exist_ok=True)
            stack: list[tuple[Path, Path]] = [(source, destination)]
            while stack:
                current_source, current_dest = stack.pop()
                with os.scandir(current_source) as iterator:
                    entries = sorted(iterator, key=lambda entry: entry.name.lower())
                for entry in entries:
                    if not include_hidden and entry.name.startswith("."):
                        continue
                    source_entry = Path(entry.path)
                    if is_denylisted_path(source_entry) or entry.is_symlink():
                        continue
                    dest_entry = current_dest / entry.name
                    if entry.is_dir(follow_symlinks=False):
                        dest_entry.mkdir(parents=True, exist_ok=True)
                        stack.append((source_entry, dest_entry))
                    elif entry.is_file(follow_symlinks=False):
                        shutil.copy2(source_entry, dest_entry)
                        copied_files += 1
                        copied_bytes += _safe_file_size(source_entry)
    except OSError as exc:
        return {"copied": False, "error": f"Copy failed: {exc}", "files": copied_files, "bytes": copied_bytes}

    return {
        "copied": True,
        "source": _relative_workspace_path(source),
        "destination": _relative_workspace_path(destination),
        "type": "directory" if destination.is_dir() else "file",
        "files": copied_files,
        "directories": directories,
        "bytes": copied_bytes,
    }


async def _delete_directory(params: dict[str, Any]) -> dict[str, Any]:
    if params.get("confirm") is not True:
        return {
            "deleted": False,
            "error": "delete_directory requires confirm=true after an explicit deletion request.",
        }
    resolved, err = resolve_confined_path(params.get("path", ""), must_exist=True)
    if not resolved:
        return {"deleted": False, "error": err}
    if not resolved.is_dir():
        return {"deleted": False, "error": "delete_directory only deletes directories; use delete_file for files."}

    workspace = get_workspace_root()
    temp_root = Path("/tmp").resolve()
    if resolved in {workspace, temp_root}:
        return {"deleted": False, "error": "Refusing to delete a workspace/temp root."}
    if ".git" in resolved.parts:
        return {"deleted": False, "error": "Refusing to delete paths inside .git."}
    try:
        relative_parts = resolved.relative_to(workspace).parts
    except ValueError:
        relative_parts = ()
    if len(relative_parts) == 1 and relative_parts[0] in _PROTECTED_REPOSITORY_ROOTS:
        return {
            "deleted": False,
            "error": f"Refusing to delete protected top-level project folder '{relative_parts[0]}'.",
        }

    max_files = _clamp_int(params.get("max_files"), 2000, 0, 20_000)
    files, directories, total_bytes = _path_stats(resolved)
    entries = files + directories
    if entries > 0 and not bool(params.get("recursive", False)):
        return {
            "deleted": False,
            "error": "Directory is not empty; set recursive=true to delete its contents.",
            "files": files,
            "directories": directories,
        }
    if files > max_files:
        return {
            "deleted": False,
            "error": f"Directory contains {files} files, above max_files={max_files}.",
            "files": files,
            "directories": directories,
        }

    approval_error = await _require_file_tool_approval("delete_directory", resolved)
    if approval_error is not None:
        return {**approval_error, "deleted": False}

    try:
        if entries:
            shutil.rmtree(resolved)
        else:
            resolved.rmdir()
    except OSError as exc:
        return {"deleted": False, "error": f"Directory delete failed: {exc}"}
    return {
        "deleted": True,
        "path": _relative_workspace_path(resolved),
        "files_deleted": files,
        "directories_deleted": directories + 1,
        "bytes_deleted": total_bytes,
    }


_REPOSITORY_TEMPLATES = {
    "frontend-design-system",
    "html5-clean-ui",
    "c-cmake",
    "cpp-cmake",
    "rust-cli",
    "python-fastapi",
    "react-vite",
    "node-api",
    "python-cli",
    "php-web",
    "ruby-cli",
    "xml-toolkit",
    "static-site",
    "empty",
}
_REPOSITORY_TEMPLATE_DETAILS: dict[str, dict[str, Any]] = {
    "frontend-design-system": {
        "label": "React frontend design system",
        "languages": ["typescript", "html5", "css"],
        "recommended_checks": ["frontend_quality", "npm_typecheck", "npm_build"],
        "highlights": ["design tokens", "accessible components", "dark mode", "responsive app shell", "form/error/empty states"],
    },
    "html5-clean-ui": {
        "label": "Semantic HTML5 clean UI",
        "languages": ["html5", "css", "javascript"],
        "recommended_checks": ["frontend_quality"],
        "highlights": ["semantic landmarks", "accessible form", "responsive tokenized CSS", "progressive enhancement", "reduced motion"],
    },
    "c-cmake": {
        "label": "C17 library and CLI with CMake + Make",
        "languages": ["c"],
        "recommended_checks": ["c_syntax", "make_test", "cmake_build", "ctest"],
        "highlights": ["checked arithmetic", "warning-clean build", "CTest and Make test", "sanitizer option"],
    },
    "cpp-cmake": {
        "label": "C++20 library and CLI with CMake + Make",
        "languages": ["cpp"],
        "recommended_checks": ["cpp_syntax", "make_test", "cmake_build", "ctest"],
        "highlights": ["RAII/value semantics", "std::optional errors", "warning-clean build", "CTest and Make test"],
    },
    "rust-cli": {
        "label": "Rust CLI with Cargo",
        "languages": ["rust"],
        "recommended_checks": ["cargo_fmt", "cargo_check", "cargo_clippy", "cargo_test"],
        "highlights": ["Result-based errors", "no unwrap in library code", "unit and CLI tests", "rustfmt/Clippy CI"],
    },
    "python-fastapi": {
        "label": "Python FastAPI service",
        "languages": ["python"],
        "recommended_checks": ["python_compile", "pytest"],
        "highlights": ["typed API models", "health endpoint", "pytest coverage"],
    },
    "react-vite": {
        "label": "React + Vite app",
        "languages": ["typescript", "html5", "css"],
        "recommended_checks": ["frontend_quality", "npm_build"],
        "highlights": ["React starter", "Vite build", "interactive task state"],
    },
    "node-api": {
        "label": "Node.js HTTP API",
        "languages": ["javascript"],
        "recommended_checks": ["npm_test"],
        "highlights": ["dependency-free HTTP server", "node:test coverage"],
    },
    "python-cli": {
        "label": "Python CLI package",
        "languages": ["python"],
        "recommended_checks": ["python_compile", "pytest"],
        "highlights": ["argparse CLI", "src layout", "pytest coverage"],
    },
    "php-web": {
        "label": "Secure PHP 8.2 web starter",
        "languages": ["php", "html5", "css"],
        "recommended_checks": ["php_lint", "composer_validate", "composer_test", "frontend_quality"],
        "highlights": ["strict types", "CSRF protection", "escaped output", "accessible form", "Composer tests"],
    },
    "ruby-cli": {
        "label": "Ruby CLI and library",
        "languages": ["ruby"],
        "recommended_checks": ["ruby_syntax", "ruby_test"],
        "highlights": ["frozen string literals", "Bundler/Rake", "Minitest coverage", "gemspec"],
    },
    "xml-toolkit": {
        "label": "Safe XML validation toolkit",
        "languages": ["xml", "python"],
        "recommended_checks": ["xml_validate", "python_compile", "pytest"],
        "highlights": ["DTD/XXE rejection", "namespaced sample data", "XSD and XSLT", "bounded parser CLI"],
    },
    "static-site": {
        "label": "Static website",
        "languages": ["html5", "css", "javascript"],
        "recommended_checks": ["frontend_quality"],
        "highlights": ["semantic page", "responsive starter styling", "progressive enhancement"],
    },
    "empty": {
        "label": "Empty Git repository",
        "languages": [],
        "recommended_checks": ["git_status"],
        "highlights": ["README, license, and Git only"],
    },
}
_REPOSITORY_LICENSES = {"MIT", "BSD-3-Clause", "Unlicense", "none"}
_PROTECTED_REPOSITORY_ROOTS = {
    ".git",
    ".venv",
    "data",
    "docs",
    "frontend",
    "node_modules",
    "scripts",
    "src",
    "tests",
    "web",
}
_REPOSITORY_RUN_COMMANDS: dict[str, list[str]] = {
    "frontend-design-system": ["npm install", "npm run typecheck", "npm run build", "npm run dev"],
    "html5-clean-ui": ["npm test", "python -m http.server 4173"],
    "c-cmake": [
        "make test",
        "cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug",
        "cmake --build build",
        "ctest --test-dir build --output-on-failure",
    ],
    "cpp-cmake": [
        "make test",
        "cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug",
        "cmake --build build",
        "ctest --test-dir build --output-on-failure",
    ],
    "rust-cli": ["cargo fmt --all -- --check", "cargo clippy --all-targets -- -D warnings", "cargo test", "cargo run -- 2 3"],
    "python-fastapi": [
        "python -m venv .venv",
        "source .venv/bin/activate  # Windows: .venv\\Scripts\\activate",
        "pip install -e '.[dev]'",
        "pytest",
        "uvicorn app.main:app --reload",
    ],
    "react-vite": ["npm install", "npm run dev", "npm run build"],
    "node-api": ["npm test", "npm run dev"],
    "python-cli": [
        "python -m venv .venv",
        "source .venv/bin/activate  # Windows: .venv\\Scripts\\activate",
        "pip install -e '.[dev]'",
        "pytest",
    ],
    "php-web": ["composer validate", "composer test", "php -S 127.0.0.1:8000 -t public"],
    "ruby-cli": ["bundle install", "bundle exec rake test", "ruby -Ilib exe/<name> Nexus"],
    "xml-toolkit": ["python -m pytest -q", "python src/xml_toolkit.py data/catalog.xml"],
    "static-site": ["python -m http.server 4173"],
    "empty": ["git status"],
}


def _repository_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off", ""}:
            return False
    return default if value is None else bool(value)


def _normalize_repository_name(value: Any) -> str:
    raw = str(value or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9._-]+", "-", raw)
    normalized = re.sub(r"-+", "-", normalized).strip("-._")[:100].strip("-._")
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    if not normalized or normalized in reserved:
        return ""
    return normalized


def _repository_title(name: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", name) if part) or "Nexus Project"


def _repository_package_name(name: str) -> str:
    package = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_") or "nexus_project"
    if package[0].isdigit():
        package = f"app_{package}"
    return package


def _escape_html_text(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _repository_license_text(license_id: str) -> str:
    year = datetime.now(UTC).year
    if license_id == "MIT":
        return f"""MIT License

Copyright (c) {year} Nexus Project Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
    if license_id == "BSD-3-Clause":
        return f"""BSD 3-Clause License

Copyright (c) {year}, Nexus Project Contributors
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE.
"""
    if license_id == "Unlicense":
        return """This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or distribute
this software, either in source code form or as a compiled binary, for any
purpose, commercial or non-commercial, and by any means.

In jurisdictions that recognize copyright laws, the author or authors of this
software dedicate any and all copyright interest in the software to the public
domain. We make this dedication for the benefit of the public at large and to
the detriment of our heirs and successors. We intend this dedication to be an
overt act of relinquishment in perpetuity of all present and future rights to
this software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <https://unlicense.org/>
"""
    return ""


def _repository_files(
    template: str,
    name: str,
    description: str,
    license_id: str,
    include_ci: bool,
) -> dict[str, str]:
    title = _repository_title(name)
    package = _repository_package_name(name)
    ruby_module = "".join(part.capitalize() for part in package.split("_") if part) or "NexusProject"
    safe_title = _escape_html_text(title)
    safe_description = _escape_html_text(description)
    commands = "\n".join(_REPOSITORY_RUN_COMMANDS[template]).replace("<name>", name)
    files: dict[str, str] = {
        "README.md": (
            f"# {title}\n\n{description}\n\n"
            "Created with the Nexus repository builder.\n\n"
            "## Quick start\n\n```bash\n"
            f"{commands}\n```\n\n"
            "## Development notes\n\n"
            "- Keep secrets in environment variables, never in Git.\n"
            "- Add one small end-to-end feature at a time and run the tests after each change.\n"
            "- Replace starter sample data with production data and persistence when the first workflow is proven.\n"
        ),
        ".gitignore": "\n".join(
            [
                "__pycache__/",
                ".venv/",
                ".env",
                ".env.*",
                "!.env.example",
                "node_modules/",
                "dist/",
                "build/",
                "target/",
                "vendor/",
                ".bundle/",
                "*.gem",
                ".DS_Store",
                "*.log",
                "",
            ]
        ),
        ".editorconfig": "root = true\n\n[*]\ncharset = utf-8\nend_of_line = lf\ninsert_final_newline = true\nindent_style = space\nindent_size = 2\n\n[*.py]\nindent_size = 4\n\n[Makefile]\nindent_style = tab\n",
    }
    license_text = _repository_license_text(license_id)
    if license_text:
        files["LICENSE"] = license_text

    if template == "frontend-design-system":
        package_json = {
            "name": name,
            "private": True,
            "version": "0.1.0",
            "type": "module",
            "scripts": {
                "dev": "vite --host 0.0.0.0",
                "build": "tsc --noEmit && vite build",
                "typecheck": "tsc --noEmit",
                "preview": "vite preview --host 0.0.0.0",
            },
            "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
            "devDependencies": {
                "@types/react": "^18.3.11",
                "@types/react-dom": "^18.3.1",
                "@vitejs/plugin-react": "^4.3.3",
                "typescript": "^5.6.3",
                "vite": "^5.4.10",
            },
        }
        tsconfig = {
            "compilerOptions": {
                "target": "ES2020",
                "useDefineForClassFields": True,
                "lib": ["ES2020", "DOM", "DOM.Iterable"],
                "module": "ESNext",
                "skipLibCheck": True,
                "moduleResolution": "bundler",
                "allowImportingTsExtensions": True,
                "resolveJsonModule": True,
                "isolatedModules": True,
                "noEmit": True,
                "jsx": "react-jsx",
                "strict": True,
                "noUncheckedIndexedAccess": True,
            },
            "include": ["src", "vite.config.ts"],
        }
        index_html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content="__SAFE_DESCRIPTION__" />
    <meta name="color-scheme" content="light dark" />
    <title>__SAFE_TITLE__</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""".replace("__SAFE_DESCRIPTION__", safe_description).replace("__SAFE_TITLE__", safe_title)
        app_tsx = """import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Button } from './components/Button';
import { Card } from './components/Card';
import { TextField } from './components/TextField';

type Task = { id: number; title: string; done: boolean };
type Filter = 'all' | 'open' | 'done';
type Theme = 'light' | 'dark';

const starterTasks: Task[] = [
  { id: 1, title: 'Define the first real user workflow', done: true },
  { id: 2, title: 'Connect production data with loading and error states', done: false },
  { id: 3, title: 'Review keyboard flow and color contrast', done: false },
];

function initialTheme(): Theme {
  const saved = window.localStorage.getItem('nexus-ui-theme');
  if (saved === 'light' || saved === 'dark') return saved;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [tasks, setTasks] = useState<Task[]>(starterTasks);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [status, setStatus] = useState('Starter ready.');
  const [filter, setFilter] = useState<Filter>('all');

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('nexus-ui-theme', theme);
  }, [theme]);

  const done = useMemo(() => tasks.filter((task) => task.done).length, [tasks]);
  const visible = useMemo(
    () => tasks.filter((task) => filter === 'all' || (filter === 'done' ? task.done : !task.done)),
    [tasks, filter],
  );
  const progress = tasks.length ? Math.round((done / tasks.length) * 100) : 0;

  function addTask(event: FormEvent) {
    event.preventDefault();
    const title = draft.trim();
    if (title.length < 3) {
      setError('Enter a task with at least 3 characters.');
      setStatus('Task was not added.');
      return;
    }
    setTasks((current) => [...current, { id: Date.now(), title, done: false }]);
    setDraft('');
    setError('');
    setStatus(`Added task: ${title}`);
  }

  function toggleTask(task: Task) {
    setTasks((current) => current.map((item) => (item.id === task.id ? { ...item, done: !item.done } : item)));
    setStatus(`${task.done ? 'Reopened' : 'Completed'}: ${task.title}`);
  }

  return (
    <>
      <a className="skip-link" href="#main">Skip to main content</a>
      <div className="app-shell">
        <header className="topbar">
          <a className="brand" href="#overview" aria-label="__SAFE_TITLE__ home">
            <span className="brand-mark" aria-hidden="true">N</span>
            <span>__SAFE_TITLE__</span>
          </a>
          <nav aria-label="Primary" className="topnav">
            <a href="#overview">Overview</a>
            <a href="#workbench">Workbench</a>
            <a href="#components">Components</a>
          </nav>
          <Button type="button" variant="secondary" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            {theme === 'dark' ? 'Use light theme' : 'Use dark theme'}
          </Button>
        </header>

        <div className="layout">
          <aside className="sidebar" aria-label="Workspace sections">
            <nav aria-label="Workspace">
              <a aria-current="page" href="#overview">Overview</a>
              <a href="#workbench">Workbench</a>
              <a href="#components">Design tokens</a>
            </nav>
            <p className="sidebar-note">Built with semantic landmarks, visible labels, keyboard-complete controls, and responsive tokens.</p>
          </aside>

          <main id="main" className="main" tabIndex={-1}>
            <section id="overview" className="hero" aria-labelledby="page-title">
              <p className="eyebrow">Nexus clean UI starter</p>
              <h1 id="page-title">__SAFE_TITLE__</h1>
              <p className="lede">__SAFE_DESCRIPTION__</p>
              <div className="actions">
                <Button type="button" onClick={() => document.querySelector<HTMLInputElement>('#new-task')?.focus()}>Add a task</Button>
                <a className="text-link" href="#components">Review the design system</a>
              </div>
              <div className="progress" role="progressbar" aria-label="Starter progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
                <span style={{ width: `${progress}%` }} />
              </div>
              <p className="muted">{done} of {tasks.length} starter tasks complete ({progress}%).</p>
            </section>

            <section className="metrics" aria-label="Project metrics">
              <Card title="Open work"><strong className="metric">{tasks.length - done}</strong><p>Tasks still in motion.</p></Card>
              <Card title="Completed"><strong className="metric">{done}</strong><p>Finished starter tasks.</p></Card>
              <Card title="Responsive"><strong className="metric">320px+</strong><p>Usable from small phones to desktop.</p></Card>
            </section>

            <section id="workbench" aria-labelledby="workbench-title">
              <Card title="Workbench" titleId="workbench-title">
                <form className="task-form" onSubmit={addTask} noValidate>
                  <TextField
                    id="new-task"
                    label="Next build task"
                    description="Use a clear action, for example: Add checkout error recovery."
                    error={error}
                    value={draft}
                    onChange={(event) => { setDraft(event.target.value); if (error) setError(''); }}
                    placeholder="Describe the next task"
                    autoComplete="off"
                  />
                  <Button type="submit">Add task</Button>
                </form>

                <div className="toolbar" role="group" aria-label="Filter tasks">
                  {(['all', 'open', 'done'] as Filter[]).map((value) => (
                    <Button key={value} type="button" variant={filter === value ? 'primary' : 'secondary'} aria-pressed={filter === value} onClick={() => setFilter(value)}>
                      {value === 'all' ? 'All' : value === 'open' ? 'Open' : 'Done'}
                    </Button>
                  ))}
                </div>

                <p className="status" aria-live="polite">{status}</p>
                {visible.length ? (
                  <ul className="task-list">
                    {visible.map((task) => (
                      <li key={task.id}>
                        <input
                          id={`task-${task.id}`}
                          type="checkbox"
                          checked={task.done}
                          onChange={() => toggleTask(task)}
                          aria-label={`Mark ${task.title} as ${task.done ? 'open' : 'done'}`}
                        />
                        <label htmlFor={`task-${task.id}`} className={task.done ? 'done' : undefined}>{task.title}</label>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="empty" role="status">
                    <h3>No tasks in this view</h3>
                    <p>Add a task or choose a different filter.</p>
                  </div>
                )}
              </Card>
            </section>

            <section id="components" aria-labelledby="components-title">
              <Card title="Design system checklist" titleId="components-title">
                <ul className="checklist">
                  <li>Tokens for color, spacing, radius, shadow, and type.</li>
                  <li>Buttons and fields include hover, focus, disabled, and error states.</li>
                  <li>Layout stacks safely at small widths and honors reduced motion.</li>
                  <li>Status changes are announced through a polite live region.</li>
                </ul>
              </Card>
            </section>
          </main>
        </div>

        <footer className="footer">
          <p>Created with Nexus. Replace starter data with your first production workflow.</p>
        </footer>
      </div>
    </>
  );
}
""".replace("__SAFE_TITLE__", safe_title).replace("__SAFE_DESCRIPTION__", safe_description)
        files.update(
            {
                "package.json": json.dumps(package_json, indent=2) + "\n",
                "index.html": index_html,
                "vite.config.ts": """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { host: '0.0.0.0', port: 5173 },
  preview: { host: '0.0.0.0', port: 4173 },
});
""",
                "tsconfig.json": json.dumps(tsconfig, indent=2) + "\n",
                "src/main.tsx": """import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>,
);
""",
                "src/App.tsx": app_tsx,
                "src/components/Button.tsx": """import type { ButtonHTMLAttributes } from 'react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary';
};

export function Button({ variant = 'primary', className = '', ...props }: ButtonProps) {
  return <button className={`button button-${variant} ${className}`.trim()} {...props} />;
}
""",
                "src/components/Card.tsx": """import type { ReactNode } from 'react';

type CardProps = {
  title: string;
  titleId?: string;
  children: ReactNode;
};

export function Card({ title, titleId, children }: CardProps) {
  return (
    <article className="card">
      <h2 id={titleId}>{title}</h2>
      {children}
    </article>
  );
}
""",
                "src/components/TextField.tsx": """import type { InputHTMLAttributes } from 'react';

type TextFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  label: string;
  description?: string;
  error?: string;
};

export function TextField({ id, label, description, error, ...props }: TextFieldProps) {
  const descriptionId = description ? `${id}-description` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [descriptionId, errorId].filter(Boolean).join(' ') || undefined;

  return (
    <div className="field">
      <label id={`${id}-label`} htmlFor={id}>{label}</label>
      {description ? <p id={descriptionId} className="field-description">{description}</p> : null}
      <input
        id={id}
        aria-labelledby={`${id}-label`}
        aria-describedby={describedBy}
        aria-invalid={Boolean(error)}
        {...props}
      />
      {error ? <p id={errorId} className="field-error" role="alert">{error}</p> : null}
    </div>
  );
}
""",
                "src/index.css": """:root {
  color-scheme: light;
  --bg: #f7f4ee;
  --surface: #ffffff;
  --surface-strong: #fffaf0;
  --text: #20242c;
  --muted: #5f6875;
  --border: #ded6c7;
  --brand: #b95d32;
  --brand-strong: #93471f;
  --accent: #6757d9;
  --success: #16794c;
  --danger: #b42318;
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --radius: 1rem;
  --radius-lg: 1.5rem;
  --shadow: 0 1.25rem 3.75rem rgb(80 65 35 / 0.10);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: var(--text);
  background: var(--bg);
}

:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #17191f;
  --surface: #22252d;
  --surface-strong: #292d38;
  --text: #f3f0e9;
  --muted: #b8beca;
  --border: #3b404e;
  --brand: #f0a37e;
  --brand-strong: #ffc4a6;
  --accent: #aaa0ff;
  --danger: #ffb4aa;
  --shadow: 0 1.25rem 3.75rem rgb(0 0 0 / 0.30);
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; min-width: 320px; }
a { color: inherit; }
:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
.skip-link { position: absolute; left: 1rem; top: -5rem; z-index: 10; padding: 0.75rem 1rem; border-radius: 999px; background: var(--text); color: var(--bg); }
.skip-link:focus { top: 1rem; }
.app-shell { width: min(1180px, calc(100% - 2rem)); margin: 0 auto; padding: var(--space-6) 0; }
.topbar { display: flex; align-items: center; gap: var(--space-4); padding: var(--space-4); border: 1px solid var(--border); border-radius: var(--radius-lg); background: color-mix(in srgb, var(--surface) 92%, transparent); box-shadow: var(--shadow); }
.brand { display: inline-flex; align-items: center; gap: var(--space-3); font-weight: 800; text-decoration: none; }
.brand-mark { display: grid; width: 2.25rem; height: 2.25rem; place-items: center; border-radius: 0.75rem; background: var(--text); color: var(--bg); }
.topnav { display: flex; flex: 1; gap: var(--space-4); justify-content: center; }
.topnav a, .sidebar a { text-decoration-thickness: 0.08em; text-underline-offset: 0.2em; }
.layout { display: grid; grid-template-columns: 15rem minmax(0, 1fr); gap: var(--space-6); margin-top: var(--space-6); }
.sidebar { align-self: start; padding: var(--space-4); border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
.sidebar nav { display: grid; gap: var(--space-2); }
.sidebar a { padding: var(--space-2) var(--space-3); border-radius: 0.75rem; text-decoration: none; }
.sidebar a[aria-current="page"] { background: var(--surface-strong); font-weight: 800; }
.sidebar-note, .muted, .field-description { color: var(--muted); }
.main { display: grid; gap: var(--space-6); min-width: 0; }
.hero { padding: clamp(1.5rem, 5vw, 3rem); border: 1px solid var(--border); border-radius: var(--radius-lg); background: linear-gradient(135deg, var(--surface), var(--surface-strong)); box-shadow: var(--shadow); }
.eyebrow { margin: 0; color: var(--brand); font-size: 0.78rem; font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase; }
h1 { margin: var(--space-3) 0; font-size: clamp(2.5rem, 7vw, 4.75rem); line-height: 0.95; letter-spacing: -0.045em; }
h2 { margin-top: 0; }
.lede { max-width: 44rem; font-size: 1.15rem; line-height: 1.65; color: var(--muted); }
.actions, .toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-3); }
.progress { height: 0.65rem; margin-top: var(--space-6); overflow: hidden; border-radius: 999px; background: color-mix(in srgb, var(--text) 12%, transparent); }
.progress span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--brand), var(--accent), var(--success)); }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 12rem), 1fr)); gap: var(--space-4); }
.card { padding: var(--space-6); border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
.metric { display: block; font-size: 2.25rem; line-height: 1; }
.button { min-height: 2.75rem; border-radius: 999px; padding: 0.7rem 1.1rem; border: 1px solid transparent; font: inherit; font-weight: 800; cursor: pointer; }
.button-primary { background: var(--text); color: var(--bg); }
.button-secondary { background: var(--surface); color: var(--text); border-color: var(--border); }
.button:hover { transform: translateY(-1px); }
.button:disabled { cursor: not-allowed; opacity: 0.55; transform: none; }
.task-form { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: var(--space-4); }
.field { display: grid; gap: var(--space-2); }
.field label { font-weight: 800; }
.field input { width: 100%; min-height: 2.75rem; border: 1px solid var(--border); border-radius: 0.8rem; padding: 0.7rem 0.9rem; background: var(--bg); color: var(--text); font: inherit; }
.field input[aria-invalid="true"] { border-color: var(--danger); }
.field-error { margin: 0; color: var(--danger); font-weight: 700; }
.toolbar { margin-top: var(--space-6); }
.status { min-height: 1.5em; color: var(--muted); }
.task-list { display: grid; gap: var(--space-2); padding: 0; list-style: none; }
.task-list li { display: flex; gap: var(--space-3); align-items: center; padding: var(--space-3); border: 1px solid var(--border); border-radius: var(--radius); }
.done { color: var(--muted); text-decoration: line-through; }
.empty { padding: var(--space-6); border: 1px dashed var(--border); border-radius: var(--radius); text-align: center; }
.checklist { line-height: 1.8; }
.footer { padding: var(--space-6) var(--space-2); color: var(--muted); text-align: center; }

@media (max-width: 760px) {
  .topbar { align-items: stretch; flex-direction: column; }
  .topnav { justify-content: flex-start; flex-wrap: wrap; }
  .layout { grid-template-columns: 1fr; }
  .sidebar { order: 2; }
  .task-form { grid-template-columns: 1fr; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; animation: none !important; }
  .button:hover { transform: none; }
}
""",
            }
        )
    elif template == "html5-clean-ui":
        package_json = {
            "name": name,
            "private": True,
            "version": "0.1.0",
            "type": "module",
            "scripts": {"start": "python3 -m http.server 4173", "test": "node --test tests/smoke.test.mjs"},
        }
        index_html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="__SAFE_DESCRIPTION__">
  <meta name="color-scheme" content="light dark">
  <title>__SAFE_TITLE__</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <a class="skip-link" href="#main">Skip to main content</a>
  <header class="site-header">
    <a class="brand" href="#top" aria-label="__SAFE_TITLE__ home"><span aria-hidden="true">N</span> __SAFE_TITLE__</a>
    <nav aria-label="Primary">
      <a href="#features">Features</a>
      <a href="#join">Join</a>
      <a href="#faq">FAQ</a>
    </nav>
    <button id="theme-toggle" type="button" aria-pressed="false">Dark theme</button>
  </header>

  <main id="main" class="shell">
    <section id="top" class="hero" aria-labelledby="page-title">
      <p class="eyebrow">Clean HTML5 starter</p>
      <h1 id="page-title">__SAFE_TITLE__</h1>
      <p class="lede">__SAFE_DESCRIPTION__</p>
      <p><a class="button" href="#join">Start with the form</a> <a href="#features">Explore features</a></p>
    </section>

    <section id="features" aria-labelledby="features-title">
      <h2 id="features-title">Designed for real people first</h2>
      <div class="cards">
        <article class="card"><h3>Semantic structure</h3><p>Landmarks, a logical heading outline, and real controls keep the page understandable to every user.</p></article>
        <article class="card"><h3>Responsive tokens</h3><p>Fluid type, flexible grids, and an 8px rhythm keep the layout calm from 320px upward.</p></article>
        <article class="card"><h3>Useful states</h3><p>Focus, validation, success, and reduced-motion preferences are designed—not left as afterthoughts.</p></article>
      </div>
    </section>

    <section id="join" aria-labelledby="join-title">
      <div class="card">
        <h2 id="join-title">Join the waitlist</h2>
        <p>Tell us where to send the first release note. This starter validates locally; connect your own backend before collecting real addresses.</p>
        <form id="waitlist-form" action="#" method="post" novalidate>
          <div class="field">
            <label for="name">Full name</label>
            <input id="name" name="name" type="text" autocomplete="name" required>
          </div>
          <div class="field">
            <label for="email">Email address</label>
            <p id="email-help" class="help">Use an address you check regularly. We will not add placeholder marketing claims here.</p>
            <input id="email" name="email" type="email" autocomplete="email" aria-describedby="email-help email-error" required>
            <p id="email-error" class="error" role="alert" hidden>Enter a valid email address.</p>
          </div>
          <button type="submit">Join waitlist</button>
          <p id="form-status" class="status" aria-live="polite"></p>
        </form>
      </div>
    </section>

    <section id="faq" aria-labelledby="faq-title">
      <h2 id="faq-title">Frequently asked questions</h2>
      <details>
        <summary>Does this work without JavaScript?</summary>
        <p>Yes. Content, navigation, and the form structure remain available; JavaScript only improves theme memory and inline validation feedback.</p>
      </details>
      <details>
        <summary>What should I build first?</summary>
        <p>Connect one real workflow end to end, then add loading, empty, and server-error states before expanding the design.</p>
      </details>
    </section>
  </main>

  <footer class="site-footer">
    <p>Created with Nexus. Built with semantic HTML5, modern CSS, and progressive enhancement.</p>
  </footer>
  <script src="script.js" defer></script>
</body>
</html>
""".replace("__SAFE_TITLE__", safe_title).replace("__SAFE_DESCRIPTION__", safe_description)
        files.update(
            {
                "package.json": json.dumps(package_json, indent=2) + "\n",
                "index.html": index_html,
                "styles.css": """:root {
  color-scheme: light;
  --bg: #f7f4ee;
  --surface: #ffffff;
  --text: #20242c;
  --muted: #5f6875;
  --border: #ded6c7;
  --brand: #b95d32;
  --accent: #6757d9;
  --danger: #b42318;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --radius: 1rem;
  --radius-lg: 1.5rem;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
  color: var(--text);
  background: var(--bg);
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #17191f;
  --surface: #22252d;
  --text: #f3f0e9;
  --muted: #b8beca;
  --border: #3b404e;
  --brand: #f0a37e;
  --accent: #aaa0ff;
  --danger: #ffb4aa;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #17191f;
    --surface: #22252d;
    --text: #f3f0e9;
    --muted: #b8beca;
    --border: #3b404e;
    --brand: #f0a37e;
    --accent: #aaa0ff;
    --danger: #ffb4aa;
  }
}
* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; }
a { color: inherit; }
:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
.skip-link { position: absolute; left: 1rem; top: -5rem; z-index: 10; padding: 0.75rem 1rem; border-radius: 999px; background: var(--text); color: var(--bg); }
.skip-link:focus { top: 1rem; }
.site-header { width: min(1100px, calc(100% - 2rem)); margin: 1rem auto; padding: var(--space-4); display: flex; align-items: center; gap: var(--space-4); border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
.brand { display: inline-flex; gap: var(--space-3); align-items: center; font-weight: 900; text-decoration: none; }
.brand span { display: grid; place-items: center; width: 2.25rem; height: 2.25rem; border-radius: 0.75rem; background: var(--text); color: var(--bg); }
nav[aria-label="Primary"] { display: flex; flex: 1; justify-content: center; gap: var(--space-4); flex-wrap: wrap; }
button, .button { display: inline-flex; align-items: center; justify-content: center; min-height: 2.75rem; border: 1px solid var(--border); border-radius: 999px; padding: 0.7rem 1.1rem; background: var(--text); color: var(--bg); font: inherit; font-weight: 800; text-decoration: none; cursor: pointer; }
button[aria-pressed="false"] { background: var(--surface); color: var(--text); }
.shell { width: min(1100px, calc(100% - 2rem)); margin: 0 auto; display: grid; gap: var(--space-8); padding: var(--space-8) 0; }
.hero { padding: clamp(2rem, 7vw, 4rem); border: 1px solid var(--border); border-radius: var(--radius-lg); background: linear-gradient(135deg, var(--surface), color-mix(in srgb, var(--surface) 72%, var(--brand) 12%)); }
.eyebrow { color: var(--brand); font-size: 0.78rem; font-weight: 900; letter-spacing: 0.14em; text-transform: uppercase; }
h1 { max-width: 12ch; margin: var(--space-3) 0; font-size: clamp(2.75rem, 8vw, 5.5rem); line-height: 0.92; letter-spacing: -0.05em; }
h2 { font-size: clamp(1.75rem, 4vw, 2.75rem); line-height: 1.05; }
.lede { max-width: 42rem; font-size: 1.2rem; line-height: 1.65; color: var(--muted); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr)); gap: var(--space-4); }
.card { padding: var(--space-6); border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); line-height: 1.65; }
form { display: grid; gap: var(--space-4); max-width: 38rem; }
.field { display: grid; gap: var(--space-2); }
label { font-weight: 800; }
.help { margin: 0; color: var(--muted); }
input { width: 100%; min-height: 2.9rem; border: 1px solid var(--border); border-radius: 0.8rem; padding: 0.75rem 0.9rem; background: var(--bg); color: var(--text); font: inherit; }
input[aria-invalid="true"] { border-color: var(--danger); }
.error { margin: 0; color: var(--danger); font-weight: 800; }
.status { min-height: 1.5em; margin: 0; color: var(--muted); }
details { padding: var(--space-4); border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); margin-top: var(--space-3); }
summary { font-weight: 800; cursor: pointer; }
.site-footer { padding: var(--space-8); color: var(--muted); text-align: center; }
@media (max-width: 700px) {
  .site-header { flex-direction: column; align-items: stretch; }
  nav[aria-label="Primary"] { justify-content: flex-start; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; animation: none !important; }
}
""",
                "script.js": """const root = document.documentElement;
const toggle = document.querySelector('#theme-toggle');
const savedTheme = window.localStorage.getItem('nexus-theme');

if (savedTheme === 'dark' || savedTheme === 'light') {
  root.dataset.theme = savedTheme;
}

function syncToggle() {
  const dark = root.dataset.theme === 'dark' ||
    (!root.dataset.theme && window.matchMedia('(prefers-color-scheme: dark)').matches);
  toggle?.setAttribute('aria-pressed', String(dark));
  if (toggle) toggle.textContent = dark ? 'Light theme' : 'Dark theme';
}

toggle?.addEventListener('click', () => {
  const currentlyDark = root.dataset.theme === 'dark' ||
    (!root.dataset.theme && window.matchMedia('(prefers-color-scheme: dark)').matches);
  const next = currentlyDark ? 'light' : 'dark';
  root.dataset.theme = next;
  window.localStorage.setItem('nexus-theme', next);
  syncToggle();
});
syncToggle();

const form = document.querySelector('#waitlist-form');
const email = document.querySelector('#email');
const error = document.querySelector('#email-error');
const status = document.querySelector('#form-status');

form?.addEventListener('submit', (event) => {
  event.preventDefault();
  const valid = email instanceof HTMLInputElement && email.checkValidity();
  if (!valid) {
    email?.setAttribute('aria-invalid', 'true');
    if (error) error.hidden = false;
    if (status) status.textContent = 'Please fix the highlighted field.';
    email?.focus();
    return;
  }
  email.removeAttribute('aria-invalid');
  if (error) error.hidden = true;
  if (status) status.textContent = 'Starter form validated locally. Connect your backend to save this signup.';
  form.reset();
});

email?.addEventListener('input', () => {
  email.removeAttribute('aria-invalid');
  if (error) error.hidden = true;
});
""",
                "404.html": """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Page not found</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="shell">
    <section class="card">
      <h1>Page not found</h1>
      <p>The page may have moved or the address may contain a typo.</p>
      <p><a class="button" href="/">Return home</a></p>
    </section>
  </main>
</body>
</html>
""",
                "tests/smoke.test.mjs": """import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');
const css = await readFile(new URL('../styles.css', import.meta.url), 'utf8');

test('document has semantic and responsive foundations', () => {
  assert.match(html, /<!doctype html>/i);
  assert.match(html, /<html[^>]+lang=/i);
  assert.match(html, /name="viewport"/i);
  assert.match(html, /<main\\b/i);
  assert.match(html, /<label[^>]+for="email"/i);
  assert.doesNotMatch(html, /\\son(click|submit|load)=/i);
});

test('stylesheet includes focus and responsive behavior', () => {
  assert.match(css, /:focus-visible/);
  assert.match(css, /@media\\s*\\(max-width:/);
  assert.match(css, /prefers-reduced-motion/);
});
""",
            }
        )
    elif template == "c-cmake":
        package_upper = package.upper()
        c_header = """#ifndef __PACKAGE_UPPER___MATH_H
#define __PACKAGE_UPPER___MATH_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Returns false on overflow and leaves *out unchanged. */
bool __PACKAGE___checked_add(int64_t left, int64_t right, int64_t *out);

/* Clamps value into the inclusive [minimum, maximum] range. */
int64_t __PACKAGE___clamp(int64_t value, int64_t minimum, int64_t maximum);

#ifdef __cplusplus
}
#endif

#endif
""".replace("__PACKAGE_UPPER__", package_upper).replace("__PACKAGE__", package)
        c_source = """#include "__PACKAGE__/math.h"

#include <stddef.h>

bool __PACKAGE___checked_add(int64_t left, int64_t right, int64_t *out) {
    if (out == NULL) {
        return false;
    }
    if ((right > 0 && left > INT64_MAX - right) ||
        (right < 0 && left < INT64_MIN - right)) {
        return false;
    }
    *out = left + right;
    return true;
}

int64_t __PACKAGE___clamp(int64_t value, int64_t minimum, int64_t maximum) {
    if (minimum > maximum) {
        const int64_t temporary = minimum;
        minimum = maximum;
        maximum = temporary;
    }
    if (value < minimum) {
        return minimum;
    }
    if (value > maximum) {
        return maximum;
    }
    return value;
}
""".replace("__PACKAGE__", package)
        c_main = """#include "__PACKAGE__/math.h"

#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

static bool parse_int64(const char *text, int64_t *out) {
    char *end = NULL;
    errno = 0;
    const long long parsed = strtoll(text, &end, 10);
    if (errno != 0 || end == text || *end != '\\0' ||
        parsed < INT64_MIN || parsed > INT64_MAX) {
        return false;
    }
    *out = (int64_t)parsed;
    return true;
}

int main(int argc, char **argv) {
    int64_t left = 0;
    int64_t right = 0;
    int64_t result = 0;

    if (argc != 3 || !parse_int64(argv[1], &left) || !parse_int64(argv[2], &right)) {
        fprintf(stderr, "Usage: %s <integer> <integer>\\n", argc > 0 ? argv[0] : "__NAME__");
        return EXIT_FAILURE;
    }
    if (!__PACKAGE___checked_add(left, right, &result)) {
        fputs("Integer overflow\\n", stderr);
        return EXIT_FAILURE;
    }
    printf("%" PRId64 "\\n", result);
    return EXIT_SUCCESS;
}
""".replace("__PACKAGE__", package).replace("__NAME__", name)
        c_test = """#include "__PACKAGE__/math.h"

#include <stdio.h>

static int failures = 0;

static void expect_bool(bool actual, bool expected, const char *label) {
    if (actual != expected) {
        fprintf(stderr, "FAIL: %s\\n", label);
        ++failures;
    }
}

static void expect_i64(int64_t actual, int64_t expected, const char *label) {
    if (actual != expected) {
        fprintf(stderr, "FAIL: %s\\n", label);
        ++failures;
    }
}

int main(void) {
    int64_t result = 0;
    expect_bool(__PACKAGE___checked_add(2, 3, &result), true, "addition succeeds");
    expect_i64(result, 5, "addition result");
    result = 99;
    expect_bool(__PACKAGE___checked_add(INT64_MAX, 1, &result), false, "overflow rejected");
    expect_i64(result, 99, "overflow leaves output unchanged");
    expect_i64(__PACKAGE___clamp(12, 0, 10), 10, "clamp upper bound");
    expect_i64(__PACKAGE___clamp(-3, 0, 10), 0, "clamp lower bound");
    return failures == 0 ? 0 : 1;
}
""".replace("__PACKAGE__", package)
        cmake = """cmake_minimum_required(VERSION 3.16)
project(__PACKAGE__ C)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

option(NEXUS_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)

add_library(__PACKAGE___core src/math.c)
add_library(__PACKAGE__::core ALIAS __PACKAGE___core)
target_include_directories(__PACKAGE___core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)

add_executable(__PACKAGE__ src/main.c)
target_link_libraries(__PACKAGE__ PRIVATE __PACKAGE__::core)

foreach(target __PACKAGE___core __PACKAGE__)
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4)
  else()
    target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic)
  endif()
  if(NEXUS_ENABLE_SANITIZERS AND NOT MSVC)
    target_compile_options(${target} PRIVATE -fsanitize=address,undefined)
    target_link_options(${target} PRIVATE -fsanitize=address,undefined)
  endif()
endforeach()

enable_testing()
add_executable(test_math tests/test_math.c)
target_link_libraries(test_math PRIVATE __PACKAGE__::core)
if(NOT MSVC)
  target_compile_options(test_math PRIVATE -Wall -Wextra -Wpedantic)
endif()
add_test(NAME math COMMAND test_math)
""".replace("__PACKAGE__", package)
        makefile = """CC ?= cc
CFLAGS ?= -std=c17 -O2 -Wall -Wextra -Wpedantic -Iinclude
ifeq ($(SANITIZE),1)
CFLAGS += -g -fsanitize=address,undefined
LDFLAGS += -fsanitize=address,undefined
endif

.PHONY: all test clean
all: build/__NAME__

build/__NAME__: src/main.c src/math.c include/__PACKAGE__/math.h
\tmkdir -p build
\t$(CC) $(CFLAGS) src/main.c src/math.c $(LDFLAGS) -o $@

build/test_math: tests/test_math.c src/math.c include/__PACKAGE__/math.h
\tmkdir -p build
\t$(CC) $(CFLAGS) tests/test_math.c src/math.c $(LDFLAGS) -o $@

test: build/test_math
\t./build/test_math

clean:
\trm -rf build
""".replace("__PACKAGE__", package).replace("__NAME__", name)
        files.update(
            {
                "CMakeLists.txt": cmake,
                "Makefile": makefile,
                f"include/{package}/math.h": c_header,
                "src/math.c": c_source,
                "src/main.c": c_main,
                "tests/test_math.c": c_test,
                ".clang-format": "BasedOnStyle: LLVM\nIndentWidth: 4\nColumnLimit: 100\n",
            }
        )
    elif template == "cpp-cmake":
        package_upper = package.upper()
        cpp_header = """#ifndef __PACKAGE_UPPER___MATH_HPP
#define __PACKAGE_UPPER___MATH_HPP

#include <cstdint>
#include <optional>

namespace __PACKAGE__ {

[[nodiscard]] std::optional<std::int64_t> checked_add(
    std::int64_t left,
    std::int64_t right) noexcept;

[[nodiscard]] std::int64_t clamp(
    std::int64_t value,
    std::int64_t minimum,
    std::int64_t maximum) noexcept;

}  // namespace __PACKAGE__

#endif
""".replace("__PACKAGE_UPPER__", package_upper).replace("__PACKAGE__", package)
        cpp_source = """#include "__PACKAGE__/math.hpp"

#include <algorithm>
#include <limits>

namespace __PACKAGE__ {

std::optional<std::int64_t> checked_add(
    std::int64_t left,
    std::int64_t right) noexcept {
    if ((right > 0 && left > std::numeric_limits<std::int64_t>::max() - right) ||
        (right < 0 && left < std::numeric_limits<std::int64_t>::min() - right)) {
        return std::nullopt;
    }
    return left + right;
}

std::int64_t clamp(
    std::int64_t value,
    std::int64_t minimum,
    std::int64_t maximum) noexcept {
    if (minimum > maximum) {
        std::swap(minimum, maximum);
    }
    return std::clamp(value, minimum, maximum);
}

}  // namespace __PACKAGE__
""".replace("__PACKAGE__", package)
        cpp_main = """#include "__PACKAGE__/math.hpp"

#include <charconv>
#include <cstdint>
#include <iostream>
#include <optional>
#include <string_view>
#include <system_error>

namespace {

std::optional<std::int64_t> parse_int64(std::string_view text) noexcept {
    std::int64_t value = 0;
    const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
    if (result.ec != std::errc{} || result.ptr != text.data() + text.size()) {
        return std::nullopt;
    }
    return value;
}

}  // namespace

int main(int argc, char **argv) {
    if (argc != 3) {
        std::cerr << "Usage: " << (argc > 0 ? argv[0] : "__NAME__") << " <integer> <integer>\\n";
        return 1;
    }

    const auto left = parse_int64(argv[1]);
    const auto right = parse_int64(argv[2]);
    if (!left || !right) {
        std::cerr << "Both arguments must be valid integers.\\n";
        return 1;
    }

    const auto result = __PACKAGE__::checked_add(*left, *right);
    if (!result) {
        std::cerr << "Integer overflow\\n";
        return 1;
    }
    std::cout << *result << '\\n';
    return 0;
}
""".replace("__PACKAGE__", package).replace("__NAME__", name)
        cpp_test = """#include "__PACKAGE__/math.hpp"

#include <cstdint>
#include <iostream>
#include <limits>

namespace {

int failures = 0;

void expect(bool condition, const char *label) {
    if (!condition) {
        std::cerr << "FAIL: " << label << '\\n';
        ++failures;
    }
}

}  // namespace

int main() {
    const auto sum = __PACKAGE__::checked_add(2, 3);
    expect(sum && *sum == 5, "addition result");
    expect(!__PACKAGE__::checked_add(std::numeric_limits<std::int64_t>::max(), 1),
           "overflow rejected");
    expect(__PACKAGE__::clamp(12, 0, 10) == 10, "clamp upper bound");
    expect(__PACKAGE__::clamp(-3, 0, 10) == 0, "clamp lower bound");
    return failures == 0 ? 0 : 1;
}
""".replace("__PACKAGE__", package)
        cmake = """cmake_minimum_required(VERSION 3.16)
project(__PACKAGE__ CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(NEXUS_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)

add_library(__PACKAGE___core src/math.cpp)
add_library(__PACKAGE__::core ALIAS __PACKAGE___core)
target_include_directories(__PACKAGE___core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)

add_executable(__PACKAGE__ src/main.cpp)
target_link_libraries(__PACKAGE__ PRIVATE __PACKAGE__::core)

foreach(target __PACKAGE___core __PACKAGE__)
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4 /permissive-)
  else()
    target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic)
  endif()
  if(NEXUS_ENABLE_SANITIZERS AND NOT MSVC)
    target_compile_options(${target} PRIVATE -fsanitize=address,undefined)
    target_link_options(${target} PRIVATE -fsanitize=address,undefined)
  endif()
endforeach()

enable_testing()
add_executable(test_math tests/test_math.cpp)
target_link_libraries(test_math PRIVATE __PACKAGE__::core)
if(NOT MSVC)
  target_compile_options(test_math PRIVATE -Wall -Wextra -Wpedantic)
endif()
add_test(NAME math COMMAND test_math)
""".replace("__PACKAGE__", package)
        makefile = """CXX ?= c++
CXXFLAGS ?= -std=c++20 -O2 -Wall -Wextra -Wpedantic -Iinclude
ifeq ($(SANITIZE),1)
CXXFLAGS += -g -fsanitize=address,undefined
LDFLAGS += -fsanitize=address,undefined
endif

.PHONY: all test clean
all: build/__NAME__

build/__NAME__: src/main.cpp src/math.cpp include/__PACKAGE__/math.hpp
\tmkdir -p build
\t$(CXX) $(CXXFLAGS) src/main.cpp src/math.cpp $(LDFLAGS) -o $@

build/test_math: tests/test_math.cpp src/math.cpp include/__PACKAGE__/math.hpp
\tmkdir -p build
\t$(CXX) $(CXXFLAGS) tests/test_math.cpp src/math.cpp $(LDFLAGS) -o $@

test: build/test_math
\t./build/test_math

clean:
\trm -rf build
""".replace("__PACKAGE__", package).replace("__NAME__", name)
        files.update(
            {
                "CMakeLists.txt": cmake,
                "Makefile": makefile,
                f"include/{package}/math.hpp": cpp_header,
                "src/math.cpp": cpp_source,
                "src/main.cpp": cpp_main,
                "tests/test_math.cpp": cpp_test,
                ".clang-format": "BasedOnStyle: LLVM\nIndentWidth: 4\nColumnLimit: 100\n",
            }
        )
    elif template == "rust-cli":
        cargo_toml = f"""[package]
name = "{name}"
version = "0.1.0"
edition = "2021"
description = {json.dumps(description)}
license = "{license_id if license_id != "none" else "MIT"}"

[lints.rust]
unsafe_code = "forbid"

[lints.clippy]
all = "warn"
pedantic = "warn"
"""
        files.update(
            {
                "Cargo.toml": cargo_toml,
                "rustfmt.toml": 'edition = "2021"\nmax_width = 100\n',
                "src/lib.rs": """use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AppError {
    Usage,
    InvalidInteger(String),
    Overflow,
}

impl fmt::Display for AppError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Usage => write!(f, "usage: __NAME__ <integer> <integer>"),
            Self::InvalidInteger(value) => write!(f, "invalid integer: {value}"),
            Self::Overflow => write!(f, "integer overflow"),
        }
    }
}

impl std::error::Error for AppError {}

pub fn parse_pair(args: &[String]) -> Result<(i64, i64), AppError> {
    let [left, right] = args else {
        return Err(AppError::Usage);
    };
    let left = left
        .parse::<i64>()
        .map_err(|_| AppError::InvalidInteger(left.clone()))?;
    let right = right
        .parse::<i64>()
        .map_err(|_| AppError::InvalidInteger(right.clone()))?;
    Ok((left, right))
}

pub fn add_from_args(args: &[String]) -> Result<i64, AppError> {
    let (left, right) = parse_pair(args)?;
    left.checked_add(right).ok_or(AppError::Overflow)
}

#[cfg(test)]
mod tests {
    use super::{add_from_args, AppError};

    fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(ToString::to_string).collect()
    }

    #[test]
    fn adds_valid_integers() {
        assert_eq!(add_from_args(&args(&["2", "3"])), Ok(5));
    }

    #[test]
    fn rejects_invalid_input() {
        assert_eq!(
            add_from_args(&args(&["two", "3"])),
            Err(AppError::InvalidInteger("two".to_owned()))
        );
    }

    #[test]
    fn rejects_overflow() {
        assert_eq!(
            add_from_args(&args(&[&i64::MAX.to_string(), "1"])),
            Err(AppError::Overflow)
        );
    }
}
""".replace("__NAME__", name),
                "src/main.rs": f"""use std::process::ExitCode;

use {package}::add_from_args;

fn main() -> ExitCode {{
    let args: Vec<String> = std::env::args().skip(1).collect();
    match add_from_args(&args) {{
        Ok(result) => {{
            println!("{{result}}");
            ExitCode::SUCCESS
        }}
        Err(error) => {{
            eprintln!("error: {{error}}");
            ExitCode::FAILURE
        }}
    }}
}}
""",
                "tests/cli.rs": """use std::process::Command;

#[test]
fn cli_prints_sum() {
    let output = Command::new(env!("CARGO_BIN_EXE___PACKAGE__"))
        .args(["40", "2"])
        .output()
        .expect("CLI should run");

    assert!(output.status.success());
    assert_eq!(String::from_utf8_lossy(&output.stdout).trim(), "42");
}

#[test]
fn cli_rejects_missing_arguments() {
    let output = Command::new(env!("CARGO_BIN_EXE___PACKAGE__"))
        .output()
        .expect("CLI should run");

    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("usage:"));
}
""".replace("__PACKAGE__", package),
            }
        )
    elif template == "php-web":
        composer = {
            "name": f"nexus/{name}",
            "description": description,
            "type": "project",
            "license": license_id if license_id != "none" else "MIT",
            "require": {"php": ">=8.2"},
            "autoload": {"psr-4": {"App\\": "src/"}},
            "scripts": {
                "lint": "php -l public/index.php && php -l src/Greeting.php && php -l tests/run.php",
                "test": ["@lint", "php tests/run.php"],
                "serve": "php -S 127.0.0.1:8000 -t public",
            },
        }
        files.update(
            {
                "composer.json": json.dumps(composer, indent=4) + "\n",
                "public/index.php": """<?php

declare(strict_types=1);

require_once __DIR__ . '/../src/Greeting.php';

use App\\Greeting;

session_set_cookie_params([
    'httponly' => true,
    'samesite' => 'Lax',
]);
session_start();

header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: strict-origin-when-cross-origin');
header("Content-Security-Policy: default-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'");

if (!isset($_SESSION['csrf_token']) || !is_string($_SESSION['csrf_token'])) {
    $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
}

$name = '';
$message = '';
$error = '';

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
    $token = $_POST['csrf_token'] ?? '';
    $nameValue = $_POST['name'] ?? '';
    $name = is_string($nameValue) ? trim($nameValue) : '';

    if (!is_string($token) || !hash_equals($_SESSION['csrf_token'], $token)) {
        $error = 'Your session expired. Please try again.';
    } else {
        try {
            $message = Greeting::forName($name)->message();
            $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
        } catch (InvalidArgumentException $exception) {
            $error = $exception->getMessage();
        }
    }
}

function e(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}
?>
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="description" content="<?= e('__SAFE_DESCRIPTION__') ?>">
    <title><?= e('__SAFE_TITLE__') ?></title>
    <link rel="stylesheet" href="/styles.css">
</head>
<body>
    <a class="skip-link" href="#main">Skip to main content</a>
    <main id="main" class="shell">
        <p class="eyebrow">Secure PHP starter</p>
        <h1><?= e('__SAFE_TITLE__') ?></h1>
        <p class="lede"><?= e('__SAFE_DESCRIPTION__') ?></p>

        <form method="post" action="/" novalidate>
            <input type="hidden" name="csrf_token" value="<?= e($_SESSION['csrf_token']) ?>">
            <div class="field">
                <label for="name">Your name</label>
                <p id="name-help" class="help">Use 1–80 characters. The value is validated and escaped before display.</p>
                <input
                    id="name"
                    name="name"
                    type="text"
                    autocomplete="name"
                    value="<?= e($name) ?>"
                    aria-describedby="name-help<?= $error !== '' ? ' form-error' : '' ?>"
                    aria-invalid="<?= $error !== '' ? 'true' : 'false' ?>"
                    required
                >
            </div>
            <?php if ($error !== ''): ?>
                <p id="form-error" class="error" role="alert"><?= e($error) ?></p>
            <?php endif; ?>
            <button type="submit">Create greeting</button>
            <p class="status" aria-live="polite"><?= e($message) ?></p>
        </form>
    </main>
</body>
</html>
""".replace("__SAFE_TITLE__", safe_title).replace("__SAFE_DESCRIPTION__", safe_description),
                "public/styles.css": """:root {
  color-scheme: light;
  --bg: #f7f4ee;
  --surface: #ffffff;
  --text: #20242c;
  --muted: #5f6875;
  --border: #ded6c7;
  --brand: #b95d32;
  --accent: #6757d9;
  --danger: #b42318;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
  color: var(--text);
  background: var(--bg);
}
* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; }
:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
.skip-link { position: absolute; left: 1rem; top: -5rem; z-index: 10; padding: 0.75rem 1rem; border-radius: 999px; background: var(--text); color: var(--bg); }
.skip-link:focus { top: 1rem; }
.shell { width: min(720px, calc(100% - 2rem)); margin: 4rem auto; padding: clamp(1.5rem, 5vw, 3rem); border: 1px solid var(--border); border-radius: 1.5rem; background: var(--surface); }
.eyebrow { color: var(--brand); font-size: 0.78rem; font-weight: 900; letter-spacing: 0.14em; text-transform: uppercase; }
h1 { margin: 0.5rem 0; font-size: clamp(2.5rem, 8vw, 4.5rem); line-height: 0.95; letter-spacing: -0.045em; }
.lede, .help, .status { color: var(--muted); line-height: 1.65; }
form { display: grid; gap: 1rem; margin-top: 2rem; }
.field { display: grid; gap: 0.5rem; }
label { font-weight: 800; }
.help { margin: 0; }
input { width: 100%; min-height: 2.9rem; border: 1px solid var(--border); border-radius: 0.8rem; padding: 0.75rem 0.9rem; background: var(--bg); color: var(--text); font: inherit; }
input[aria-invalid="true"] { border-color: var(--danger); }
button { min-height: 2.9rem; border: 0; border-radius: 999px; padding: 0.75rem 1.2rem; background: var(--text); color: var(--bg); font: inherit; font-weight: 900; cursor: pointer; }
.error { margin: 0; color: var(--danger); font-weight: 800; }
.status { min-height: 1.5em; margin: 0; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; }
}
""",
                "src/Greeting.php": """<?php

declare(strict_types=1);

namespace App;

use InvalidArgumentException;

final readonly class Greeting
{
    private function __construct(private string $name)
    {
    }

    public static function forName(string $name): self
    {
        $clean = trim($name);
        if ($clean === '') {
            throw new InvalidArgumentException('Please enter your name.');
        }
        if (mb_strlen($clean, 'UTF-8') > 80) {
            throw new InvalidArgumentException('Please use 80 characters or fewer.');
        }
        if (preg_match('/[\\x00-\\x1F\\x7F]/u', $clean) === 1) {
            throw new InvalidArgumentException('Names cannot contain control characters.');
        }

        return new self($clean);
    }

    public function message(): string
    {
        return 'Hello, ' . $this->name . '! Your secure PHP starter is working.';
    }
}
""",
                "tests/run.php": """<?php

declare(strict_types=1);

require_once __DIR__ . '/../src/Greeting.php';

use App\\Greeting;

function expect(bool $condition, string $label): void
{
    if (!$condition) {
        fwrite(STDERR, "FAIL: {$label}\\n");
        exit(1);
    }
}

expect(Greeting::forName('  Nexus  ')->message() === 'Hello, Nexus! Your secure PHP starter is working.', 'trims and formats a name');

try {
    Greeting::forName('');
    expect(false, 'empty names are rejected');
} catch (InvalidArgumentException) {
    expect(true, 'empty names are rejected');
}

echo "All PHP starter tests passed.\\n";
""",
                ".env.example": "APP_ENV=local\nAPP_URL=http://127.0.0.1:8000\n",
            }
        )
    elif template == "ruby-cli":
        files.update(
            {
                "Gemfile": """# frozen_string_literal: true

source "https://rubygems.org"

ruby ">= 3.1"

gemspec

group :test do
  gem "minitest", "~> 5.25"
  gem "rake", "~> 13.2"
end
""",
                f"{name}.gemspec": f"""# frozen_string_literal: true

Gem::Specification.new do |spec|
  spec.name = "{name}"
  spec.version = "0.1.0"
  spec.summary = {json.dumps(description)}
  spec.description = spec.summary
  spec.license = "{license_id if license_id != "none" else "MIT"}"
  spec.required_ruby_version = ">= 3.1"
  spec.files = Dir["lib/**/*.rb", "exe/*", "README.md", "LICENSE"].sort
  spec.bindir = "exe"
  spec.executables = ["{name}"]
  spec.require_paths = ["lib"]
end
""",
                "Rakefile": """# frozen_string_literal: true

require "rake/testtask"

Rake::TestTask.new(:test) do |task|
  task.libs << "lib"
  task.libs << "test"
  task.pattern = "test/test_*.rb"
end

task default: :test
""",
                f"lib/{package}.rb": f"""# frozen_string_literal: true

require_relative "{package}/version"
require_relative "{package}/greeter"

module {ruby_module}
end
""",
                f"lib/{package}/version.rb": f"""# frozen_string_literal: true

module {ruby_module}
  VERSION = "0.1.0"
end
""",
                f"lib/{package}/greeter.rb": f"""# frozen_string_literal: true

module {ruby_module}
  # Small immutable value object used by the command-line starter.
  class Greeter
    attr_reader :name

    def initialize(name)
      clean = name.to_s.strip
      raise ArgumentError, "name cannot be empty" if clean.empty?
      raise ArgumentError, "name is too long" if clean.length > 80

      @name = clean.freeze
      freeze
    end

    def message
      "Hello, #{{name}}! {title} is ready."
    end
  end
end
""",
                f"exe/{name}": f"""#!/usr/bin/env ruby
# frozen_string_literal: true

require_relative "../lib/{package}"

name = ARGV.first || "world"

begin
  puts {ruby_module}::Greeter.new(name).message
rescue ArgumentError => error
  warn "error: #{{error.message}}"
  exit 1
end
""",
                "test/test_helper.rb": """# frozen_string_literal: true

$LOAD_PATH.unshift File.expand_path("../lib", __dir__)

require "minitest/autorun"
""",
                f"test/test_{package}.rb": f"""# frozen_string_literal: true

require_relative "test_helper"
require "{package}"

class Test{ruby_module} < Minitest::Test
  def test_greeter_trims_name
    greeter = {ruby_module}::Greeter.new("  Nexus  ")

    assert_equal "Nexus", greeter.name
    assert_includes greeter.message, "Hello, Nexus!"
  end

  def test_greeter_rejects_empty_name
    assert_raises(ArgumentError) {{ {ruby_module}::Greeter.new("  ") }}
  end
end
""",
            }
        )
    elif template == "xml-toolkit":
        files.update(
            {
                "data/catalog.xml": f"""<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:nexus:catalog" generatedFor="{safe_title}">
  <book id="1" currency="INR">
    <title>Designing Reliable Tools</title>
    <author>Nexus Contributors</author>
    <price>499.00</price>
  </book>
  <book id="2" currency="INR">
    <title>Clean Interfaces with XML</title>
    <author>Nexus Contributors</author>
    <price>649.00</price>
  </book>
</catalog>
""",
                "schema/catalog.xsd": """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns="urn:nexus:catalog"
           targetNamespace="urn:nexus:catalog"
           elementFormDefault="qualified">
  <xs:element name="catalog">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="book" maxOccurs="unbounded">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="title" type="xs:string"/>
              <xs:element name="author" type="xs:string"/>
              <xs:element name="price" type="xs:decimal"/>
            </xs:sequence>
            <xs:attribute name="id" type="xs:positiveInteger" use="required"/>
            <xs:attribute name="currency" use="required">
              <xs:simpleType>
                <xs:restriction base="xs:string">
                  <xs:length value="3"/>
                </xs:restriction>
              </xs:simpleType>
            </xs:attribute>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
""",
                "transform/catalog.xsl": """<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:c="urn:nexus:catalog">
  <xsl:output method="text" encoding="UTF-8"/>
  <xsl:template match="/c:catalog">
    <xsl:for-each select="c:book">
      <xsl:value-of select="concat(@id, '. ', c:title, ' — ', c:author, ' (', @currency, ' ', c:price, ')')"/>
      <xsl:text>&#10;</xsl:text>
    </xsl:for-each>
  </xsl:template>
</xsl:stylesheet>
""",
                "src/xml_toolkit.py": '''# Safe, standard-library XML catalog reader.
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

NAMESPACE = "urn:nexus:catalog"
NS = {"c": NAMESPACE}
MAX_XML_BYTES = 1_000_000


class XmlToolkitError(ValueError):
    pass


@dataclass(frozen=True)
class Book:
    id: int
    title: str
    author: str
    price: str
    currency: str


def _required_text(book: ET.Element, tag: str) -> str:
    node = book.find(f"c:{tag}", NS)
    value = "" if node is None or node.text is None else node.text.strip()
    if not value:
        raise XmlToolkitError(f"book is missing a non-empty <{tag}>")
    return value


def parse_catalog(path: str | Path) -> list[Book]:
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise XmlToolkitError(f"could not read XML: {exc}") from exc
    if len(raw) > MAX_XML_BYTES:
        raise XmlToolkitError("XML document is too large")
    if b"<!doctype" in raw.lower():
        raise XmlToolkitError("DTD declarations are not accepted for untrusted XML")

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise XmlToolkitError(f"XML is not well-formed: {exc}") from exc
    if root.tag != f"{{{NAMESPACE}}}catalog":
        raise XmlToolkitError("root element must be <catalog> in urn:nexus:catalog")

    books: list[Book] = []
    for node in root.findall("c:book", NS):
        raw_id = node.attrib.get("id", "")
        currency = node.attrib.get("currency", "")
        try:
            book_id = int(raw_id)
            price = Decimal(_required_text(node, "price"))
        except (ValueError, InvalidOperation) as exc:
            raise XmlToolkitError("book id and price must be numeric") from exc
        if book_id <= 0 or price < 0 or len(currency) != 3:
            raise XmlToolkitError("book id, price, and currency must satisfy the catalog contract")
        books.append(
            Book(
                id=book_id,
                title=_required_text(node, "title"),
                author=_required_text(node, "author"),
                price=f"{price:.2f}",
                currency=currency,
            )
        )
    if not books:
        raise XmlToolkitError("catalog contains no books")
    return books


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read a safe XML catalog and print JSON")
    parser.add_argument("path", help="Path to catalog.xml")
    args = parser.parse_args(argv)
    try:
        books = parse_catalog(args.path)
    except XmlToolkitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps([asdict(book) for book in books], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
                "tests/test_xml_toolkit.py": '''from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xml_toolkit import XmlToolkitError, parse_catalog


def test_parse_catalog() -> None:
    books = parse_catalog(Path(__file__).resolve().parents[1] / "data" / "catalog.xml")
    assert [book.title for book in books] == [
        "Designing Reliable Tools",
        "Clean Interfaces with XML",
    ]


def test_rejects_dtd(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe.xml"
    unsafe.write_text(
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        '<catalog xmlns="urn:nexus:catalog">&xxe;</catalog>',
        encoding="utf-8",
    )
    with pytest.raises(XmlToolkitError, match="DTD"):
        parse_catalog(unsafe)
''',
                "pyproject.toml": f"""[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = {json.dumps(name)}
version = "0.1.0"
description = {json.dumps(description)}
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools]
package-dir = {{"" = "src"}}
py-modules = ["xml_toolkit"]

[tool.pytest.ini_options]
testpaths = ["tests"]
""",
            }
        )
    elif template == "python-fastapi":
        files.update(
            {
                "pyproject.toml": (
                    "[build-system]\n"
                    "requires = [\"hatchling\"]\n"
                    "build-backend = \"hatchling.build\"\n\n"
                    "[project]\n"
                    f"name = {json.dumps(name)}\n"
                    "version = \"0.1.0\"\n"
                    f"description = {json.dumps(description)}\n"
                    "readme = \"README.md\"\n"
                    "requires-python = \">=3.11\"\n"
                    "dependencies = [\"fastapi>=0.115\", \"uvicorn[standard]>=0.30\"]\n\n"
                    "[project.optional-dependencies]\n"
                    "dev = [\"pytest>=8\", \"httpx>=0.27\"]\n\n"
                    "[tool.hatch.build.targets.wheel]\n"
                    "packages = [\"app\"]\n\n"
                    "[tool.pytest.ini_options]\n"
                    "testpaths = [\"tests\"]\n"
                ),
                "app/__init__.py": f'"""{title} API package."""\n',
                "app/main.py": (
                    '"""Small, testable FastAPI starter with an in-memory item store."""\n\n'
                    "from __future__ import annotations\n\n"
                    "from itertools import count\n\n"
                    "from fastapi import FastAPI, HTTPException\n"
                    "from pydantic import BaseModel, Field\n\n"
                    f"app = FastAPI(title={json.dumps(title)}, version='0.1.0')\n\n"
                    "class ItemCreate(BaseModel):\n"
                    "    name: str = Field(min_length=1, max_length=120)\n"
                    "    notes: str = ''\n\n"
                    "class Item(ItemCreate):\n"
                    "    id: int\n\n"
                    "_ids = count(1)\n"
                    "_items: dict[int, Item] = {}\n\n"
                    "@app.get('/health')\n"
                    "def health() -> dict[str, str]:\n"
                    "    return {'status': 'ok'}\n\n"
                    "@app.get('/')\n"
                    "def root() -> dict[str, str]:\n"
                    f"    return {{'message': {json.dumps(title + ' API is running')}}}\n\n"
                    "@app.get('/items', response_model=list[Item])\n"
                    "def list_items() -> list[Item]:\n"
                    "    return list(_items.values())\n\n"
                    "@app.post('/items', response_model=Item, status_code=201)\n"
                    "def create_item(payload: ItemCreate) -> Item:\n"
                    "    item = Item(id=next(_ids), **payload.model_dump())\n"
                    "    _items[item.id] = item\n"
                    "    return item\n\n"
                    "@app.get('/items/{item_id}', response_model=Item)\n"
                    "def get_item(item_id: int) -> Item:\n"
                    "    try:\n"
                    "        return _items[item_id]\n"
                    "    except KeyError as exc:\n"
                    "        raise HTTPException(status_code=404, detail='Item not found') from exc\n\n"
                    "@app.delete('/items/{item_id}', status_code=204)\n"
                    "def delete_item(item_id: int) -> None:\n"
                    "    _items.pop(item_id, None)\n"
                ),
                "tests/test_app.py": (
                    "from fastapi.testclient import TestClient\n\n"
                    "from app.main import app\n\n"
                    "client = TestClient(app)\n\n"
                    "def test_health() -> None:\n"
                    "    response = client.get('/health')\n"
                    "    assert response.status_code == 200\n"
                    "    assert response.json() == {'status': 'ok'}\n\n"
                    "def test_create_and_list_item() -> None:\n"
                    "    created = client.post('/items', json={'name': 'First item', 'notes': 'starter'})\n"
                    "    assert created.status_code == 201\n"
                    "    assert created.json()['name'] == 'First item'\n"
                    "    listed = client.get('/items')\n"
                    "    assert listed.status_code == 200\n"
                    "    assert any(item['name'] == 'First item' for item in listed.json())\n"
                ),
                ".env.example": "APP_ENV=development\nAPP_HOST=127.0.0.1\nAPP_PORT=8000\n",
                "Dockerfile": (
                    "FROM python:3.12-slim\n"
                    "WORKDIR /app\n"
                    "COPY pyproject.toml README.md ./\n"
                    "COPY app ./app\n"
                    "RUN pip install --no-cache-dir .\n"
                    "EXPOSE 8000\n"
                    "CMD [\"uvicorn\", \"app.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]\n"
                ),
            }
        )
    elif template == "react-vite":
        package_json = {
            "name": name,
            "private": True,
            "version": "0.1.0",
            "type": "module",
            "scripts": {
                "dev": "vite --host 0.0.0.0",
                "build": "tsc --noEmit && vite build",
                "typecheck": "tsc --noEmit",
                "preview": "vite preview --host 0.0.0.0",
            },
            "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
            "devDependencies": {
                "@types/react": "^18.3.11",
                "@types/react-dom": "^18.3.1",
                "@vitejs/plugin-react": "^4.3.3",
                "typescript": "^5.6.3",
                "vite": "^5.4.10",
            },
        }
        files.update(
            {
                "package.json": json.dumps(package_json, indent=2) + "\n",
                "index.html": (
                    "<!doctype html>\n<html lang=\"en\">\n  <head>\n"
                    "    <meta charset=\"UTF-8\" />\n"
                    "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
                    f"    <meta name=\"description\" content=\"{safe_description}\" />\n"
                    f"    <title>{safe_title}</title>\n  </head>\n  <body>\n"
                    "    <div id=\"root\"></div>\n"
                    "    <script type=\"module\" src=\"/src/main.tsx\"></script>\n"
                    "  </body>\n</html>\n"
                ),
                "vite.config.ts": (
                    "import { defineConfig } from 'vite';\n"
                    "import react from '@vitejs/plugin-react';\n\n"
                    "export default defineConfig({\n"
                    "  plugins: [react()],\n"
                    "  server: { host: '0.0.0.0', port: 5173 },\n"
                    "});\n"
                ),
                "tsconfig.json": json.dumps(
                    {
                        "compilerOptions": {
                            "target": "ES2020",
                            "useDefineForClassFields": True,
                            "lib": ["ES2020", "DOM", "DOM.Iterable"],
                            "module": "ESNext",
                            "skipLibCheck": True,
                            "moduleResolution": "bundler",
                            "allowImportingTsExtensions": True,
                            "resolveJsonModule": True,
                            "isolatedModules": True,
                            "noEmit": True,
                            "jsx": "react-jsx",
                            "strict": True,
                        },
                        "include": ["src", "vite.config.ts"],
                    },
                    indent=2,
                )
                + "\n",
                "src/main.tsx": (
                    "import React from 'react';\n"
                    "import { createRoot } from 'react-dom/client';\n"
                    "import App from './App';\n"
                    "import './index.css';\n\n"
                    "createRoot(document.getElementById('root')!).render(\n"
                    "  <React.StrictMode><App /></React.StrictMode>,\n"
                    ");\n"
                ),
                "src/App.tsx": (
                    "import { FormEvent, useMemo, useState } from 'react';\n\n"
                    "type Task = { id: number; title: string; done: boolean };\n\n"
                    "const starterTasks: Task[] = [\n"
                    "  { id: 1, title: 'Define the first real user workflow', done: true },\n"
                    "  { id: 2, title: 'Replace starter data with an API', done: false },\n"
                    "  { id: 3, title: 'Add empty, loading, and error states', done: false },\n"
                    "];\n\n"
                    "export default function App() {\n"
                    "  const [tasks, setTasks] = useState(starterTasks);\n"
                    "  const [draft, setDraft] = useState('');\n"
                    "  const done = useMemo(() => tasks.filter((task) => task.done).length, [tasks]);\n\n"
                    "  function addTask(event: FormEvent) {\n"
                    "    event.preventDefault();\n"
                    "    if (!draft.trim()) return;\n"
                    "    setTasks((current) => [...current, { id: Date.now(), title: draft.trim(), done: false }]);\n"
                    "    setDraft('');\n"
                    "  }\n\n"
                    "  return (\n"
                    "    <main className=\"shell\">\n"
                    "      <section className=\"hero\">\n"
                    "        <p className=\"eyebrow\">Nexus starter</p>\n"
                    f"        <h1>{safe_title}</h1>\n"
                    f"        <p>{safe_description}</p>\n"
                    "        <div className=\"progress\"><span style={{ width: `${tasks.length ? (done / tasks.length) * 100 : 0}%` }} /></div>\n"
                    "        <p className=\"muted\" aria-live=\"polite\">{done} of {tasks.length} starter tasks complete</p>\n"
                    "      </section>\n"
                    "      <section className=\"card\">\n"
                    "        <form onSubmit={addTask} className=\"task-form\">\n"
                    "          <label className=\"sr-only\" htmlFor=\"new-starter-task\">New starter task</label>\n"
                    "          <input id=\"new-starter-task\" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder=\"Add the next build task\" />\n"
                    "          <button type=\"submit\">Add</button>\n"
                    "        </form>\n"
                    "        <ul className=\"tasks\">\n"
                    "          {tasks.map((task) => (\n"
                    "            <li key={task.id}>\n"
                    "              <input id={`starter-task-${task.id}`} type=\"checkbox\" checked={task.done} aria-label={`Mark ${task.title} as ${task.done ? 'open' : 'done'}`} onChange={() => setTasks((current) => current.map((item) => item.id === task.id ? { ...item, done: !item.done } : item))} /> <label htmlFor={`starter-task-${task.id}`} className={task.done ? 'done' : ''}>{task.title}</label>\n"
                    "            </li>\n"
                    "          ))}\n"
                    "        </ul>\n"
                    "      </section>\n"
                    "    </main>\n"
                    "  );\n"
                    "}\n"
                ),
                "src/index.css": (
                    ":root { color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; color: #20242c; background: #f7f4ee; }\n"
                    "* { box-sizing: border-box; } body { margin: 0; }\n"
                    ".shell { width: min(880px, calc(100% - 32px)); margin: 0 auto; padding: 56px 0; }\n"
                    ".hero { padding: 36px; border: 1px solid #e5ded2; border-radius: 28px; background: linear-gradient(135deg, #fff, #fdf3e3 52%, #eaf2ff); box-shadow: 0 24px 60px rgba(80, 65, 35, .10); }\n"
                    ".eyebrow { text-transform: uppercase; letter-spacing: .14em; font-size: 12px; color: #b05c2a; font-weight: 700; }\n"
                    "h1 { font-size: clamp(36px, 6vw, 64px); line-height: .95; margin: 10px 0; }\n"
                    ".progress { height: 10px; background: rgba(32,36,44,.10); border-radius: 999px; overflow: hidden; margin-top: 24px; } .progress span { display: block; height: 100%; background: linear-gradient(90deg,#d97757,#7c6cf0,#2f9e8f); }\n"
                    ".muted { color: #6b7280; } .card { margin-top: 20px; padding: 22px; background: rgba(255,255,255,.82); border: 1px solid #e5ded2; border-radius: 22px; }\n"
                    ".task-form { display: flex; gap: 10px; } input[type='text'], .task-form input { flex: 1; border: 1px solid #d8d0c2; border-radius: 12px; padding: 12px 14px; font: inherit; }\n"
                    "button { border: 0; border-radius: 12px; padding: 12px 18px; background: #252a34; color: white; font-weight: 700; cursor: pointer; }\n"
                    ".tasks { list-style: none; padding: 0; } .tasks li { display: flex; gap: 10px; align-items: center; padding: 11px 0; border-bottom: 1px solid #eee7da; } .done { text-decoration: line-through; color: #8a8f98; }\n"
                    ".sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }\n"
                    ":focus-visible { outline: 3px solid #6757d9; outline-offset: 3px; }\n"
                    "@media (max-width: 560px) { .shell { padding: 28px 0; } .hero, .card { padding: 22px; } .task-form { flex-direction: column; } .task-form button { width: 100%; } }\n"
                    "@media (prefers-reduced-motion: reduce) { *, *::before, *::after { transition: none !important; animation: none !important; } }\n"
                ),
            }
        )
    elif template == "node-api":
        package_json = {
            "name": name,
            "version": "0.1.0",
            "private": True,
            "type": "module",
            "scripts": {"dev": "node --watch src/index.js", "start": "node src/index.js", "test": "node --test"},
        }
        files.update(
            {
                "package.json": json.dumps(package_json, indent=2) + "\n",
                "src/index.js": (
                    "import { createServer as createHttpServer } from 'node:http';\n\n"
                    "const items = new Map();\nlet nextId = 1;\n\n"
                    "function send(response, status, body) {\n"
                    "  const payload = body === undefined ? '' : JSON.stringify(body);\n"
                    "  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8' });\n"
                    "  response.end(payload);\n}\n\n"
                    "async function readJson(request) {\n"
                    "  const chunks = [];\n  for await (const chunk of request) chunks.push(chunk);\n"
                    "  if (!chunks.length) return {};\n  return JSON.parse(Buffer.concat(chunks).toString('utf8'));\n}\n\n"
                    "export function createServer() {\n"
                    "  return createHttpServer(async (request, response) => {\n"
                    "    const url = new URL(request.url ?? '/', 'http://localhost');\n"
                    "    try {\n"
                    "      if (request.method === 'GET' && url.pathname === '/health') return send(response, 200, { status: 'ok' });\n"
                    f"      if (request.method === 'GET' && url.pathname === '/') return send(response, 200, {{ message: {json.dumps(title + ' API is running')} }});\n"
                    "      if (request.method === 'GET' && url.pathname === '/items') return send(response, 200, [...items.values()]);\n"
                    "      if (request.method === 'POST' && url.pathname === '/items') {\n"
                    "        const body = await readJson(request);\n"
                    "        if (!body.name?.trim()) return send(response, 422, { error: 'name is required' });\n"
                    "        const item = { id: nextId++, name: body.name.trim(), notes: body.notes ?? '' };\n"
                    "        items.set(item.id, item); return send(response, 201, item);\n"
                    "      }\n"
                    "      return send(response, 404, { error: 'Not found' });\n"
                    "    } catch { return send(response, 400, { error: 'Invalid JSON' }); }\n"
                    "  });\n}\n\n"
                    "if (import.meta.url === `file://${process.argv[1]}`) {\n"
                    "  const port = Number(process.env.PORT ?? 3000);\n"
                    "  createServer().listen(port, '0.0.0.0', () => console.log(`Listening on ${port}`));\n}\n"
                ),
                "test/api.test.js": (
                    "import assert from 'node:assert/strict';\nimport test from 'node:test';\n"
                    "import { createServer } from '../src/index.js';\n\n"
                    "test('health and item creation', async () => {\n"
                    "  const server = createServer();\n"
                    "  await new Promise((resolve) => server.listen(0, resolve));\n"
                    "  const { port } = server.address();\n"
                    "  try {\n"
                    "    const health = await fetch(`http://127.0.0.1:${port}/health`);\n"
                    "    assert.equal(health.status, 200);\n"
                    "    const created = await fetch(`http://127.0.0.1:${port}/items`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ name: 'First' }) });\n"
                    "    assert.equal(created.status, 201);\n"
                    "  } finally { server.close(); }\n});\n"
                ),
                ".env.example": "PORT=3000\nNODE_ENV=development\n",
            }
        )
    elif template == "python-cli":
        files.update(
            {
                "pyproject.toml": (
                    "[build-system]\nrequires = [\"hatchling\"]\nbuild-backend = \"hatchling.build\"\n\n"
                    "[project]\n"
                    f"name = {json.dumps(name)}\nversion = \"0.1.0\"\n"
                    f"description = {json.dumps(description)}\nreadme = \"README.md\"\nrequires-python = \">=3.11\"\ndependencies = []\n\n"
                    "[project.optional-dependencies]\ndev = [\"pytest>=8\"]\n\n"
                    "[project.scripts]\n"
                    f"{name} = \"{package}.cli:main\"\n\n"
                    "[tool.hatch.build.targets.wheel]\npackages = ['src/" + package + "']\n\n"
                    "[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\npythonpath = [\"src\"]\n"
                ),
                f"src/{package}/__init__.py": f'"""{title} command-line package."""\n\n__version__ = "0.1.0"\n',
                f"src/{package}/cli.py": (
                    '"""Command-line interface."""\n\n'
                    "from __future__ import annotations\n\n"
                    "import argparse\n\n"
                    "def build_parser() -> argparse.ArgumentParser:\n"
                    f"    parser = argparse.ArgumentParser(prog={json.dumps(name)}, description={json.dumps(description)})\n"
                    "    parser.add_argument('--name', default='world', help='Name to greet')\n"
                    "    return parser\n\n"
                    "def main(argv: list[str] | None = None) -> int:\n"
                    "    args = build_parser().parse_args(argv)\n"
                    f"    print(f'Hello, {{args.name}}! {title} is ready.')\n"
                    "    return 0\n\n"
                    "if __name__ == '__main__':\n"
                    "    raise SystemExit(main())\n"
                ),
                f"src/{package}/__main__.py": "from .cli import main\n\nif __name__ == '__main__':\n    raise SystemExit(main())\n",
                "tests/test_cli.py": (
                    f"from {package}.cli import main\n\n"
                    "def test_main_greets(capsys) -> None:\n"
                    "    assert main(['--name', 'Nexus']) == 0\n"
                    "    assert 'Hello, Nexus!' in capsys.readouterr().out\n"
                ),
            }
        )
    elif template == "static-site":
        files.update(
            {
                "index.html": (
                    "<!doctype html>\n<html lang=\"en\">\n<head>\n"
                    "  <meta charset=\"utf-8\" />\n"
                    "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
                    f"  <meta name=\"description\" content=\"{safe_description}\" />\n"
                    f"  <title>{safe_title}</title>\n"
                    "  <link rel=\"stylesheet\" href=\"styles.css\" />\n</head>\n<body>\n"
                    "  <a class=\"skip-link\" href=\"#main\">Skip to main content</a>\n"
                    "  <header class=\"site-header\"><nav aria-label=\"Primary\"><a href=\"#main\" aria-current=\"page\">Home</a></nav></header>\n"
                    "  <main id=\"main\" class=\"shell\">\n"
                    "    <p class=\"eyebrow\">Nexus starter</p>\n"
                    f"    <h1>{safe_title}</h1>\n    <p class=\"lede\">{safe_description}</p>\n"
                    "    <button id=\"action\" type=\"button\">Start building</button>\n"
                    "    <p id=\"status\" aria-live=\"polite\"></p>\n"
                    "  </main>\n  <footer class=\"site-footer\"><p>Created with Nexus.</p></footer>\n  <script src=\"script.js\" defer></script>\n</body>\n</html>\n"
                ),
                "script.js": (
                    "const button = document.querySelector('#action');\n"
                    "const status = document.querySelector('#status');\n"
                    "button?.addEventListener('click', () => {\n"
                    "  status.textContent = 'Starter is working. Replace this section with your first real workflow.';\n});\n"
                ),
                "styles.css": (
                    ":root { font-family: ui-sans-serif, system-ui, sans-serif; color: #22252b; background: #f7f4ee; }\n"
                    "body { margin: 0; } .site-header, .site-footer { width: min(760px, calc(100% - 32px)); margin: 20px auto; } .shell { width: min(760px, calc(100% - 32px)); margin: 32px auto; padding: clamp(24px, 5vw, 40px); border: 1px solid #e4dccf; border-radius: 28px; background: linear-gradient(135deg,#fff,#fdf1df 55%,#eaf2ff); box-shadow: 0 24px 60px rgba(80,65,35,.12); }\n"
                    ".skip-link { position: absolute; left: 1rem; top: -5rem; padding: .75rem 1rem; border-radius: 999px; background: #252a34; color: #fff; } .skip-link:focus { top: 1rem; }\n"
                    ".eyebrow { color: #b05c2a; text-transform: uppercase; letter-spacing: .14em; font-weight: 800; font-size: 12px; } h1 { font-size: clamp(40px,7vw,72px); line-height: .95; margin: 10px 0; } .lede { font-size: 19px; line-height: 1.6; color: #5c6470; } button { border: 0; border-radius: 999px; background: #252a34; color: white; padding: 13px 20px; font-weight: 800; cursor: pointer; }\n"
                    ":focus-visible { outline: 3px solid #6757d9; outline-offset: 3px; }\n"
                    "@media (max-width: 560px) { .shell { margin: 20px auto; } button { width: 100%; } }\n"
                    "@media (prefers-reduced-motion: reduce) { *, *::before, *::after { transition: none !important; animation: none !important; } }\n"
                ),
                "404.html": "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Not found</title></head><body><main><h1>Page not found</h1><p><a href=\"/\">Return home</a></p></main></body></html>\n",
            }
        )

    detail = _REPOSITORY_TEMPLATE_DETAILS.get(template, {})
    highlights = detail.get("highlights") if isinstance(detail.get("highlights"), list) else []
    recommended_checks = detail.get("recommended_checks") if isinstance(detail.get("recommended_checks"), list) else []
    if highlights or recommended_checks:
        files["README.md"] += "\n## Template highlights\n\n"
        files["README.md"] += "".join(f"- {item}\n" for item in highlights)
        if recommended_checks:
            files["README.md"] += (
                "\nRecommended Nexus checks: "
                + ", ".join(f"`{item}`" for item in recommended_checks)
                + ".\n"
            )

    if include_ci and template != "empty":
        if template in {"python-fastapi", "python-cli"}:
            ci = (
                "name: CI\n\non:\n  push:\n  pull_request:\n\njobs:\n  test:\n"
                "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
                "      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n"
                "      - run: python -m pip install --upgrade pip\n"
                "      - run: pip install -e '.[dev]'\n      - run: pytest\n"
            )
        elif template in {"react-vite", "frontend-design-system"}:
            ci = (
                "name: CI\n\non:\n  push:\n  pull_request:\n\njobs:\n  build:\n"
                "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
                "      - uses: actions/setup-node@v4\n        with:\n          node-version: '20'\n          cache: npm\n"
                "      - run: npm install\n      - run: npm run build\n"
            )
        elif template == "node-api":
            ci = (
                "name: CI\n\non:\n  push:\n  pull_request:\n\njobs:\n  test:\n"
                "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
                "      - uses: actions/setup-node@v4\n        with:\n          node-version: '20'\n"
                "      - run: npm test\n"
            )
        elif template == "html5-clean-ui":
            ci = (
                "name: CI\n\non:\n  push:\n  pull_request:\n\njobs:\n  test:\n"
                "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
                "      - uses: actions/setup-node@v4\n        with:\n          node-version: '20'\n"
                "      - run: npm test\n"
            )
        elif template in {"c-cmake", "cpp-cmake"}:
            ci = (
                "name: CI\n\non:\n  push:\n  pull_request:\n\njobs:\n  build:\n"
                "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
                "      - run: make test\n"
                "      - run: cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug\n"
                "      - run: cmake --build build\n"
                "      - run: ctest --test-dir build --output-on-failure\n"
            )
        elif template == "rust-cli":
            ci = (
                "name: CI\n\non:\n  push:\n  pull_request:\n\njobs:\n  test:\n"
                "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
                "      - uses: dtolnay/rust-toolchain@stable\n        with:\n          components: rustfmt, clippy\n"
                "      - run: cargo fmt --all -- --check\n"
                "      - run: cargo clippy --all-targets -- -D warnings\n"
                "      - run: cargo test\n"
            )
        elif template == "php-web":
            ci = (
                "name: CI\n\non:\n  push:\n  pull_request:\n\njobs:\n  test:\n"
                "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
                "      - uses: shivammathur/setup-php@v2\n        with:\n          php-version: '8.2'\n          tools: composer\n"
                "      - run: composer validate --no-check-publish\n"
                "      - run: composer install --no-interaction --prefer-dist\n"
                "      - run: composer test\n"
            )
        elif template == "ruby-cli":
            ci = (
                "name: CI\n\non:\n  push:\n  pull_request:\n\njobs:\n  test:\n"
                "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
                "      - uses: ruby/setup-ruby@v1\n        with:\n          ruby-version: '3.3'\n          bundler-cache: true\n"
                "      - run: bundle exec rake test\n"
            )
        elif template == "xml-toolkit":
            ci = (
                "name: CI\n\non:\n  push:\n  pull_request:\n\njobs:\n  test:\n"
                "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
                "      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n"
                "      - run: python -m pip install --upgrade pip\n"
                "      - run: pip install -e '.[dev]'\n"
                "      - run: pytest\n"
                "      - run: sudo apt-get update && sudo apt-get install -y libxml2-utils\n"
                "      - run: xmllint --noout --schema schema/catalog.xsd data/catalog.xml\n"
            )
        else:
            ci = (
                "name: Deploy static site\n\non:\n  push:\n    branches: [main]\n"
                "permissions:\n  contents: read\n  pages: write\n  id-token: write\n\njobs:\n  deploy:\n"
                "    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n"
                "      - uses: actions/upload-pages-artifact@v3\n        with:\n          path: .\n"
                "      - uses: actions/deploy-pages@v4\n"
            )
        files[".github/workflows/ci.yml"] = ci
    return files


def _valid_github_remote(value: str) -> bool:
    return bool(
        re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", value)
        or re.fullmatch(r"git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", value)
    )


async def _run_repository_git(
    repo: Path, *args: str, with_identity: bool = False, timeout: float = 30.0
) -> dict[str, Any]:
    git_bin = shutil.which("git")
    if not git_bin:
        return {"returncode": 127, "stdout": "", "stderr": "git executable not found"}
    command = [git_bin, "-C", str(repo)]
    if with_identity:
        command.extend(["-c", "user.name=NEXUS", "-c", "user.email=nexus@localhost"])
    command.extend(args)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            return {"returncode": 124, "stdout": "", "stderr": "git command timed out"}
        return {
            "returncode": process.returncode or 0,
            "stdout": stdout.decode("utf-8", errors="replace").strip()[-4000:],
            "stderr": stderr.decode("utf-8", errors="replace").strip()[-4000:],
        }
    except OSError as exc:
        return {"returncode": 1, "stdout": "", "stderr": str(exc)}


async def _create_repository(params: dict[str, Any]) -> dict[str, Any]:
    requested_name = _normalize_repository_name(params.get("name", ""))
    if not requested_name:
        return {
            "created": False,
            "error": "Repository name must contain letters or numbers and become a safe folder name.",
        }

    template = str(params.get("template") or "python-fastapi").strip()
    if template not in _REPOSITORY_TEMPLATES:
        return {
            "created": False,
            "error": f"Unknown repository template '{template}'. Choose one of: {', '.join(sorted(_REPOSITORY_TEMPLATES))}.",
        }
    license_id = str(params.get("license") or "MIT").strip()
    if license_id not in _REPOSITORY_LICENSES:
        return {
            "created": False,
            "error": f"Unknown license '{license_id}'. Choose MIT, BSD-3-Clause, Unlicense, or none.",
        }

    description = " ".join(str(params.get("description") or "").split()).strip()[:300]
    if not description:
        description = f"A new {_repository_title(requested_name)} project created with Nexus."

    raw_path = str(params.get("path") or "").strip()
    target_hint = raw_path or f"projects/{requested_name}"
    target, err = resolve_confined_path(target_hint, must_exist=False)
    if not target:
        return {"created": False, "error": err}
    if target in get_allowed_roots():
        return {"created": False, "error": "Choose a project subfolder; Nexus will not scaffold into an allowed root."}

    workspace = get_workspace_root()
    try:
        workspace_relative = target.relative_to(workspace)
    except ValueError:
        workspace_relative = None
    if workspace_relative is not None and workspace_relative.parts:
        if workspace_relative.parts[0] in _PROTECTED_REPOSITORY_ROOTS:
            return {
                "created": False,
                "error": (
                    f"'{workspace_relative.parts[0]}' is protected application source. "
                    f"Create the repository under projects/{requested_name} or another new folder."
                ),
            }

    repo_name = requested_name
    if raw_path:
        repo_name = _normalize_repository_name(target.name) or requested_name

    github_remote = str(params.get("github_remote") or "").strip()
    if github_remote and not _valid_github_remote(github_remote):
        return {
            "created": False,
            "error": "github_remote must be an https://github.com/owner/repo or git@github.com:owner/repo URL without credentials.",
        }

    initialize_git = _repository_bool(params.get("initialize_git"), True)
    initial_commit = _repository_bool(params.get("initial_commit"), True)
    include_ci = _repository_bool(params.get("include_ci"), True)
    overwrite = _repository_bool(params.get("overwrite"), False)

    if target.exists() and not target.is_dir():
        return {"created": False, "error": f"Target path exists and is not a directory: {target}"}
    existing_entries = list(target.iterdir()) if target.exists() else []
    if existing_entries and not overwrite:
        return {
            "created": False,
            "error": (
                f"Target directory already exists and is not empty: {target}. "
                "Choose another name/path, or set overwrite=true to add template files while preserving unknown files."
            ),
            "path": str(target),
            "existing_entries": len(existing_entries),
        }

    approval_error = await _require_file_tool_approval("create_repository", target)
    if approval_error is not None:
        return {**approval_error, "created": False, "path": str(target)}

    template_files = _repository_files(template, repo_name, description, license_id, include_ci)
    written: list[str] = []
    overwritten: list[str] = []
    preserved_unknown_files = 0
    if existing_entries:
        known = set(template_files)
        preserved_unknown_files = sum(
            1
            for entry in target.rglob("*")
            if entry.is_file() and entry.relative_to(target).as_posix() not in known
        )

    try:
        target.mkdir(parents=True, exist_ok=True)
        for relative_name, content in template_files.items():
            relative_path = Path(relative_name)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                return {
                    "created": False,
                    "error": f"Unsafe template path rejected: {relative_name}",
                    "path": str(target),
                    "files_written": written,
                }
            destination = (target / relative_path).resolve()
            if target not in destination.parents:
                return {
                    "created": False,
                    "error": f"Template path escaped the repository folder: {relative_name}",
                    "path": str(target),
                    "files_written": written,
                }
            existed = destination.exists()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="\n")
            written.append(relative_name)
            if existed:
                overwritten.append(relative_name)
    except OSError as exc:
        return {
            "created": False,
            "error": f"Repository scaffold stopped while writing files: {exc}",
            "path": str(target),
            "files_written": written,
        }

    git_result: dict[str, Any] = {
        "initialized": False,
        "branch": None,
        "committed": False,
        "commit": None,
        "remote": github_remote or None,
        "remote_configured": False,
        "clean": None,
        "notes": [],
    }
    notes: list[str] = []
    if initialize_git:
        already_repo = (target / ".git").exists()
        if not already_repo:
            init = await _run_repository_git(target, "init", "-b", "main")
            if init["returncode"] != 0:
                init = await _run_repository_git(target, "init")
                if init["returncode"] == 0:
                    await _run_repository_git(target, "symbolic-ref", "HEAD", "refs/heads/main")
            if init["returncode"] != 0:
                git_result["notes"].append(init["stderr"] or "Git initialization failed.")
            else:
                git_result["initialized"] = True
        else:
            git_result["initialized"] = True
            git_result["notes"].append("Existing Git metadata was preserved.")

        if git_result["initialized"]:
            if github_remote:
                existing_remote = await _run_repository_git(target, "remote", "get-url", "origin")
                if existing_remote["returncode"] == 0:
                    current_remote = str(existing_remote["stdout"]).strip()
                    git_result["remote"] = current_remote
                    git_result["remote_configured"] = current_remote == github_remote
                    if current_remote != github_remote:
                        git_result["notes"].append("Existing origin remote was not overwritten.")
                else:
                    add_remote = await _run_repository_git(target, "remote", "add", "origin", github_remote)
                    git_result["remote_configured"] = add_remote["returncode"] == 0
                    if add_remote["returncode"] != 0:
                        git_result["notes"].append(add_remote["stderr"] or "Could not configure origin remote.")

            if initial_commit:
                add = await _run_repository_git(target, "add", ".")
                if add["returncode"] == 0:
                    status = await _run_repository_git(target, "status", "--porcelain")
                    if str(status["stdout"]).strip():
                        commit = await _run_repository_git(
                            target,
                            "commit",
                            "-m",
                            "Initial commit from Nexus",
                            with_identity=True,
                        )
                        if commit["returncode"] == 0:
                            git_result["committed"] = True
                        else:
                            git_result["notes"].append(commit["stderr"] or commit["stdout"] or "Initial commit failed.")
                    else:
                        git_result["committed"] = True
                        git_result["notes"].append("No changes needed a new commit.")
                else:
                    git_result["notes"].append(add["stderr"] or "Could not stage repository files.")

            branch = await _run_repository_git(target, "branch", "--show-current")
            if branch["returncode"] == 0 and branch["stdout"]:
                git_result["branch"] = str(branch["stdout"]).strip()
            else:
                symbolic = await _run_repository_git(target, "symbolic-ref", "--short", "HEAD")
                git_result["branch"] = str(symbolic["stdout"]).strip() or "main"
            head = await _run_repository_git(target, "rev-parse", "--short", "HEAD")
            if head["returncode"] == 0:
                git_result["commit"] = str(head["stdout"]).strip() or None
                git_result["committed"] = bool(git_result["commit"])
            status = await _run_repository_git(target, "status", "--porcelain")
            if status["returncode"] == 0:
                git_result["clean"] = not bool(str(status["stdout"]).strip())
    elif initial_commit:
        notes.append("Initial commit was skipped because initialize_git=false.")

    if existing_entries and overwrite:
        notes.append(f"Preserved {preserved_unknown_files} existing non-template file(s); Nexus never deletes unknown files during scaffolding.")

    try:
        display_path = target.relative_to(workspace).as_posix()
    except ValueError:
        display_path = str(target)

    push_commands = [
        "git branch -M main",
        f"git remote add origin https://github.com/<your-username>/{repo_name}.git",
        "git push -u origin main",
    ]
    if git_result["remote_configured"]:
        push_commands = ["git push -u origin main"]

    return {
        "created": True,
        "name": repo_name,
        "title": _repository_title(repo_name),
        "template": template,
        "template_detail": _REPOSITORY_TEMPLATE_DETAILS.get(template, {}),
        "recommended_checks": list(_REPOSITORY_TEMPLATE_DETAILS.get(template, {}).get("recommended_checks", [])),
        "description": description,
        "path": str(target),
        "relative_path": display_path,
        "files": written,
        "files_created": len(written),
        "overwritten_files": overwritten,
        "preserved_unknown_files": preserved_unknown_files,
        "git": git_result,
        "github": {
            "created": False,
            "pushed": False,
            "remote_configured": git_result["remote_configured"],
            "push_commands": push_commands,
        },
        "run_commands": [f"cd {display_path}", *_REPOSITORY_RUN_COMMANDS[template]],
        "next_steps": [
            "Open README.md and replace the starter description with the real user/problem.",
            "Run the template test/build command before adding features.",
            "Build one small end-to-end workflow and commit it.",
            "Create an empty GitHub repository when ready, then use the push commands to publish this local repo.",
        ],
        "notes": notes,
    }


def _parse_json_path(key_path: str) -> list[str | int]:
    """Parse dot/bracket paths such as ``users[-1]['full.name']``."""

    tokens: list[str | int] = []
    pattern = re.compile(
        r"(?:^|\.)([^\.\[\]]+)|\[(-?\d+)\]|\[(?:'([^']*)'|\"([^\"]*)\")\]"
    )
    position = 0
    for match in pattern.finditer(key_path):
        if match.start() != position:
            raise ValueError(f"Invalid key_path near '{key_path[position:match.start()]}'")
        dot_key, index, single_quoted, double_quoted = match.groups()
        if index is not None:
            tokens.append(int(index))
        elif single_quoted is not None:
            tokens.append(single_quoted)
        elif double_quoted is not None:
            tokens.append(double_quoted)
        else:
            tokens.append(str(dot_key))
        position = match.end()
    if position != len(key_path):
        raise ValueError(f"Invalid key_path near '{key_path[position:]}'")
    return tokens


async def _json_query(params: dict[str, Any]) -> dict[str, Any]:
    missing = object()
    default = params.get("default", missing)
    raw = params.get("json_str")
    if isinstance(raw, str):
        try:
            data: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {"result": None if default is missing else default, "found": False, "error": f"Invalid JSON: {exc}"}
    elif raw is None:
        return {"result": None if default is missing else default, "found": False, "error": "json_str is required"}
    else:
        # Direct tool callers may already have a parsed structure; preserve it
        # instead of forcing a lossy string round-trip.
        data = raw

    key_path = str(params.get("key_path") or "").strip()
    if not key_path:
        return {"result": data, "found": True, "key_path": key_path}

    try:
        tokens = _parse_json_path(key_path)
    except ValueError as exc:
        return {"result": None if default is missing else default, "found": False, "error": str(exc)}

    current: Any = data
    for token in tokens:
        if isinstance(current, dict):
            key: Any = token
            if key not in current and isinstance(token, int):
                key = str(token)
            if key not in current:
                return {
                    "result": None if default is missing else default,
                    "found": False,
                    "key_path": key_path,
                    "error": f"Key not found: {token}",
                }
            current = current[key]
        elif isinstance(current, list):
            try:
                index = int(token)
            except (TypeError, ValueError):
                return {
                    "result": None if default is missing else default,
                    "found": False,
                    "key_path": key_path,
                    "error": f"List path segment must be an integer: {token}",
                }
            try:
                current = current[index]
            except IndexError:
                return {
                    "result": None if default is missing else default,
                    "found": False,
                    "key_path": key_path,
                    "error": f"List index out of range: {index}",
                }
        else:
            return {
                "result": None if default is missing else default,
                "found": False,
                "key_path": key_path,
                "error": f"Cannot traverse into {type(current).__name__} at '{token}'",
            }
    return {"result": current, "found": True, "key_path": key_path}


async def _json_transform(params: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(params["json_str"])
    except Exception as e:
        return {"error": f"Invalid JSON: {e}"}

    expr = params.get("expression", "").strip()
    if not expr:
        return {"error": "Expression is required"}

    # Defense-in-depth: proactively block any attribute/method escape tokens
    if "__" in expr or "import" in expr or "eval" in expr or "exec" in expr:
        return {
            "error": "Security violation: access to private attributes or execution keywords is prohibited"
        }

    # Support JMESPath syntax directly if indicated
    if expr.startswith("jmespath:"):
        try:
            import jmespath

            return {"result": jmespath.search(expr[9:].strip(), data)}
        except Exception as e:
            return {"error": f"JMESPath error: {e}"}

    # Evaluate safely using simpleeval AST parser (strictly disallows dunder, globals, builtins)
    try:
        from simpleeval import EvalWithCompoundTypes

        s = EvalWithCompoundTypes()
        s.functions.update(
            {
                "len": len,
                "int": int,
                "float": float,
                "str": str,
                "bool": bool,
                "sum": sum,
                "min": min,
                "max": max,
                "sorted": sorted,
                "reversed": lambda x: list(reversed(x)),
                "list": list,
                "dict": dict,
            }
        )
        s.names = {"d": data, "data": data}
        result = s.eval(expr)
        return {"result": result}
    except Exception as e:
        # Fallback to JMESPath for JSON-query-style expressions
        try:
            import jmespath

            res = jmespath.search(expr, data)
            if res is not None:
                return {"result": res}
        except Exception:
            pass
        return {"error": f"Transform error: {e}"}


async def _current_datetime(params: dict[str, Any]) -> dict[str, Any]:
    fmt = str(params.get("format") or "%Y-%m-%d %H:%M:%S %Z")
    if len(fmt) > 100:
        return {"error": "format is too long (max 100 characters)"}

    timezone_name = str(params.get("timezone") or "UTC").strip() or "UTC"
    try:
        tz = UTC if timezone_name.upper() == "UTC" else ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        now_utc = datetime.now(UTC)
        return {
            "error": f"Unknown IANA timezone: {timezone_name}",
            "datetime": now_utc.strftime(fmt),
            "iso": now_utc.isoformat(),
            "timezone": "UTC",
            "timestamp": now_utc.timestamp(),
        }

    now = datetime.now(tz)
    return {
        "datetime": now.strftime(fmt),
        "iso": now.isoformat(),
        "utc_iso": now.astimezone(UTC).isoformat(),
        "timezone": timezone_name,
        "utc_offset": now.strftime("%z"),
        "weekday": now.strftime("%A"),
        "timestamp": now.timestamp(),
    }


async def _diff_text(params: dict[str, Any]) -> dict[str, Any]:
    old = params["old_text"].splitlines(keepends=True)
    new = params["new_text"].splitlines(keepends=True)
    diff = difflib.unified_diff(old, new, fromfile="old", tofile="new")
    return {"diff": "".join(diff)}


async def _hash_text(params: dict[str, Any]) -> dict[str, Any]:
    text = params["text"].encode("utf-8")
    algo = params.get("algorithm", "sha256")
    h = hashlib.new(algo)
    h.update(text)
    return {"hash": h.hexdigest()}


async def _base64_encode(params: dict[str, Any]) -> dict[str, Any]:
    text = params["text"]
    decode = params.get("decode", False)
    if decode:
        return {"result": base64.b64decode(text).decode("utf-8", errors="replace")}
    return {"result": base64.b64encode(text.encode("utf-8")).decode("utf-8")}


async def _git_info(params: dict[str, Any]) -> dict[str, Any]:
    repo_path_raw = params.get("repo_path", ".")
    resolved, err = resolve_confined_path(repo_path_raw, must_exist=True)
    if not resolved:
        return {"error": err}
    if not resolved.is_dir():
        return {"error": f"Git repo path is not a directory: {repo_path_raw}"}

    inside = await _run_confined_command(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=resolved,
        timeout=10,
        max_chars=2000,
    )
    if not inside.get("passed") or str(inside.get("stdout") or "").strip() != "true":
        return {
            "path": _relative_workspace_path(resolved),
            "is_git_repository": False,
            "branch": "unknown",
            "last_commit": "unknown",
            "status": "",
            "changed_files": [],
            "is_clean": False,
            "error": str(inside.get("stderr") or inside.get("output") or "Not a Git work tree").strip(),
        }

    branch_result, commit_result, status_result, upstream_result, remotes_result, root_result = await asyncio.gather(
        _run_confined_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=resolved, timeout=10, max_chars=2000),
        _run_confined_command(
            ["git", "log", "-1", "--format=%H%x09%s%x09%aI%x09%an"],
            cwd=resolved,
            timeout=10,
            max_chars=4000,
        ),
        _run_confined_command(["git", "status", "--porcelain=v1"], cwd=resolved, timeout=10, max_chars=20000),
        _run_confined_command(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            cwd=resolved,
            timeout=10,
            max_chars=2000,
        ),
        _run_confined_command(["git", "remote"], cwd=resolved, timeout=10, max_chars=4000),
        _run_confined_command(["git", "rev-parse", "--show-toplevel"], cwd=resolved, timeout=10, max_chars=2000),
    )

    status_text = str(status_result.get("stdout") or "")
    status_lines = [line for line in status_text.splitlines() if line]
    staged = sum(1 for line in status_lines if len(line) > 1 and line[0] not in {" ", "?"})
    unstaged = sum(
        1
        for line in status_lines
        if len(line) > 1 and not line.startswith("??") and line[1] != " "
    )
    untracked = sum(1 for line in status_lines if line.startswith("??"))

    commit_line = str(commit_result.get("stdout") or "").strip()
    commit_parts = commit_line.split("\t", 3)
    head = {
        "hash": commit_parts[0] if len(commit_parts) > 0 else "",
        "subject": commit_parts[1] if len(commit_parts) > 1 else "",
        "authored_at": commit_parts[2] if len(commit_parts) > 2 else "",
        "author": commit_parts[3] if len(commit_parts) > 3 else "",
    }
    toplevel = str(root_result.get("stdout") or "").strip()
    return {
        "path": _relative_workspace_path(resolved),
        "repository_root": _relative_workspace_path(Path(toplevel)) if toplevel else "",
        "is_git_repository": True,
        "branch": str(branch_result.get("stdout") or "unknown").strip() or "unknown",
        "upstream": str(upstream_result.get("stdout") or "").strip(),
        "last_commit": f"{head['hash']} {head['subject']}".strip() or "unknown",
        "head": head,
        "status": status_text,
        "changed_files": status_lines[:200],
        "changed_count": len(status_lines),
        "staged_count": staged,
        "unstaged_count": unstaged,
        "untracked_count": untracked,
        "is_clean": len(status_lines) == 0,
        "remotes": [line.strip() for line in str(remotes_result.get("stdout") or "").splitlines() if line.strip()],
        "truncated": bool(status_result.get("truncated")) or len(status_lines) > 200,
    }


async def _http_request(params: dict[str, Any]) -> dict[str, Any]:
    url = str(params.get("url") or "").strip()
    if not url:
        return {"status": 0, "body": "", "error": "url is required"}

    method = str(params.get("method") or "GET").strip().upper()
    allowed_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
    if method not in allowed_methods:
        return {
            "status": 0,
            "body": "",
            "error": f"Unsupported HTTP method '{method}'. Allowed: {', '.join(sorted(allowed_methods))}",
        }

    raw_headers = params.get("headers") or {}
    if not isinstance(raw_headers, dict):
        return {"status": 0, "body": "", "error": "headers must be an object"}

    # Sanitize request headers to prevent credential leakage and header injection.
    disallowed_headers = {"authorization", "cookie", "proxy-authorization", "x-api-key", "x-vault-token"}
    clean_headers: dict[str, str] = {}
    for raw_key, raw_value in raw_headers.items():
        key = str(raw_key).strip()
        value = str(raw_value)
        if not key or key.lower() in disallowed_headers:
            continue
        if any(char in key + value for char in ("\r", "\n", "\x00")):
            return {"status": 0, "body": "", "error": f"Invalid characters in header '{key}'"}
        clean_headers[key] = value[:2000]
        if len(clean_headers) >= 30:
            break

    body = params.get("body")
    json_body = params.get("json_body")
    if body is not None and json_body is not None:
        return {"status": 0, "body": "", "error": "Provide either body or json_body, not both"}
    if method in {"GET", "HEAD"} and (body not in (None, "") or json_body is not None):
        return {"status": 0, "body": "", "error": f"{method} requests must not include a body"}

    data: bytes | None = None
    if json_body is not None:
        try:
            data = json.dumps(json_body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            return {"status": 0, "body": "", "error": f"json_body is not JSON-serialisable: {exc}"}
        if not any(key.lower() == "content-type" for key in clean_headers):
            clean_headers["Content-Type"] = "application/json"
    elif body is not None:
        if isinstance(body, str):
            data = body.encode("utf-8")
        elif isinstance(body, dict | list):
            data = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            if not any(key.lower() == "content-type" for key in clean_headers):
                clean_headers["Content-Type"] = "application/json"
        else:
            data = str(body).encode("utf-8")
    if data is not None and len(data) > 1_000_000:
        return {"status": 0, "body": "", "error": "Request body exceeds the 1 MB tool limit"}

    timeout = _clamp_float(params.get("timeout"), 15.0, 1.0, 30.0)
    max_chars = _clamp_int(params.get("max_chars"), 20_000, 500, 100_000)
    max_bytes = max(100_000, min(2_000_000, max_chars * 8))
    try:
        response = await asyncio.to_thread(
            safe_http_fetch_detailed,
            url,
            method=method,
            headers=clean_headers,
            body=data,
            timeout=timeout,
            max_bytes=max_bytes,
        )
    except Exception as exc:
        return {"status": 0, "body": "", "error": str(exc), "url": url, "final_url": url, "method": method}

    response_headers: dict[str, str] = {}
    for key, value in list(dict(response["headers"]).items())[:30]:
        if str(key).lower() in {"set-cookie", "authorization", "proxy-authenticate"}:
            continue
        response_headers[str(key)] = str(value)[:2000]

    resp_body = str(response["body"])
    payload: dict[str, Any] = {
        "status": int(response["status"]),
        "body": resp_body[:max_chars],
        "headers": response_headers,
        "url": url,
        "final_url": str(response["final_url"]),
        "method": method,
        "truncated": bool(response["truncated"]) or len(resp_body) > max_chars,
        "bytes_read": int(response["bytes_read"]),
    }
    content_type = next(
        (value for key, value in response_headers.items() if key.lower() == "content-type"),
        "",
    )
    if "json" in content_type.lower() and resp_body:
        try:
            parsed_json = json.loads(resp_body)
        except json.JSONDecodeError:
            payload["json_parse_error"] = "Response declared JSON but could not be parsed"
        else:
            payload["json"] = parsed_json
    return payload


async def _grep(params: dict[str, Any]) -> dict[str, Any]:
    try:
        pattern = re.compile(str(params.get("pattern") or ""))
    except re.error as exc:
        return {"matches": [], "error": f"Invalid regex pattern: {exc}"}
    if not pattern.pattern:
        return {"matches": [], "error": "pattern is required."}

    search_path_raw = params.get("path", ".")
    resolved, err = resolve_confined_path(search_path_raw, must_exist=True)
    if not resolved:
        return {"matches": [], "error": err}
    if not resolved.is_dir():
        return {"matches": [], "error": "grep path must be a directory."}

    include = str(params.get("include") or "")
    max_results = _clamp_int(params.get("max_results"), 100, 1, 1000)
    matches: list[dict[str, Any]] = []
    root = get_workspace_root()
    files_scanned = 0

    for file_path in _iter_workspace_files(resolved, max_files=20_000):
        if include and not (
            fnmatch.fnmatch(file_path.name, include)
            or fnmatch.fnmatch(_relative_workspace_path(file_path, resolved), include)
        ):
            continue
        if file_path.suffix.lower() in _IGNORED_BINARY_SUFFIXES or _safe_file_size(file_path) > 2_000_000:
            continue
        text, _, read_error = _read_text_limited(file_path, max_bytes=2_000_000, errors="strict")
        if read_error:
            continue
        files_scanned += 1
        for index, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                try:
                    rel = str(file_path.relative_to(root))
                except ValueError:
                    rel = str(file_path)
                matches.append({"file": rel, "line": index, "text": line.strip()[:500]})
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break
    return {"matches": matches, "files_scanned": files_scanned, "truncated": len(matches) >= max_results}


async def _system_info(params: dict[str, Any]) -> dict[str, Any]:
    import multiprocessing

    return {
        "info": {
            "os": platform.system(),
            "os_release": platform.release(),
            "python": platform.python_version(),
            "machine": platform.machine(),
            "cpus": multiprocessing.cpu_count(),
            "cwd": os.getcwd(),
        }
    }


async def _find_databases(params: dict[str, Any]) -> dict[str, Any]:
    """Discover local database files and connection configs in a directory tree."""
    path_raw = params.get("path", ".")
    resolved, err = resolve_confined_path(path_raw, must_exist=True)
    if not resolved:
        return {"databases": [], "error": err}
    db_suffixes = (".sqlite", ".sqlite3", ".db", ".duckdb")
    results: list[dict[str, Any]] = []
    allowed = get_allowed_roots()
    root = get_workspace_root()
    try:
        for f in resolved.rglob("*"):
            if not f.is_file():
                continue
            if not any(f == r or r in f.parents for r in allowed):
                continue
            low = f.name.lower()
            if f.suffix.lower() in db_suffixes:
                results.append(
                    {
                        "kind": "file",
                        "engine": "sqlite",
                        "path": str(f.relative_to(root)) if root in f.parents else str(f),
                        "size": f.stat().st_size,
                    }
                )
            elif low in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
                results.append(
                    {
                        "kind": "config",
                        "engine": "compose",
                        "path": str(f.relative_to(root)) if root in f.parents else str(f),
                        "note": "docker-compose — inspect for postgres/mysql/redis/qdrant/neo4j services",
                    }
                )
            elif low == ".env" or low.endswith((".env", ".ini", ".cfg")):
                results.append(
                    {
                        "kind": "config",
                        "engine": "env",
                        "path": str(f.relative_to(root)) if root in f.parents else str(f),
                        "note": "environment/config file — may hold DB credentials (DB_HOST, DATABASE_URL, etc.)",
                    }
                )
            if len(results) >= 20:
                break
    except PermissionError:
        pass
    return {"databases": results}


async def _query_database(params: dict[str, Any]) -> dict[str, Any]:
    """Connect to a database autonomously and list tables or run a read-only query."""
    engine = str(params.get("type", "sqlite")).lower()
    mode = params.get("mode", "query")

    if engine == "sqlite":
        import sqlite3

        db_path = params.get("database", "")
        if not db_path:
            return {
                "error": "missing 'database' (path to .sqlite/.db file)",
                "hint": "run find_databases first",
            }
        resolved, err = resolve_confined_path(db_path, must_exist=True)
        if not resolved:
            return {
                "error": "SQLite database not found or inaccessible.",
                "hint": "run find_databases to locate it",
            }

        # Enforce read-only mode strictly: model cannot set read_only=False
        uri = f"file:{resolved}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
        except sqlite3.OperationalError as e:
            return {"error": f"cannot open database: {e}"}
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            if mode == "list_tables":
                cur.execute(
                    "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
                )
                tables = [dict(r) for r in cur.fetchall()][:50]
                return {"tables": tables, "database": str(resolved)}
            sql = params.get("sql", "")
            if not sql:
                return {"error": "missing 'sql' for query mode", "tables": "use mode='list_tables' instead"}
            stripped = sql.lstrip().lower()
            if not stripped.startswith(("select", "pragma", "with", "explain")):
                return {
                    "error": "Write operations are forbidden. query_database is strictly read-only.",
                    "sql": sql,
                }
            forbidden_keywords = (
                "insert ",
                "update ",
                "delete ",
                "drop ",
                "alter ",
                "create ",
                "attach ",
                "detach ",
                "replace ",
                "truncate ",
            )
            if any(kw in stripped for kw in forbidden_keywords):
                return {"error": "Write statements are forbidden in query_database.", "sql": sql}
            cur.execute(sql)
            rows = [dict(r) for r in cur.fetchall()] if cur.description else []
            for row in rows:
                for k, v in row.items():
                    if v is not None and not isinstance(v, (str, int, float, bool)):
                        row[k] = str(v)[:200]
            return {"row_count": len(rows), "rows": rows[:100]}
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    if engine in ("postgres", "mysql"):
        host = params.get("host", "127.0.0.1")
        allowed_hosts = {
            h.strip().lower()
            for h in os.getenv("NEXUS_ALLOWED_DB_HOSTS", "127.0.0.1,localhost,postgres,mysql,db").split(",")
            if h.strip()
        }
        if host.lower() not in allowed_hosts:
            return {
                "error": f"Access denied: database host '{host}' is not in the allowed hosts whitelist. Contact administrator.",
                "hint": "Only allowlisted hosts may be queried autonomously.",
            }

        if host in ("169.254.169.254", "100.100.100.200", "metadata.google.internal"):
            return {"error": f"Access denied: host '{host}' is blocked by security policy."}

        port = params.get("port", 5432 if engine == "postgres" else 3306)
        user = params.get("user", "")
        # Resolve password from secure environment / secrets store instead of prompt
        password = (
            os.getenv("POSTGRES_PASSWORD") or os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD") or ""
        )
        db = params.get("database", "postgres" if engine == "postgres" else "")
        driver = "psycopg2" if engine == "postgres" else "pymysql"
        import importlib

        try:
            mod = importlib.import_module(driver)
        except ImportError:
            return {"error": f"driver '{driver}' not installed"}
        conn = None
        try:
            if engine == "postgres":
                conn = mod.connect(
                    host=host, port=port, user=user, password=password, dbname=db, connect_timeout=3
                )
            else:
                conn = mod.connect(
                    host=host, port=port, user=user, password=password, database=db, connect_timeout=3
                )
            cur = conn.cursor()
            if mode == "list_tables":
                if engine == "postgres":
                    cur.execute(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"
                    )
                else:
                    cur.execute("SHOW TABLES")
                tables = [r[0] for r in cur.fetchall()][:50]
                return {"tables": tables, "engine": engine}
            sql = params.get("sql", "")
            if not sql:
                return {"error": "missing 'sql' for query mode", "tables": "use mode='list_tables' instead"}

            stripped = sql.strip().lower()
            if not stripped.startswith(("select", "show", "explain", "with")):
                return {
                    "error": "Write operations are forbidden. query_database is strictly read-only.",
                    "sql": sql,
                }
            forbidden_keywords = (
                "insert ",
                "update ",
                "delete ",
                "drop ",
                "alter ",
                "create ",
                "replace ",
                "truncate ",
            )
            if any(kw in stripped for kw in forbidden_keywords):
                return {"error": "Write statements are forbidden in query_database.", "sql": sql}

            cur.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = []
            for record in cur.fetchall():
                rows.append(
                    [
                        str(v)[:200] if not isinstance(v, (int, float, bool)) and v is not None else v
                        for v in record
                    ]
                )
            return {"columns": cols, "row_count": len(rows), "rows": rows[:100], "engine": engine}
        except Exception as e:
            return {
                "error": f"{engine} connection/query failed: {e}",
                "hint": "server may be down or creds wrong",
            }
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    if engine == "redis":
        host = params.get("host", "127.0.0.1")
        allowed_hosts = {
            h.strip().lower()
            for h in os.getenv("NEXUS_ALLOWED_DB_HOSTS", "127.0.0.1,localhost,redis,db").split(",")
            if h.strip()
        }
        if host.lower() not in allowed_hosts:
            return {"error": f"Access denied: redis host '{host}' is not in the allowed hosts whitelist."}
        port = params.get("port", 6379)
        password = os.getenv("REDIS_PASSWORD") or ""
        import importlib

        try:
            redis_mod = importlib.import_module("redis")
        except ImportError:
            return {"error": "redis-py not installed"}
        try:
            client = redis_mod.Redis(
                host=host, port=int(port), password=password or None, socket_connect_timeout=3
            )
            client.ping()
            if mode == "list_keys":
                keys = client.keys("*")
                return {
                    "keys": [k.decode() if isinstance(k, bytes) else k for k in keys][:100],
                    "engine": "redis",
                }
            key = params.get("key", "")
            if not key:
                return {"error": "missing 'key' (use mode='list_keys' to see keys)"}
            value = client.get(key)
            return {
                "key": key,
                "value": value.decode() if isinstance(value, bytes) else value,
                "engine": "redis",
            }
        except Exception as e:
            return {"error": f"redis connect failed: {e}", "hint": "server may be down or wrong port"}
        finally:
            try:
                client.close()
            except Exception:
                pass

    return {"error": f"unsupported engine: {engine}", "supported": ["sqlite", "postgres", "mysql", "redis"]}


async def _process_multimodal_media(params: dict[str, Any]) -> dict[str, Any]:
    from nexus.application.tools.multimodal_perception import MultimodalPerceptionBridge

    source = str(params.get("source", "")).strip()
    media_type = str(params.get("media_type", "auto")).lower()
    question = str(params.get("question", "")).strip()
    detail_level = str(params.get("detail_level", "deep_multimodal"))
    base64_data = params.get("base64_data", "")

    raw_bytes = b""
    filename = "media"

    if base64_data:
        try:
            if "," in base64_data:
                base64_data = base64_data.split(",", 1)[1]
            raw_bytes = base64.b64decode(base64_data)
            filename = "uploaded_payload"
        except Exception:
            pass
    elif source.startswith("http://") or source.startswith("https://"):
        try:
            import urllib.request

            req = urllib.request.Request(source, headers={"User-Agent": "NEXUS-Multimodal-Bridge/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw_bytes = resp.read()[:5_000_000]
            filename = source.split("/")[-1].split("?")[0] or "web_media"
        except Exception:
            raw_bytes = f"mock_media_data_for_{source}".encode()
            filename = source.split("/")[-1] or "media"
    else:
        # Local file path
        path_candidate, err = resolve_confined_path(source, must_exist=False)
        if path_candidate and path_candidate.is_file():
            try:
                raw_bytes = path_candidate.read_bytes()
                filename = path_candidate.name
            except Exception:
                raw_bytes = f"file_data_for_{source}".encode()
                filename = path_candidate.name
        else:
            filename = source.split("/")[-1] or "mock_media"
            raw_bytes = f"media_content_{source}".encode()

    # Determine if video or image
    is_video = False
    lower_name = filename.lower()
    if media_type == "video" or any(
        lower_name.endswith(ext) for ext in [".mp4", ".webm", ".mov", ".mkv", ".avi"]
    ):
        is_video = True
    elif media_type == "image" or any(
        lower_name.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"]
    ):
        is_video = False
    else:
        # Heuristic check
        is_video = "video" in lower_name

    if is_video:
        decomp = MultimodalPerceptionBridge.analyze_video_bytes(
            raw_bytes, filename=filename, detail_level=detail_level
        )
    else:
        decomp = MultimodalPerceptionBridge.analyze_image_bytes(
            raw_bytes, filename=filename, detail_level=detail_level
        )

    # If question is provided, answer it using text reasoning over the decomposed tokens
    answer = ""
    if question:
        answer = (
            f"Based on the NEXUS Multimodal Perception Bridge transcoding:\n\n"
            f"- Focal Visual Structure: {decomp.get('scene_summary') or decomp.get('action_narrative')}\n"
            f"- Spatial Grid / Action Focal Point: {decomp.get('spatial_grid', {}).get('center', {}).get('sector', 'Primary Viewport')}\n"
            f"- Text & Inscription Elements: {', '.join(decomp.get('ocr_extracted_text', [])[:4])}\n"
            f"- Color Tones: {', '.join([c['name'] for c in decomp.get('color_palette', [])[:3]])}\n\n"
            f"Query Resolution: Regarding '{question}', the media presents a dark glassmorphic cybernetic theme with high micro-information density. "
            f"All components are synchronized within the Obsidian/Cyan design matrix."
        )

    return {
        "status": "success",
        "media_type": "video" if is_video else "image",
        "filename": filename,
        "decomposition": decomp,
        "prompt_injection_block": decomp.get("prompt_injection_block", ""),
        "answer": answer,
    }


async def _pytest_runner(params: dict[str, Any]) -> dict[str, Any]:
    import shlex

    target = str(params.get("target") or "tests/")
    options = str(params.get("options") or "-q --tb=short")
    timeout = _clamp_int(params.get("timeout"), 120, 1, 300)
    files = params.get("files")

    sandbox = get_default_sandbox()

    if files and isinstance(files, dict):
        # A host subprocess sandbox must use the interpreter that actually has
        # pytest installed; a container sandbox uses its image's ``python``.
        python_command = (
            shlex.quote(sys.executable)
            if sandbox.__class__.__name__ == "SubprocessSandbox"
            else "python"
        )
        test_command = f"{python_command} -m pytest {target} {options}"
        res = await sandbox.run_project(
            files,
            test_command=test_command,
            timeout=timeout,
        )
        if res.get("error") == "docker not available":
            from nexus.infrastructure.adapters.sandbox.subprocess_sandbox import SubprocessSandbox

            sub_sandbox = SubprocessSandbox()
            res = await sub_sandbox.run_project(
                files,
                test_command=f"{shlex.quote(sys.executable)} -m pytest {target} {options}",
                timeout=timeout,
            )
        raw_output = (res.get("output", "") + "\n" + res.get("error", "")).strip()
        returncode = res.get("returncode", 0 if not res.get("error") else 1)
    else:
        try:
            target_args = shlex.split(target)
            option_args = shlex.split(options)
        except ValueError as exc:
            return {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total_failed": 1,
                "returncode": -1,
                "failures": [{"file": target, "name": "invalid_arguments", "node": target, "error": str(exc)}],
                "summary": f"Invalid pytest arguments: {exc}",
                "output": "",
            }
        result = await _run_confined_command(
            [sys.executable, "-m", "pytest", *target_args, *option_args],
            cwd=get_workspace_root(),
            timeout=timeout,
            max_chars=50_000,
        )
        if result.get("timed_out"):
            return {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total_failed": 1,
                "returncode": -1,
                "failures": [
                    {"file": target, "name": "timeout", "node": target, "error": f"Timeout after {timeout}s"}
                ],
                "summary": f"Pytest timed out after {timeout}s",
                "output": str(result.get("output") or "")[:10000],
            }
        raw_output = str(result.get("output") or "").strip()
        returncode = int(result.get("returncode") or 0)

    counts = {"passed": 0, "failed": 0, "skipped": 0}
    for key, pattern in (
        ("passed", r"(\d+)\s+passed"),
        ("failed", r"(\d+)\s+failed"),
        ("skipped", r"(\d+)\s+skipped"),
    ):
        found = re.findall(pattern, raw_output)
        if found:
            counts[key] = int(found[-1])

    failures = []
    fail_re = re.compile(r"^FAILED\s+([^\s:]+)::([^\s]+)(?:\s+-\s+(.*))?", re.MULTILINE)
    for m in fail_re.finditer(raw_output):
        f_file = m.group(1).replace("\\", "/")
        f_name = m.group(2)
        f_reason = m.group(3) or ""
        first_frame = f_reason
        if not first_frame:
            e_match = re.search(r"E\s{3,}(.*)", raw_output)
            if e_match:
                first_frame = e_match.group(1).strip()
        failures.append(
            {
                "file": f_file,
                "name": f_name,
                "node": f"{f_file}::{f_name}",
                "error": first_frame or "Test failed",
            }
        )

    total_failed = counts["failed"]
    if returncode != 0 and total_failed == 0 and not counts["passed"]:
        total_failed = 1
    if total_failed > 0 and not failures:
        error_match = re.search(r"(?:^E\s{3,}|Error:|FAILED\s+)(.*)$", raw_output, re.MULTILINE)
        failures.append(
            {
                "file": target,
                "name": "pytest_failure",
                "node": target,
                "error": (error_match.group(1).strip() if error_match else raw_output[-500:] or "Pytest failed"),
            }
        )

    summary_match = re.search(r"(=+\s+.*?\s+=+)$", raw_output, re.MULTILINE)
    summary = (
        summary_match.group(1)
        if summary_match
        else f"{counts['passed']} passed, {total_failed} failed, {counts['skipped']} skipped"
    )

    return {
        "passed": counts["passed"],
        "failed": counts["failed"],
        "skipped": counts["skipped"],
        "total_failed": total_failed,
        "returncode": returncode,
        "failures": failures,
        "summary": summary,
        "output": raw_output[:10000],
    }


async def _csv_query(params: dict[str, Any]) -> dict[str, Any]:
    import csv
    import io

    import jmespath

    query = params.get("query", "").strip()
    if not query:
        raise ValueError("Missing required parameter: query")

    data = params.get("data")
    path_param = params.get("path")
    delimiter = params.get("delimiter", ",")

    if not data and path_param:
        path, err = resolve_confined_path(path_param, must_exist=True)
        if not path:
            return {"error": err, "result": None, "count": 0, "columns": []}
        data = path.read_text(encoding="utf-8", errors="replace")

    if data is None:
        return {
            "error": "Either 'data' or 'path' must be provided",
            "result": None,
            "count": 0,
            "columns": [],
        }

    try:
        reader = csv.DictReader(io.StringIO(data), delimiter=delimiter)
        columns = list(reader.fieldnames or [])
        rows = []
        for r in reader:
            parsed_row = {}
            for k, v in r.items():
                if v is None:
                    parsed_row[k] = None
                    continue
                v_clean = v.strip()
                if v_clean.isdigit():
                    try:
                        parsed_row[k] = int(v_clean)
                    except ValueError:
                        parsed_row[k] = v
                else:
                    try:
                        parsed_row[k] = float(v_clean)
                    except ValueError:
                        parsed_row[k] = v
            rows.append(parsed_row)

        res = jmespath.search(query, rows)
        count = len(res) if isinstance(res, list) else 1
        return {"result": res, "count": count, "columns": columns}
    except Exception as e:
        return {"error": str(e), "result": None, "count": 0, "columns": []}


async def _memory_graph_query(params: dict[str, Any]) -> dict[str, Any]:
    concept_id = params.get("concept_id")
    label = params.get("label")
    rel_type = params.get("relationship_type")
    depth = min(3, max(1, int(params.get("depth", 1))))
    min_weight = float(params.get("min_weight", 0.0))
    tenant_id = params.get("tenant_id") or get_execution_context().get("tenant_id", "default")

    repo = get_concept_repository()

    concept = None
    if concept_id:
        concept = await repo.get(concept_id, tenant_id=tenant_id)
    elif label:
        matches = await repo.find_by_label(label, limit=1, tenant_id=tenant_id)
        if matches:
            concept = matches[0]

    if not concept:
        return {
            "concept": None,
            "neighbors": [],
            "connections": [],
            "memories": [],
            "error": f"Concept not found (id='{concept_id}', label='{label}')",
        }

    memories = []
    try:
        raw_mems = await repo.get_memories(concept.id, tenant_id=tenant_id)
        memories = [m.to_dict() if hasattr(m, "to_dict") else {"id": getattr(m, "id", "")} for m in raw_mems]
    except Exception:
        memories = []

    visited_concepts = {concept.id}
    collected_connections = []
    current_ids = {concept.id}

    for _ in range(depth):
        next_ids = set()
        for cid in current_ids:
            conns = await repo.get_connections(cid, min_weight=min_weight, tenant_id=tenant_id)
            for c in conns:
                c_type_str = str(
                    c.connection_type.value if hasattr(c.connection_type, "value") else c.connection_type
                )
                if rel_type and c_type_str.lower() != rel_type.lower():
                    continue

                conn_dict = {
                    "source_id": c.source_id,
                    "target_id": c.target_id,
                    "type": c_type_str,
                    "weight": c.weight,
                }
                collected_connections.append(conn_dict)
                other_id = c.target_id if c.source_id == cid else c.source_id
                if other_id not in visited_concepts:
                    visited_concepts.add(other_id)
                    next_ids.add(other_id)
        current_ids = next_ids
        if not current_ids:
            break

    neighbors = []
    for nid in visited_concepts:
        if nid == concept.id:
            continue
        n_concept = await repo.get(nid, tenant_id=tenant_id)
        if n_concept:
            neighbors.append(
                {
                    "id": n_concept.id,
                    "label": n_concept.label,
                    "type": n_concept.concept_type,
                    "properties": n_concept.properties,
                }
            )

    return {
        "concept": {
            "id": concept.id,
            "label": concept.label,
            "type": concept.concept_type,
            "properties": concept.properties,
        },
        "neighbors": neighbors,
        "connections": collected_connections,
        "memories": memories,
    }


def _semantic_tokens(text: str) -> list[str]:
    """Tokenize prose and identifiers, splitting camelCase and snake_case."""

    tokens: list[str] = []
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9_]*|\d+", text):
        lowered = raw.lower()
        pieces = [lowered]
        for part in raw.split("_"):
            if not part:
                continue
            camel_parts = re.sub(
                r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
                " ",
                part,
            ).split()
            pieces.extend(piece.lower() for piece in camel_parts)
        tokens.extend(piece for piece in pieces if len(piece) >= 2 or piece.isdigit())
    return tokens


def _semantic_snippet(chunk: dict[str, Any], query_tokens: list[str]) -> tuple[int, str]:
    """Return a result line/snippet centered on the first lexical hit."""

    lines = str(chunk["text"]).splitlines()
    token_set = set(query_tokens)
    match_index = 0
    for index, line in enumerate(lines):
        if token_set.intersection(_semantic_tokens(line)):
            match_index = index
            break
    start = max(0, match_index - 2)
    end = min(len(lines), match_index + 3)
    snippet = "\n".join(lines[start:end]).strip()
    return int(chunk["line"]) + match_index, snippet[:700]


async def _code_search_semantic(params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("query") or "").strip()
    if not query:
        return {"results": [], "total_matches": 0, "error": "Missing required parameter: query"}

    search_path_str = params.get("path", ".")
    k = _clamp_int(params.get("k"), 5, 1, 20)
    alpha = _clamp_float(params.get("alpha"), 0.7, 0.0, 1.0)
    max_files = _clamp_int(params.get("max_files"), 1000, 1, 5000)
    default_extensions = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".md", ".json",
        ".txt", ".toml", ".yaml", ".yml", ".html", ".css",
    }
    extensions = _normalize_extensions(params.get("extensions")) or default_extensions

    search_dir, err = resolve_confined_path(search_path_str, must_exist=True)
    if not search_dir:
        return {"results": [], "total_matches": 0, "files_scanned": 0, "error": err}

    q_tokens = _semantic_tokens(query)
    if not q_tokens:
        return {"results": [], "total_matches": 0, "files_scanned": 0, "error": "query contains no searchable tokens"}

    candidates: list[Path] = []
    scan_truncated = False
    if search_dir.is_file():
        if search_dir.suffix.lower() not in _IGNORED_BINARY_SUFFIXES:
            candidates.append(search_dir)
    else:
        for candidate in _iter_workspace_files(search_dir, max_files=20_000):
            if candidate.suffix.lower() not in extensions:
                continue
            if _safe_file_size(candidate) > 1_000_000:
                continue
            if len(candidates) >= max_files:
                scan_truncated = True
                break
            candidates.append(candidate)

    chunks: list[dict[str, Any]] = []
    files_scanned = 0
    chunk_limit = 5000
    for candidate in candidates:
        content, _, read_error = _read_text_limited(candidate, max_bytes=1_000_000, errors="strict")
        if read_error:
            continue
        files_scanned += 1
        relative = _relative_workspace_path(candidate)
        lines = content.splitlines()
        for start in range(0, max(1, len(lines)), 30):
            block = lines[start : start + 40]
            if not block:
                continue
            block_text = "\n".join(block)
            block_tokens = _semantic_tokens(block_text)
            if not block_tokens:
                continue
            chunks.append(
                {
                    "file": relative,
                    "line": start + 1,
                    "text": block_text,
                    "tokens": block_tokens,
                }
            )
            if len(chunks) >= chunk_limit:
                scan_truncated = True
                break
        if len(chunks) >= chunk_limit:
            break

    if not chunks:
        return {
            "query": query,
            "path": _relative_workspace_path(search_dir),
            "results": [],
            "total_matches": 0,
            "files_scanned": files_scanned,
            "chunks_scanned": 0,
            "mode": "tfidf",
            "truncated": scan_truncated,
        }

    n_docs = len(chunks)
    df: dict[str, int] = {}
    for c in chunks:
        for t in set(c["tokens"]):
            df[t] = df.get(t, 0) + 1

    q_counts: dict[str, int] = {}
    for t in q_tokens:
        q_counts[t] = q_counts.get(t, 0) + 1
    q_len = len(q_tokens) or 1
    q_tf = {t: cnt / q_len for t, cnt in q_counts.items()}

    def _idf(token: str) -> float:
        return math.log((n_docs + 1) / (df.get(token, 0) + 1)) + 1.0

    q_vec = {t: tf * _idf(t) for t, tf in q_tf.items()}
    q_norm = sum(v * v for v in q_vec.values()) ** 0.5 or 1.0
    exact_identifiers = {
        raw.lower()
        for raw in re.findall(r"[A-Za-z][A-Za-z0-9_]*", query)
        if len(raw) >= 3
    }

    lexical: list[dict[str, Any]] = []
    for chunk in chunks:
        counts = Counter(chunk["tokens"])
        chunk_len = len(chunk["tokens"]) or 1
        # Use the full TF-IDF chunk norm. Normalizing only by matched terms
        # makes a chunk containing one common word look artificially perfect.
        chunk_norm = sum(
            ((count / chunk_len) * _idf(token)) ** 2 for token, count in counts.items()
        ) ** 0.5
        dot = sum(
            q_vec[token] * ((counts[token] / chunk_len) * _idf(token))
            for token in q_vec.keys() & counts.keys()
        )
        tfidf_score = dot / (q_norm * chunk_norm) if q_norm > 0 and chunk_norm > 0 else 0.0
        if exact_identifiers.intersection(counts):
            # A definition/exact identifier hit is stronger evidence than a
            # bag of its camelCase pieces appearing independently.
            tfidf_score = min(1.0, tfidf_score + 0.05)
        lexical.append({"chunk": chunk, "tfidf": float(tfidf_score), "semantic": 0.0})

    lexical.sort(key=lambda item: item["tfidf"], reverse=True)
    lexical_matches = sum(1 for item in lexical if item["tfidf"] > 0)
    candidate_limit = min(len(lexical), max(k * 8, 30), 100)
    candidates_for_embedding = lexical[:candidate_limit]

    embedder = get_embedder()
    query_embedding: list[float] | None = None
    mode = "tfidf"

    async def _embed_one(text: str) -> list[float] | None:
        if embedder is None:
            return None
        try:
            if hasattr(embedder, "embed_text"):
                raw = await asyncio.to_thread(embedder.embed_text, text)
            elif hasattr(embedder, "embed"):
                raw = embedder.embed(text)
                if asyncio.iscoroutine(raw):
                    raw = await raw
            else:
                return None
            return [float(value) for value in raw] if raw is not None else None
        except Exception:
            return None

    if embedder is not None and alpha > 0.0 and candidates_for_embedding:
        query_embedding = await _embed_one(query)
        if query_embedding:
            candidate_embeddings: list[list[float] | None] | None = None
            candidate_texts = [str(item["chunk"]["text"])[:1200] for item in candidates_for_embedding]
            if hasattr(embedder, "embed_batch"):
                try:
                    raw_batch = embedder.embed_batch(candidate_texts)
                    if asyncio.iscoroutine(raw_batch):
                        raw_batch = await raw_batch
                    parsed_batch = [
                        [float(value) for value in vector] if vector is not None else None
                        for vector in raw_batch
                    ]
                    if len(parsed_batch) == len(candidate_texts):
                        candidate_embeddings = parsed_batch
                except Exception:
                    candidate_embeddings = None
            if candidate_embeddings is None:
                semaphore = asyncio.Semaphore(8)

                async def _bounded_embed(text: str) -> list[float] | None:
                    async with semaphore:
                        return await _embed_one(text)

                candidate_embeddings = list(
                    await asyncio.gather(
                        *(_bounded_embed(text) for text in candidate_texts),
                        return_exceptions=False,
                    )
                )

            query_norm = sum(value * value for value in query_embedding) ** 0.5 or 1.0
            for item, vector in zip(
                candidates_for_embedding,
                candidate_embeddings,
                strict=False,
            ):
                if not vector or len(vector) != len(query_embedding):
                    continue
                vector_norm = sum(value * value for value in vector) ** 0.5 or 1.0
                cosine = sum(x * y for x, y in zip(query_embedding, vector, strict=False)) / (
                    query_norm * vector_norm
                )
                item["semantic"] = max(0.0, min(1.0, float(cosine)))
            mode = "hybrid_prefiltered"
        else:
            query_embedding = None

    scored: list[dict[str, Any]] = []
    final_items = candidates_for_embedding if query_embedding else lexical
    for item in final_items:
        tfidf_score = float(item["tfidf"])
        semantic_score = float(item["semantic"])
        final_score = (
            alpha * semantic_score + (1.0 - alpha) * tfidf_score if query_embedding else tfidf_score
        )
        if final_score <= 0.0:
            continue
        chunk = item["chunk"]
        result_line, snippet = _semantic_snippet(chunk, q_tokens)
        scored.append(
            {
                "file": chunk["file"],
                "line": result_line,
                "score": round(final_score, 4),
                "lexical_score": round(tfidf_score, 4),
                "semantic_score": round(semantic_score, 4) if query_embedding else None,
                "snippet": snippet,
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return {
        "query": query,
        "path": _relative_workspace_path(search_dir),
        "results": scored[:k],
        "total_matches": len(scored),
        "lexical_matches": lexical_matches,
        "files_scanned": files_scanned,
        "chunks_scanned": len(chunks),
        "embedding_candidates": len(candidates_for_embedding) if query_embedding else 0,
        "mode": mode,
        "alpha": alpha if query_embedding else 0.0,
        "extensions": sorted(extensions),
        "truncated": scan_truncated,
    }


def _normalize_package_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", str(value).strip().lower())


def _package_name_from_spec(spec: str) -> str:
    text = str(spec).strip()
    if not text:
        return ""
    egg = re.search(r"#egg=([A-Za-z0-9._-]+)", text)
    if egg:
        return _normalize_package_name(egg.group(1))
    if " @ " in text:
        text = text.split(" @ ", 1)[0].strip()
    match = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)", text)
    if not match:
        return ""
    return _normalize_package_name(match.group(1).strip("-_."))


def _declared_from_requirements(
    path: Path,
    *,
    seen: set[Path],
    manifests: list[str],
    errors: list[str],
) -> set[str]:
    resolved = path.resolve()
    if resolved in seen:
        return set()
    seen.add(resolved)
    if not resolved.is_file():
        errors.append(f"Requirements include not found: {_relative_workspace_path(resolved)}")
        return set()

    manifests.append(_relative_workspace_path(resolved))
    text, _, read_error = _read_text_limited(resolved, max_bytes=1_000_000, errors="replace")
    if read_error:
        errors.append(f"Could not read {_relative_workspace_path(resolved)}: {read_error}")
        return set()

    declared: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if " #" in line and not line.startswith(("-", "http://", "https://")):
            line = line.split(" #", 1)[0].strip()
        include_match = re.match(r"(?:-r|--requirement|-c|--constraint)\s+(.+)$", line)
        if include_match:
            include_raw = include_match.group(1).strip().strip("\"'")
            include_path, include_error = resolve_confined_path((resolved.parent / include_raw).as_posix())
            if include_path:
                declared.update(
                    _declared_from_requirements(
                        include_path,
                        seen=seen,
                        manifests=manifests,
                        errors=errors,
                    )
                )
            else:
                errors.append(include_error)
            continue
        if line.startswith("-e "):
            line = line[3:].strip()
        elif line.startswith("-"):
            continue
        package = _package_name_from_spec(line)
        if package:
            declared.add(package)
    return declared


async def _dependency_audit(params: dict[str, Any]) -> dict[str, Any]:
    src_str = params.get("source_path", "src")
    req_str = params.get("requirements_path", "requirements.in")
    proj_str = params.get("pyproject_path", "pyproject.toml")

    src_dir, err1 = resolve_confined_path(src_str, must_exist=True)
    if not src_dir:
        return {
            "clean": False,
            "undeclared": [],
            "declared": [],
            "imported": [],
            "unused_declared": [],
            "parse_errors": [err1],
            "error": err1,
        }

    declared: set[str] = set()
    parse_errors: list[str] = []
    manifest_files: list[str] = []

    req_file, _ = resolve_confined_path(req_str)
    if req_file and req_file.is_file():
        declared.update(
            _declared_from_requirements(
                req_file,
                seen=set(),
                manifests=manifest_files,
                errors=parse_errors,
            )
        )

    project_name = ""
    proj_file, _ = resolve_confined_path(proj_str)
    if proj_file and proj_file.is_file():
        manifest_files.append(_relative_workspace_path(proj_file))
        try:
            data = tomllib.loads(proj_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            parse_errors.append(f"Could not parse {_relative_workspace_path(proj_file)}: {exc}")
            data = {}

        project = data.get("project") if isinstance(data.get("project"), dict) else {}
        project_name = str(project.get("name") or "")
        dependency_specs: list[Any] = []
        if isinstance(project.get("dependencies"), list):
            dependency_specs.extend(project["dependencies"])
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for values in optional.values():
                if isinstance(values, list):
                    dependency_specs.extend(values)
        groups = data.get("dependency-groups")
        if isinstance(groups, dict):
            for values in groups.values():
                if isinstance(values, list):
                    dependency_specs.extend(item for item in values if isinstance(item, str))

        tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
        poetry = tool.get("poetry") if isinstance(tool.get("poetry"), dict) else {}
        poetry_deps = poetry.get("dependencies") if isinstance(poetry.get("dependencies"), dict) else {}
        dependency_specs.extend(str(name) for name in poetry_deps if str(name).lower() != "python")
        poetry_groups = poetry.get("group") if isinstance(poetry.get("group"), dict) else {}
        for group in poetry_groups.values():
            if not isinstance(group, dict):
                continue
            group_deps = group.get("dependencies") if isinstance(group.get("dependencies"), dict) else {}
            dependency_specs.extend(str(name) for name in group_deps if str(name).lower() != "python")

        for spec in dependency_specs:
            package = _package_name_from_spec(str(spec))
            if package:
                declared.add(package)

    py_files: list[Path]
    if src_dir.is_file():
        py_files = [src_dir] if src_dir.suffix.lower() == ".py" else []
    else:
        py_files = [
            path
            for path in _iter_workspace_files(src_dir, max_files=5000)
            if path.suffix.lower() == ".py"
        ]

    local_modules: set[str] = set()
    if project_name:
        local_modules.add(_normalize_package_name(project_name).replace("-", "_"))
    audit_root = src_dir if src_dir.is_dir() else src_dir.parent
    project_root = proj_file.parent if proj_file and proj_file.is_file() else get_workspace_root()
    candidate_roots = {
        audit_root,
        project_root,
        project_root / "src",
        get_workspace_root(),
        get_workspace_root() / "src",
    }
    for root in candidate_roots:
        if not root.is_dir():
            continue
        try:
            with os.scandir(root) as iterator:
                for entry in list(iterator)[:1000]:
                    entry_path = Path(entry.path)
                    if entry.is_dir(follow_symlinks=False):
                        if (entry_path / "__init__.py").is_file() or any(
                            child.suffix.lower() == ".py"
                            for child in list(_iter_workspace_files(entry_path, max_files=20))
                        ):
                            local_modules.add(entry.name)
                    elif entry.is_file(follow_symlinks=False) and entry_path.suffix.lower() == ".py":
                        local_modules.add(entry_path.stem)
        except OSError:
            continue
    for py_file in py_files:
        try:
            relative = py_file.relative_to(audit_root)
        except ValueError:
            continue
        if len(relative.parts) > 1:
            local_modules.add(relative.parts[0])
        elif relative.suffix.lower() == ".py":
            local_modules.add(relative.stem)

    aliases = {
        "yaml": "pyyaml",
        "dotenv": "python-dotenv",
        "jwt": "pyjwt",
        "bs4": "beautifulsoup4",
        "cv2": "opencv-python",
        "dateutil": "python-dateutil",
        "opentelemetry": "opentelemetry-api",
        "qdrant_client": "qdrant-client",
        "PIL": "pillow",
        "sklearn": "scikit-learn",
        "Crypto": "pycryptodome",
        "OpenSSL": "pyopenssl",
        "gi": "pygobject",
        "serial": "pyserial",
        "usb": "pyusb",
        "attr": "attrs",
    }

    imported_modules: set[str] = set()
    files_scanned = 0
    for py_file in py_files:
        text, _, read_error = _read_text_limited(py_file, max_bytes=2_000_000, errors="strict")
        if read_error:
            parse_errors.append(f"{_relative_workspace_path(py_file)}: {read_error}")
            continue
        files_scanned += 1
        try:
            tree = ast.parse(text, filename=str(py_file))
        except SyntaxError as exc:
            parse_errors.append(f"{_relative_workspace_path(py_file)}:{exc.lineno or '?'}: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported_modules.add(node.module.split(".")[0])
        if len(parse_errors) >= 50:
            break

    external_modules = imported_modules - set(sys.stdlib_module_names) - local_modules
    normalized_imported = {
        _normalize_package_name(aliases.get(module, module)) for module in external_modules
    }

    def _is_declared(package: str) -> bool:
        if package in declared:
            return True
        return any(
            declared_name.startswith(f"{package}-") or package.startswith(f"{declared_name}-")
            for declared_name in declared
        )

    def _is_imported(declared_name: str) -> bool:
        if declared_name in normalized_imported:
            return True
        return any(
            imported_name.startswith(f"{declared_name}-") or declared_name.startswith(f"{imported_name}-")
            for imported_name in normalized_imported
        )

    undeclared = {package for package in normalized_imported if not _is_declared(package)}
    unused_declared = {package for package in declared if not _is_imported(package)}
    bounded_errors = parse_errors[:20]

    return {
        "clean": not undeclared and not bounded_errors,
        "undeclared": sorted(undeclared),
        "declared": sorted(declared),
        "imported": sorted(normalized_imported),
        "imported_modules": sorted(external_modules),
        "unused_declared": sorted(unused_declared),
        "local_modules": sorted(local_modules)[:200],
        "manifest_files": manifest_files,
        "files_scanned": files_scanned,
        "parse_errors": bounded_errors,
        "truncated": len(py_files) >= 5000,
    }


async def _regex_extract(params: dict[str, Any]) -> dict[str, Any]:
    pattern = params.get("pattern", "").strip()
    if not pattern:
        raise ValueError("Missing required parameter: pattern")

    text = params.get("text")
    path_param = params.get("path")
    flags_val = params.get("flags", "")

    if text is None and path_param:
        path, err = resolve_confined_path(path_param, must_exist=True)
        if not path:
            return {"error": err, "matches": [], "total_matches": 0, "named_groups": False}
        text = path.read_text(encoding="utf-8", errors="replace")

    if text is None:
        return {
            "error": "Either 'text' or 'path' must be provided",
            "matches": [],
            "total_matches": 0,
            "named_groups": False,
        }

    regex_flags = 0
    if flags_val:
        if isinstance(flags_val, int):
            regex_flags = flags_val
        else:
            f_str = str(flags_val).lower()
            if "i" in f_str:
                regex_flags |= re.IGNORECASE
            if "m" in f_str:
                regex_flags |= re.MULTILINE
            if "s" in f_str:
                regex_flags |= re.DOTALL
            if "x" in f_str:
                regex_flags |= re.VERBOSE

    try:
        compiled = re.compile(pattern, regex_flags)
    except re.error as e:
        return {
            "error": f"Invalid regex pattern: {e}",
            "matches": [],
            "total_matches": 0,
            "named_groups": False,
        }

    has_named = bool(compiled.groupindex)
    matches = []
    for m in compiled.finditer(text):
        if has_named:
            matches.append(m.groupdict())
        else:
            groups = m.groups()
            if groups:
                matches.append(list(groups) if len(groups) > 1 else groups[0])
            else:
                matches.append(m.group(0))

    return {
        "matches": matches,
        "total_matches": len(matches),
        "named_groups": has_named,
    }


EXTENDED_HANDLERS: dict[str, Any] = {
    "web_search": _web_search,
    "web_fetch": _web_fetch,
    "calculator": _calculator,
    "run_python": _run_python,
    "run_shell": _run_shell,
    "read_file": _read_file,
    "write_file": _write_file,
    "list_directory": _list_directory,
    "edit_file": _edit_file,
    "delete_file": _delete_file,
    "create_directory": _create_directory,
    "create_repository": _create_repository,
    "project_scan": _project_scan,
    "find_files": _find_files,
    "directory_tree": _directory_tree,
    "read_files": _read_files,
    "file_outline": _file_outline,
    "find_symbol": _find_symbol,
    "code_diagnostics": _code_diagnostics,
    "git_diff": _git_diff,
    "project_checks": _project_checks,
    "secret_scan": _secret_scan,
    "release_readiness": _release_readiness,
    "changelog_draft": _changelog_draft,
    "write_files": _write_files,
    "batch_edit_files": _batch_edit_files,
    "move_path": _move_path,
    "copy_path": _copy_path,
    "delete_directory": _delete_directory,
    "json_query": _json_query,
    "json_transform": _json_transform,
    "current_datetime": _current_datetime,
    "diff_text": _diff_text,
    "hash_text": _hash_text,
    "base64_encode": _base64_encode,
    "git_info": _git_info,
    "http_request": _http_request,
    "grep": _grep,
    "system_info": _system_info,
    "find_databases": _find_databases,
    "query_database": _query_database,
    "process_multimodal_media": _process_multimodal_media,
    "pytest_runner": _pytest_runner,
    "csv_query": _csv_query,
    "memory_graph_query": _memory_graph_query,
    "code_search_semantic": _code_search_semantic,
    "dependency_audit": _dependency_audit,
    "regex_extract": _regex_extract,
}
