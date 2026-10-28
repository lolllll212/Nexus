"""J.A.R.V.I.S. tool suite: git, swarm, calculator, sandbox, memory, repo reads.

Extracted from backend/main.py (strangler refactor, Upgrade 1). GRAPH-dependent
tools (system diagnostics, cosmos trigger) stay in main.py until the knowledge
service lands.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

# agent_comm lives in scripts/ - make the import work regardless of entrypoint.
if str(ROOT_DIR / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "scripts"))


def tool_git_status() -> dict[str, Any]:
    """Execute real git status and recent commit history."""
    try:
        status_res = subprocess.run(
            ["git", "status", "--short", "--branch"],
            capture_output=True,
            text=True,
            cwd=str(ROOT_DIR),
            timeout=5,
        )
        log_res = subprocess.run(
            ["git", "log", "-n", "4", "--oneline"],
            capture_output=True,
            text=True,
            cwd=str(ROOT_DIR),
            timeout=5,
        )
        lines = status_res.stdout.splitlines()
        branch_line = lines[0] if lines else "## unknown"
        branch_name = branch_line.replace("##", "").strip()
        changes = [line.strip() for line in lines[1:] if line.strip()]
        commits = [c.strip() for c in log_res.stdout.splitlines() if c.strip()]
        return {
            "branch": branch_name,
            "changes_count": len(changes),
            "changes": changes[:6],
            "recent_commits": commits,
            "clean": len(changes) == 0,
        }
    except Exception as exc:
        return {
            "branch": "master",
            "changes_count": 0,
            "changes": [],
            "recent_commits": [],
            "error": str(exc),
            "clean": True,
        }


def tool_list_tasks(status_filter: str = "all") -> dict[str, Any]:
    """Inspect the shared swarm task queue from agent_comm."""
    try:
        import agent_comm

        st = agent_comm.load_state()
        queue = st.get("task_queue", [])
        if status_filter != "all":
            queue = [t for t in queue if t.get("status") == status_filter]
        pending = [t for t in queue if t.get("status") == "pending"]
        claimed = [t for t in queue if t.get("status") == "claimed"]
        resolved = [t for t in queue if t.get("status") == "resolved"]
        return {
            "total": len(queue),
            "pending_count": len(pending),
            "claimed_count": len(claimed),
            "resolved_count": len(resolved),
            "tasks": queue[:6],
        }
    except Exception as exc:
        return {
            "total": 0,
            "pending_count": 0,
            "claimed_count": 0,
            "resolved_count": 0,
            "tasks": [],
            "error": str(exc),
        }


def tool_agent_status() -> dict[str, Any]:
    """Inspect swarm agent liveness, roles, and current activities."""
    agent_roles = {
        "astra": "Application / Eval / Docs Researcher",
        "tron": "Domain / Core Logic / TDD Engineer",
        "xenom": "Infra / Web / Sandbox / Security Architect",
        "ceo": "Strategic Orchestrator & Consensus Overseer",
    }
    try:
        import agent_comm

        st = agent_comm.load_state()
        agents_data = st.get("agents", {})
        now = time.time()
        agent_list = []
        for name, role in agent_roles.items():
            info = agents_data.get(name, {})
            last_hb = info.get("last_heartbeat", 0)
            idle_sec = max(0, int(now - last_hb)) if last_hb else 99999
            agent_list.append(
                {
                    "name": name.upper(),
                    "role": role,
                    "status": "online" if idle_sec < 300 else "standby",
                    "idle_sec": idle_sec,
                    "current_task": info.get("current_task") or "Awaiting dispatch",
                }
            )
        return {"agents": agent_list, "count": len(agent_list)}
    except Exception as exc:
        fallback = [
            {"name": k.upper(), "role": v, "status": "standby", "current_task": "Idle"}
            for k, v in agent_roles.items()
        ]
        return {"agents": fallback, "count": len(fallback), "error": str(exc)}


def tool_calculator(expr: str) -> dict[str, Any]:
    """Evaluate mathematical expression safely."""
    safe_dict = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": pow,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "pi": math.pi,
        "e": math.e,
        "factorial": math.factorial,
        "floor": math.floor,
        "ceil": math.ceil,
    }
    clean = re.sub(r"(?i)\b(calculate|what\s+is|evaluate|compute|eval|math)\b", "", expr)
    clean = clean.replace("^", "**")
    clean = re.sub(r"[^0-9a-zA-Z_\+\-\*\/\(\)\.\,\s\%]", "", clean).strip()
    try:
        res = eval(clean, {"__builtins__": None}, safe_dict)  # nosec
        return {"expression": clean, "result": res, "ok": True}
    except Exception as exc:
        return {"expression": expr, "error": str(exc), "ok": False}


def tool_run_python(code: str) -> dict[str, Any]:
    """Execute Python snippet safely and return output."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    start_t = time.perf_counter()
    ok = True
    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            exec_globals = {
                "__name__": "__main__",
                "math": math,
                "time": time,
                "json": json,
            }
            exec(code, exec_globals)
    except Exception as exc:
        ok = False
        stderr_buf.write(str(exc))
    elapsed_ms = round((time.perf_counter() - start_t) * 1000, 2)
    return {
        "ok": ok,
        "stdout": stdout_buf.getvalue().strip(),
        "stderr": stderr_buf.getvalue().strip(),
        "elapsed_ms": elapsed_ms,
    }


def tool_memory_query(query: str, k: int = 5) -> dict[str, Any]:
    """Query content-addressable memory chunks."""
    try:
        from nexus.infrastructure.adapters.persistence.agent_memory_store import (
            AgentMemoryStore,
        )

        store = AgentMemoryStore(ROOT_DIR / "agent_memory.json")
        chunks = store.search(query, k=k) if hasattr(store, "search") else store.latest(n=k)
        return {
            "count": len(chunks),
            "chunks": [c.to_dict() if hasattr(c, "to_dict") else str(c) for c in chunks],
        }
    except Exception as exc:
        return {"error": str(exc), "chunks": []}


_BINARY_EXTS = {
    ".exe",
    ".dll",
    ".node",
    ".pyd",
    ".so",
    ".dylib",
    ".zip",
    ".7z",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".woff",
    ".woff2",
    ".db",
    ".sqlite",
}
_SECRET_NAMES = {".env", ".dev.vars"}


def _safe_repo_path(raw: str) -> Path | None:
    """Resolve a user-supplied path to inside ROOT_DIR; None when refused."""
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        return None
    try:
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT_DIR / p
        resolved = p.resolve()
    except OSError:
        return None
    root = ROOT_DIR.resolve()
    if root != resolved and root not in resolved.parents:
        return None
    if resolved.name.lower() in _SECRET_NAMES:
        return None
    if resolved.suffix.lower() in _BINARY_EXTS:
        return None
    return resolved


def _extract_path_hint(query: str) -> str:
    """Pull the most path-like token out of a natural-language request."""
    # Quoted absolute paths may contain spaces. The candidate is still passed
    # through _safe_repo_path before use, so extraction alone grants no access.
    m = re.search(r"[\"']((?:[A-Za-z]:\\|/)[^\"']+)[\"']", query)
    if m:
        return m.group(1).strip()
    m = re.search(r"[A-Za-z]:\\[^\s\"']*", query)
    if m:
        return m.group(0)
    # POSIX absolute paths (for example a Linux /tmp/... repository root) do
    # not necessarily end in a file extension, unlike README.md-style hints.
    m = re.search(r"(?<![\w:/])/[^\s\"']+", query)
    if m:
        return m.group(0).rstrip(").,;:")
    m = re.search(r"[\w./\\-]+\.[A-Za-z0-9]{1,6}\b", query)
    if m:
        return m.group(0)
    # 'docs directory' / 'the plugins folder' style hints
    m = re.search(r"\b(?:directory|folder|dir)\s+([A-Za-z0-9][A-Za-z0-9_-]{1,40})\b", query, re.I)
    if m and m.group(1).lower() not in ("directory", "folder", "dir", "name", "listing"):
        return m.group(1)
    return ""


_HOME = Path.home()
_DISCOVERY_SCAN_CAP = 2000  # entries examined per discovery call


def _discover_sibling_root(token: str) -> Path | None:
    """Find a sibling project directory by name under the user profile.

    Read-only discovery, shallow (home + common dev folders, depth 2), capped.
    Used when a query names a repo that is not inside NEXUS itself, e.g.
    'look into the repo astra-x-main'.
    """
    token = (token or "").strip().lower().strip("\"'")
    if len(token) < 3:
        return None
    candidates: list[Path] = []
    seen: set[str] = set()
    scanned = 0
    try:
        bases = [_HOME] + [
            _HOME / n
            for n in ("Downloads", "Documents", "Desktop", "Projects", "projects", "dev", "code", "repos")
            if (_HOME / n).is_dir()
        ]
    except OSError:
        return None
    for base in bases:
        try:
            children = list(base.iterdir())
        except OSError:
            continue
        for child in children:
            if scanned >= _DISCOVERY_SCAN_CAP:
                return candidates[0] if candidates else None
            scanned += 1
            if not child.is_dir() or child.name.startswith("."):
                continue
            if child.name.lower() == token and str(child) not in seen:
                seen.add(str(child))
                candidates.append(child)
            try:
                for grand in child.iterdir():
                    if scanned >= _DISCOVERY_SCAN_CAP:
                        break
                    scanned += 1
                    if grand.is_dir() and grand.name.lower() == token and str(grand) not in seen:
                        seen.add(str(grand))
                        candidates.append(grand)
            except OSError:
                continue
    return candidates[0] if candidates else None


def _extract_named_repo(query: str) -> str:
    """Capture a bare repo/project name from phrases like 'the repo astra-x-main'."""
    m = re.search(
        r"(?:repo|repository|project|folder|directory)\s+(?:at\s+|called\s+|named\s+)?"
        r"[\"']?([A-Za-z0-9][A-Za-z0-9._-]{2,60})[\"']?",
        query,
    )
    if m:
        token = m.group(1)
        # Avoid generic words that are not repo names.
        if token.lower() not in ("status", "structure", "root", "layout", "file", "files"):
            return token
    return ""


def tool_read_repo(query: str) -> dict[str, Any]:
    """Read a file or list a directory inside the repo, or give an overview."""
    hint = _extract_path_hint(query)
    target = _safe_repo_path(hint) if hint else None
    lowered = query.lower()

    if target and target.is_file():
        try:
            size = target.stat().st_size
            text = target.read_text(encoding="utf-8", errors="replace")[:8000]
            return {
                "kind": "file",
                "path": str(target.relative_to(ROOT_DIR)),
                "bytes": size,
                "truncated": size > 8000,
                "excerpt": text,
            }
        except OSError as exc:
            return {"kind": "error", "path": str(target), "error": str(exc)[:200]}

    if target and target.is_dir():
        try:
            entries = []
            for child in sorted(target.iterdir())[:60]:
                try:
                    entries.append(
                        {
                            "name": child.name,
                            "type": "dir" if child.is_dir() else "file",
                            "bytes": child.stat().st_size if child.is_file() else 0,
                        }
                    )
                except OSError:
                    continue
            return {
                "kind": "directory",
                "path": str(target.relative_to(ROOT_DIR)),
                "count": len(entries),
                "entries": entries,
            }
        except OSError as exc:
            return {"kind": "error", "path": str(target), "error": str(exc)[:200]}

    # Sibling-repo discovery: the query names a project that is not inside
    # NEXUS (e.g. 'look into the repo astra-x-main'). An in-repo directory of
    # the same name always wins; the profile-wide scan is the fallback.
    named = _extract_named_repo(query) or (hint if hint and "." not in hint else "")
    if named:
        in_repo = _safe_repo_path(named)
        if in_repo is not None and (in_repo.is_dir() or in_repo.is_file()):
            # In-repo hit wins over profile-wide discovery.
            try:
                if in_repo.is_file():
                    size = in_repo.stat().st_size
                    text = in_repo.read_text(encoding="utf-8", errors="replace")[:8000]
                    return {
                        "kind": "file",
                        "path": str(in_repo.relative_to(ROOT_DIR)),
                        "bytes": size,
                        "truncated": size > 8000,
                        "excerpt": text,
                    }
                entries = []
                for child in sorted(in_repo.iterdir())[:60]:
                    try:
                        entries.append(
                            {
                                "name": child.name,
                                "type": "dir" if child.is_dir() else "file",
                                "bytes": child.stat().st_size if child.is_file() else 0,
                            }
                        )
                    except OSError:
                        continue
                return {
                    "kind": "directory",
                    "path": str(in_repo.relative_to(ROOT_DIR)),
                    "count": len(entries),
                    "entries": entries,
                }
            except OSError as exc:
                return {"kind": "error", "path": str(in_repo), "error": str(exc)[:200]}
        else:
            discovered = _discover_sibling_root(named)
            if discovered is not None:
                try:
                    entries = []
                    for child in sorted(discovered.iterdir())[:60]:
                        try:
                            entries.append(
                                {
                                    "name": child.name,
                                    "type": "dir" if child.is_dir() else "file",
                                    "bytes": child.stat().st_size if child.is_file() else 0,
                                }
                            )
                        except OSError:
                            continue
                    readme = discovered / "README.md"
                    excerpt = ""
                    if readme.is_file():
                        excerpt = readme.read_text(encoding="utf-8", errors="replace")[:800]
                    return {
                        "kind": "directory",
                        "external": True,
                        "path": str(discovered),
                        "count": len(entries),
                        "entries": entries,
                        "readme_excerpt": excerpt,
                        "note": "sibling repository discovered on the local disk (read-only)",
                    }
                except OSError as exc:
                    return {"kind": "error", "path": str(discovered), "error": str(exc)[:200]}
            return {
                "kind": "not-found",
                "searched": named,
                "note": "no directory with that name was found under the user profile",
            }

    if not target and any(kw in lowered for kw in ("project", "repo", "repository", "structure", "overview")):
        try:
            top = sorted(
                (
                    {"name": c.name, "type": "dir" if c.is_dir() else "file"}
                    for c in ROOT_DIR.iterdir()
                    if not c.name.startswith(".") and c.name not in {"node_modules", "__pycache__"}
                ),
                key=lambda e: (e["type"] != "dir", e["name"].lower()),
            )[:40]
        except OSError:
            top = []
        return {
            "kind": "overview",
            "path": ".",
            "note": "repo root listing - ask to read a specific file for analysis",
            "entries": top,
        }

    return {"kind": "refused", "hint": hint[:120]}


# ─── Deep research (research-and-train pipeline) ─────────────────────────────

_URL_RE = re.compile(r"https?://[^\s\"')\]]+")


def _fetch_reader_text(url: str, timeout: float = 25.0) -> str:
    """Fetch a page as clean text via the free Jina Reader (no API key)."""
    import httpx

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(f"https://r.jina.ai/{url}", headers={"Accept": "text/plain"})
            if resp.status_code == 200:
                return resp.text[:6000]
    except Exception:
        pass
    return ""


def _trigger_indexer() -> bool:
    """Regenerate graph-data.js + holo.json so new notes hit RAG + the graph."""
    try:
        subprocess.run(
            [sys.executable, str(BACKEND_DIR / "indexer.py")],
            cwd=str(ROOT_DIR),
            timeout=120,
            capture_output=True,
        )
        return True
    except Exception:
        return False


async def deep_research(query: str, max_depth: int = 3, context: str = "") -> dict:
    """Break a question into sub-queries, fetch any provided URLs via the free
    Jina Reader, synthesize a cited Markdown note into docs/notes/, and
    re-index so the knowledge is immediately RAG-searchable.

    No search API key is configured here, so live fetching is URL-driven
    (links found in the query); planning and synthesis use the active LLM.
    """
    from backend.services import llm as llm_service

    # 1. Plan sub-queries with the LLM.
    sub_queries: list[str] = []
    try:
        content, _r = await llm_service._call_llm(
            "You are a research planner. Break the user's question into at most "
            f"{max_depth} focused sub-questions. Reply ONLY with a JSON array of "
            "strings, no prose.",
            [{"role": "user", "content": query}],
        )
        match = re.search(r"\[.*\]", content or "", re.S)
        arr = json.loads(match.group(0)) if match else []
        if isinstance(arr, list):
            sub_queries = [str(q) for q in arr][:max_depth]
    except Exception:
        pass
    if not sub_queries:
        sub_queries = [query]

    # 2. Fetch live sources when the query carries URLs (reader, no key).
    urls = [u.rstrip(".,;)") for u in _URL_RE.findall(query)][:3]
    sources: list[dict] = []
    for u in urls:
        text = _fetch_reader_text(u)
        if text.strip():
            sources.append({"url": u, "excerpt": text[:300]})

    # 3. Synthesize the research note.
    sources_ctx = "\n\n".join(f"[{s['url']}]\n{s['excerpt']}" for s in sources) or "(no live sources)"
    try:
        note_md, _r = await llm_service._call_llm(
            "You are NEXUS's deep-research analyst. Write a structured Markdown "
            "research note answering the question: a short summary, one section "
            "per sub-question, a 'Key findings' bullet list, then 'Sources'. "
            "Cite provided live excerpts where used. Max ~60 lines.\n\n"
            f"QUESTION: {query}\n\nSUB-QUESTIONS:\n"
            + "\n".join(f"- {q}" for q in sub_queries)
            + (f"\n\nSHARED CONTEXT FROM EARLIER TOOLS:\n{context}" if context else "")
            + f"\n\nLIVE SOURCE EXCERPTS:\n{sources_ctx}",
            [{"role": "user", "content": "Write the research note now."}],
        )
    except Exception as exc:
        return {"ok": False, "error": f"research synthesis failed: {exc}"}

    if not (note_md or "").strip():
        return {"ok": False, "error": "empty research synthesis"}

    # 4. Save under docs/notes/ - the indexed knowledge home.
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:40] or "note"
    notes_dir = ROOT_DIR / "docs" / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    note_path = notes_dir / f"research-{slug}.md"
    counter = 1
    while note_path.exists():
        note_path = notes_dir / f"research-{slug}-{counter}.md"
        counter += 1
    note_path.write_text(f"# Research: {query}\n\n{note_md.strip()}\n", encoding="utf-8")

    # 5. Refresh the knowledge graph so the note is searchable immediately.
    indexed = _trigger_indexer()

    return {
        "ok": True,
        "note_path": str(note_path.relative_to(ROOT_DIR)),
        "sub_queries": sub_queries,
        "sources": [s["url"] for s in sources],
        "indexed": indexed,
        "summary": note_md.strip()[:400],
    }


# ─── Tool blackboard: cross-tool data sharing ────────────────────────────────
#
# Every dispatched tool publishes its structured result here under a stable key.
# Later tools (and the LLM synthesis pass) can read another tool's data instead
# of recomputing it - e.g. deep research grounds itself in the git/repo/memory
# context that earlier tools in the same conversation gathered.

import json as _json  # noqa: E402  (tools.py previously had no json import)

TOOL_BLACKBOARD: dict = {}
_BB_MAX = 24  # rolling cap on remembered tool payloads


def bb_put(key: str, data) -> None:
    """Publish a tool result on the shared blackboard (rolling, newest wins)."""
    TOOL_BLACKBOARD[key] = {"ts": time.time(), "data": data}
    if len(TOOL_BLACKBOARD) > _BB_MAX:
        oldest = min(TOOL_BLACKBOARD.items(), key=lambda kv: kv[1]["ts"])[0]
        TOOL_BLACKBOARD.pop(oldest, None)


def bb_get(key: str):
    entry = TOOL_BLACKBOARD.get(key)
    return entry["data"] if entry else None


def bb_compact(max_keys: int = 8, excerpt: int = 500) -> str:
    """Compact serialization of recent blackboard entries for LLM prompts."""
    entries = sorted(TOOL_BLACKBOARD.items(), key=lambda kv: kv[1]["ts"], reverse=True)
    parts = []
    for key, entry in entries[:max_keys]:
        try:
            body = _json.dumps(entry["data"], default=str)[:excerpt]
        except Exception:
            body = str(entry["data"])[:excerpt]
        parts.append("[" + key + "] " + body)
    return "\n\n".join(parts) if parts else "(blackboard empty)"


def run_tool_by_name(name: str, query: str = "") -> dict:
    """Run one registered tool by name - the tool-grounded training and
    cross-tool dispatch entry point."""
    runners = {
        "git": tool_git_status,
        "tasks": tool_list_tasks,
        "agents": tool_agent_status,
        "memory": lambda: tool_memory_query(query),
        "repo": lambda: tool_read_repo(query),
        "calc": lambda: tool_calculator(query),
    }
    runner = runners.get(name)
    if runner is None:
        return {"error": "unknown tool '" + str(name) + "'"}
    try:
        return runner()
    except Exception as exc:
        return {"error": str(exc)[:200]}
