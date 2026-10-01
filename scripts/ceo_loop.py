"""
NEXUS Autonomous CEO Loop

Runs the CEO agent in autonomous mode: polls for issues, delegates to agents,
monitors progress, and reports — all without user intervention.

Usage:
    python scripts/ceo_loop.py --interval 300
    python scripts/ceo_loop.py --once
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = REPO_ROOT / "nexus_state.json"
HANDOFF_FILE = REPO_ROOT / "docs" / "HANDOFF.md"
ACTIVITY_LOG = REPO_ROOT / "agent_activity.jsonl"

PYTEST_TIMEOUT = 900
LINT_TIMEOUT = 300
MAX_BOARD_ENTRIES = 20
ACTIVE_TASK_STATUSES = frozenset({"pending", "claimed", "in_progress", "working"})

AUTONOMOUS_HEADER_RE = re.compile(r"^### .* \u2014 ceo \(autonomous\)\s*$", re.M)
FOREIGN_HEADER_RE = re.compile(r"^### (?!\u2014 ceo \(autonomous\))", re.M)

OWNER_MAP = {
    "astra": ["src/nexus/application/", "tests/eval/", "docs/"],
    "tron": ["src/nexus/domain/", "plugins/", "tests/unit/"],
    "xenom": ["src/nexus/infrastructure/", "web/", "config/", "tests/integration/"],
}
UNASSIGNED = "unassigned"

KEYWORD_OWNERS = [
    ("tron", ["domain", "unit test"]),
    ("astra", ["application", "eval", "architecture-map"]),
    ("xenom", ["infrastructure", "adapter", "route", "web"]),
]

load_dotenv(REPO_ROOT / ".env")


def log_activity(agent: str, action: str, detail: str = "") -> None:
    entry = {"ts": datetime.now(UTC).isoformat(), "agent": agent, "action": action, "detail": detail}
    with open(ACTIVITY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def push_webhook(agent: str, task: str, status: str) -> None:
    url = os.environ.get("NEXUS_WEBHOOK_URL", "")
    if not url:
        return
    try:
        import httpx

        httpx.post(
            url,
            json={
                "agent": agent,
                "task": task,
                "status": status,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            timeout=5,
        )
    except Exception:
        pass


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"agents": {}, "task_queue": [], "locks": [], "messages": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def run_cmd(cmd: str, timeout: int) -> tuple[str, int | None]:
    """Run a shell command and return (merged output, returncode).

    returncode is None when the command never produced one (timeout, crash, or
    the shell itself failed to start). Callers must treat None as "did not run",
    never as "clean".
    """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=timeout,
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        return f"{partial}\n[timed out after {timeout}s]", None
    except OSError as exc:
        return f"[could not start command: {exc}]", None
    output = result.stdout or ""
    if result.stderr:
        output = f"{output}\n{result.stderr}"
    return output.strip(), result.returncode


def rel_posix(path: str) -> str:
    """Normalize Windows or POSIX paths into repo-relative forward-slash paths."""
    text = str(path).strip().strip("'\"").replace("\\", "/")
    try:
        if Path(text).is_absolute():
            text = os.path.relpath(text, REPO_ROOT).replace("\\", "/")
    except (OSError, ValueError):
        pass
    while text.startswith("./"):
        text = text[2:]
    return text


def norm(path: str) -> str:
    """Case-folded form of rel_posix, used for all owner matching and dedup."""
    return rel_posix(path).lower()


def extract_paths(text: str) -> list[str]:
    candidates = re.findall(r"[A-Za-z0-9_.\-/\\]+\.(?:py|md|ts|tsx|toml|json|yml|yaml|ini|txt|cfg)", text)
    return sorted({rel_posix(c) for c in candidates})


def parse_pytest_summary(output: str) -> dict:
    """Parse pytest's final summary line into integer counts."""
    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "deselected": 0,
    }
    summary = ""
    for line in reversed(output.splitlines()):
        if re.search(r"\d+ (?:passed|failed|failed|error|errors|skipped|xfailed|xpassed|deselected)\b", line):
            summary = line
            break
    scope = summary or output
    for key, pattern in (
        ("passed", r"(\d+) passed"),
        ("failed", r"(\d+) failed"),
        ("errors", r"(\d+) errors?"),
        ("skipped", r"(\d+) skipped"),
        ("xfailed", r"(\d+) xfailed"),
        ("xpassed", r"(\d+) xpassed"),
        ("deselected", r"(\d+) deselected"),
    ):
        found = re.findall(pattern, scope)
        counts[key] = int(found[-1]) if found else 0
    return counts


def parse_pytest_failures(output: str) -> tuple[list[str], list[str]]:
    nodes: list[str] = []
    files: set[str] = set()
    for line in output.splitlines():
        match = re.match(r"^\s*(?:FAILED|ERROR)\s+(\S+)", line)
        if not match:
            continue
        node = rel_posix(match.group(1))
        nodes.append(node)
        files.add(node.split("::")[0])
    return nodes, sorted(files)


def check_tests() -> dict:
    output, returncode = run_cmd("python -m pytest tests/ -q --tb=no -rf 2>&1", PYTEST_TIMEOUT)
    counts = parse_pytest_summary(output)
    nodes, files = parse_pytest_failures(output)
    return {
        "passed": counts["passed"],
        "failed": counts["failed"],
        "errors": counts["errors"],
        "skipped": counts["skipped"],
        "xfailed": counts["xfailed"],
        "xpassed": counts["xpassed"],
        "total_failed": counts["failed"] + counts["errors"],
        "ran": returncode is not None and counts["passed"] + counts["failed"] + counts["errors"] > 0,
        "failed_nodes": nodes,
        "failed_files": files,
        "returncode": returncode,
        "output": output[-500:],
    }


def check_ruff() -> dict:
    output, returncode = run_cmd("ruff check src/ tests/ --output-format concise 2>&1", LINT_TIMEOUT)
    findings = []
    for line in output.splitlines():
        match = re.match(r"^(\S.*?\.py):\d+:\d+:\s+(\S+)\s+(.*)$", line)
        if match:
            findings.append(
                {"file": rel_posix(match.group(1)), "code": match.group(2), "message": match.group(3).strip()}
            )
    files = sorted({f["file"] for f in findings})
    codes = sorted({f["code"] for f in findings})
    return {
        "clean": returncode == 0,
        "ran": returncode is not None,
        "files": files,
        "codes": codes,
        "findings": findings,
        "returncode": returncode,
        "output": output[-300:],
    }


def check_black() -> dict:
    output, returncode = run_cmd("black --check src/ tests/ 2>&1", LINT_TIMEOUT)
    files = sorted({rel_posix(m) for m in re.findall(r"would reformat\s+(\S+\.py)", output)})
    return {
        "clean": returncode == 0,
        "ran": returncode is not None,
        "files": files,
        "returncode": returncode,
        "output": output[-300:],
    }


def owner_of_file(path: str) -> str:
    """Map a single file to its owning agent, or UNASSIGNED when no owner claims it."""
    normalized = norm(path)
    for agent, paths in OWNER_MAP.items():
        for prefix in paths:
            token = prefix.rstrip("/").lower()
            if normalized == token or normalized.startswith(token + "/"):
                return agent
    return UNASSIGNED


def classify_files(files: list[str]) -> dict:
    """Bucket files by owning agent; files nobody owns land in UNASSIGNED."""
    buckets: dict[str, list[str]] = {}
    for path in files:
        buckets.setdefault(owner_of_file(path), []).append(path)
    return {owner: sorted(set(paths)) for owner, paths in buckets.items()}


def keyword_owners(text: str) -> list[str]:
    """Last-resort routing from issue prose; empty means 'nobody claimed it'."""
    lowered = norm(text)
    owners = {owner for owner, keywords in KEYWORD_OWNERS if any(k in lowered for k in keywords)}
    return [owner for owner in OWNER_MAP if owner in owners]


def route_issue(issue: str, files: list[str] | None = None) -> list[str]:
    """Return every owner implicated by an issue.

    Multi-owner issues yield several owners so the caller can split the work;
    anything nobody claims is routed to UNASSIGNED rather than dumped on xenom.
    """
    buckets = classify_files(files or extract_paths(issue))
    owners = [owner for owner in OWNER_MAP if owner in buckets]
    if owners:
        return owners
    if not buckets:
        return keyword_owners(issue) or [UNASSIGNED]
    return [UNASSIGNED]


def issue_signature(kind: str, files: list[str]) -> str:
    """Stable identity for an issue, independent of counts and prose."""
    payload = kind + "|" + "|".join(sorted(norm(f) for f in files))
    return f"{kind}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]}"


def find_existing_task(state: dict, signature: str, files: list[str]) -> str | None:
    """Return the id of an active task already covering this issue, if any.

    Dedup runs on the stable signature first, then falls back to "does any
    active task's description mention one of these files?" so tasks written by
    scripts/agent_comm.py with different wording still suppress duplicates.
    """
    for task in state.get("task_queue", []):
        if task.get("status") not in ACTIVE_TASK_STATUSES:
            continue
        if task.get("signature"):
            # Script-created task: only its exact signature counts, so a "tests" task
            # never suppresses a separate "ruff" task for the same file.
            if signature and task.get("signature") == signature:
                return str(task.get("id"))
            continue
        # Legacy prose task (scripts/agent_comm.py or a human): no signature to compare,
        # so treat it as covering any issue that names one of the same files.
        description = norm(str(task.get("description", "")))
        for path in files:
            if path and path in description:
                return str(task.get("id"))
    return None


def acceptance_for(kind: str, files: list[str]) -> tuple[list[str], str]:
    """Acceptance criteria + priority for a delegated task, by issue kind."""
    scoped = " ".join(files[:3])
    if kind == "tests":
        acc = [f"pytest {scoped} -q passes"] if scoped else ["pytest tests/ -q passes"]
        return acc, "high"
    if kind == "ruff":
        acc = [f"ruff check {scoped} clean"] if scoped else ["ruff check src/ tests/ clean"]
        return acc, "medium"
    if kind == "black":
        acc = [f"black --check {scoped} clean"] if scoped else ["black --check src/ tests/ clean"]
        return acc, "medium"
    return ["pytest tests/ -q passes"], "medium"


def delegate_task(
    ceo_agent: str,
    target: str,
    description: str,
    signature: str = "",
    files: list[str] | None = None,
    kind: str = "",
) -> str:
    state = load_state()
    state.setdefault("task_queue", [])
    # The id is derived AFTER the reload, and carries a uuid4 suffix so several
    # tasks queued in the same second can never collide.
    task_id = f"task-{int(time.time())}-{len(state['task_queue']) + 1:03d}-{uuid.uuid4().hex[:4]}"
    file_list = list(files or [])
    acceptance, priority = acceptance_for(kind, file_list)
    state["task_queue"].append(
        {
            "id": task_id,
            "description": description,
            "requested_by": ceo_agent or "ceo",
            "for": target,
            "status": "pending",
            "priority": priority,
            "signature": signature,
            "files": file_list,
            "acceptance": acceptance,
            "evidence": None,
            "verified": False,
            "created_at": datetime.now(UTC).isoformat(),
            "claimed_by": None,
            "claimed_at": None,
            "resolved_at": None,
        }
    )
    save_state(state)
    log_activity("ceo", "delegate", f"{task_id} -> {target}: {description[:100]}")
    push_webhook("ceo", f"delegated to {target}: {description}", "in-progress")
    return task_id


def board_digest(message: str) -> str:
    """Hash a report body, ignoring the volatile timestamp/count lines."""
    body = "\n".join(line for line in message.splitlines() if "AUTONOMOUS CYCLE" not in line)
    collapsed = re.sub(r"\s+", " ", body).strip()
    return hashlib.sha256(collapsed.encode("utf-8")).hexdigest()[:16]


def prune_autonomous(text: str, keep: int) -> str:
    """Drop the oldest autonomous board entries, never foreign ones."""
    headers = list(AUTONOMOUS_HEADER_RE.finditer(text))
    if len(headers) <= keep or keep < 1:
        return text
    bounds = [
        (m.start(), headers[i + 1].start() if i + 1 < len(headers) else len(text))
        for i, m in enumerate(headers)
    ]
    droppable = [
        i
        for i, (start, end) in enumerate(bounds)
        if not FOREIGN_HEADER_RE.search(text[headers[i].end() : end])
    ]
    drop: set[int] = set()
    for i in droppable:
        if len(headers) - len(drop) <= keep:
            break
        drop.add(i)
    if not drop:
        return text
    chunks, cursor = [], 0
    for i, (start, end) in enumerate(bounds):
        if i in drop:
            chunks.append(text[cursor:start])
            cursor = end
    chunks.append(text[cursor:])
    return "".join(chunks)


def post_board(message: str, force: bool = False) -> bool:
    """Append a cycle report, capped at MAX_BOARD_ENTRIES. False when skipped."""
    existing = HANDOFF_FILE.read_text(encoding="utf-8") if HANDOFF_FILE.exists() else ""
    if not force and existing:
        headers = list(AUTONOMOUS_HEADER_RE.finditer(existing))
        if headers:
            last = headers[-1]
            # Digest the previous entry BODY only. Including its "### <ts> — ceo (autonomous)"
            # header would bake a fresh timestamp into every digest and defeat the comparison.
            segment = existing[last.end() :]
            nxt = FOREIGN_HEADER_RE.search(segment)
            previous = segment[: nxt.start()] if nxt else segment
            if board_digest(previous) == board_digest(message):
                return False
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"\n### {timestamp} \u2014 ceo (autonomous)\n{message.strip()}\n"
    kept = prune_autonomous(existing, MAX_BOARD_ENTRIES - 1)
    prefix = f"{kept.rstrip()}\n" if kept.strip() else ""
    with open(HANDOFF_FILE, "w", encoding="utf-8") as f:
        f.write(prefix + entry)
    push_webhook("ceo", message.strip()[:200], "done")
    return True


def build_issues(tests: dict, ruff: dict, black: dict) -> list[dict]:
    issues = []
    if not tests["ran"]:
        issues.append(
            {
                "kind": "tests",
                "text": f"Tests: pytest did not complete (returncode={tests['returncode']})",
                "files": [],
            }
        )
    elif tests["total_failed"] > 0:
        detail = ", ".join(tests["failed_files"][:5]) or "no FAILED lines parsed"
        issues.append(
            {
                "kind": "tests",
                "text": (
                    f"Tests: {tests['total_failed']} failed, {tests['passed']} passed, "
                    f"{tests['skipped']} skipped in {detail}"
                ),
                "files": list(tests["failed_files"]),
            }
        )
    if not ruff["clean"]:
        if ruff["ran"]:
            codes = ", ".join(ruff["codes"][:5]) or "unknown"
            detail = ", ".join(ruff["files"][:5]) or "unknown files"
            issues.append(
                {
                    "kind": "ruff",
                    "text": f"Ruff errors [{codes}] in {detail}",
                    "files": list(ruff["files"]),
                }
            )
        else:
            issues.append(
                {
                    "kind": "ruff",
                    "text": f"Ruff did not complete (returncode={ruff['returncode']}): {ruff['output'][-120:]}",
                    "files": [],
                }
            )
    if not black["clean"]:
        if black["ran"]:
            detail = ", ".join(black["files"][:5]) or "unknown files"
            issues.append(
                {
                    "kind": "black",
                    "text": f"Black reformat needed in {detail}",
                    "files": list(black["files"]),
                }
            )
        else:
            issues.append(
                {
                    "kind": "black",
                    "text": f"Black did not complete (returncode={black['returncode']}): {black['output'][-120:]}",
                    "files": [],
                }
            )
    return issues


def dispatch_issues(state: dict, issues: list[dict]) -> tuple[int, int, list[str], list[str]]:
    """Route every issue to its owners, skipping issues already queued.

    Multi-owner issues are split into one task per owner, each scoped to that
    owner's files. Returns (delegated, skipped, created_task_ids, report_lines).
    """
    lines: list[str] = []
    created: list[str] = []
    delegated = skipped = 0
    for issue in issues:
        owners = route_issue(issue["text"], issue["files"])
        lines.append(f"  - {issue['text']} -> owners: {', '.join(owners)}")
        for owner in owners:
            scoped = classify_files(issue["files"]).get(owner) or issue["files"]
            signature = issue_signature(issue["kind"], scoped)
            existing_id = find_existing_task(state, signature, scoped)
            if existing_id:
                skipped += 1
                lines.append(f"      {owner}: SKIPPED, already queued as {existing_id}")
                continue
            detail = ", ".join(scoped[:5]) or "no files attributed"
            description = f"Fix {issue['kind']}: {detail} [signature={signature}]"
            created.append(
                delegate_task(
                    "ceo",
                    owner,
                    description,
                    signature=signature,
                    files=scoped,
                    kind=issue["kind"],
                )
            )
            delegated += 1
            lines.append(f"      {owner}: DELEGATED")
            # Mirror the new task into the in-memory state so a later issue in this
            # same cycle dedups against it instead of queueing a second copy.
            state.setdefault("task_queue", []).append(
                {"id": created[-1], "status": "pending", "signature": signature, "description": description}
            )
    return delegated, skipped, created, lines


def run_autonomous_cycle() -> None:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    tests = check_tests()
    ruff = check_ruff()
    black = check_black()

    issues = build_issues(tests, ruff, black)
    state = load_state()
    pending = [t for t in state.get("task_queue", []) if t.get("status") == "pending"]
    blocked = [t for t in state.get("task_queue", []) if t.get("status") in ("claimed", "in_progress")]

    report = f"""
CEO AUTONOMOUS CYCLE — {timestamp}
================================
TESTS: {tests['passed']} passed, {tests['total_failed']} failed, {tests['skipped']} skipped
LINT:  ruff={'OK' if ruff['clean'] else 'FAIL'}, black={'OK' if black['clean'] else 'FAIL'}
TASKS: {len(pending)} pending, {len(blocked)} in-progress
AGENTS:
  astra:   {state.get('agents', {}).get('astra', {}).get('status', '?')}
  tron:    {state.get('agents', {}).get('tron', {}).get('status', '?')}
  xenom:   {state.get('agents', {}).get('xenom', {}).get('status', '?')}
"""
    delegated, skipped, created = 0, 0, []

    if issues:
        delegated, skipped, created, lines = dispatch_issues(state, issues)
        report += "\nISSUES DETECTED:\n" + "\n".join(lines) + "\n"
        report += f"\nDELEGATED: {delegated} new, {skipped} skipped (already queued)."
    else:
        report += "\nISSUES DETECTED: none."

    posted = post_board(report)
    if not posted:
        report += "\nBOARD: not posted (unchanged since last cycle)."
    for task_id in created:
        report += f"\nNEW TASK: {task_id}"

    log_activity("ceo", "cycle", f"tests {tests['passed']}p/{tests['total_failed']}f, {len(pending)} pending")
    print(report)


def main():
    parser = argparse.ArgumentParser(description="NEXUS Autonomous CEO")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between cycles")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    if args.once:
        run_autonomous_cycle()
        return

    print(f"CEO autonomous loop started (interval={args.interval}s)")
    while True:
        run_autonomous_cycle()
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
