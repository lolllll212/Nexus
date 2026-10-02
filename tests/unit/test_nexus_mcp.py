"""Unit tests for the standard Nexus MCP stdio server (task-041)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Ensure scripts is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import nexus_mcp  # noqa: E402


@pytest.fixture
def mcp_server_process():
    """Spawn the MCP server as a subprocess communicating over stdio."""
    proc = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "scripts" / "nexus_mcp.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()


def _rpc_exchange(proc: subprocess.Popen, payload: dict | str) -> dict:
    """Send a line of JSON/text to MCP server stdin and read the JSON-RPC response."""
    assert proc.stdin is not None
    assert proc.stdout is not None
    if isinstance(payload, dict):
        line = json.dumps(payload) + "\n"
    else:
        line = payload.strip() + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()
    resp_line = proc.stdout.readline()
    assert resp_line, "MCP server closed stdout unexpectedly"
    return json.loads(resp_line.strip())


def test_mcp_subprocess_handshake_and_ping(mcp_server_process):
    """Verify standard MCP initialize handshake returns 2024-11-05 and ping works."""
    # 1. Initialize
    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test-client", "version": "0.1.0"},
        },
    }
    resp = _rpc_exchange(mcp_server_process, init_req)
    assert resp.get("jsonrpc") == "2.0"
    assert resp.get("id") == 1
    result = resp.get("result", {})
    assert result.get("protocolVersion") == "2024-11-05"
    assert result.get("serverInfo", {}).get("name") == "idle"
    assert result.get("serverInfo", {}).get("version") == "1.0.0"
    assert "tools" in result.get("capabilities", {})
    assert "resources" in result.get("capabilities", {})

    # 2. Ping
    ping_resp = _rpc_exchange(mcp_server_process, {"jsonrpc": "2.0", "id": 2, "method": "ping"})
    assert ping_resp.get("jsonrpc") == "2.0"
    assert ping_resp.get("id") == 2
    assert ping_resp.get("result") == {}


def test_mcp_subprocess_tools_list_and_schemas(mcp_server_process):
    """Verify tools/list exposes >= 15 tools with valid input schemas."""
    req = {"jsonrpc": "2.0", "id": 10, "method": "tools/list"}
    resp = _rpc_exchange(mcp_server_process, req)
    assert resp.get("id") == 10
    tools = resp.get("result", {}).get("tools", [])
    assert len(tools) >= 15

    tool_names = {t["name"] for t in tools}
    expected_tools = {
        "next_task",
        "claim_task",
        "resolve_task",
        "heartbeat",
        "progress",
        "ask_ceo",
        "check_inbox",
        "plan_create",
        "plan_begin",
        "plan_step",
        "plan_finish",
        "plan_check_file",
        "memory_put",
        "memory_query",
        "consensus_propose",
        "consensus_review",
        "consensus_vote",
        "git_status",
    }
    assert expected_tools.issubset(tool_names)

    # Check that each tool has valid schema structure
    for t in tools:
        assert "description" in t
        assert "inputSchema" in t
        assert t["inputSchema"].get("type") == "object"
        assert "properties" in t["inputSchema"]


def test_mcp_subprocess_resources_list_and_read(mcp_server_process):
    """Verify resources/list returns standard URIs and resources/read returns valid JSON."""
    # List resources
    list_resp = _rpc_exchange(mcp_server_process, {"jsonrpc": "2.0", "id": 20, "method": "resources/list"})
    resources = list_resp.get("result", {}).get("resources", [])
    assert len(resources) >= 5
    uris = {r["uri"] for r in resources}
    assert "nexus://tasks/pending" in uris
    assert "nexus://state/current" in uris
    assert "nexus://board/plans" in uris
    assert "nexus://board/consensus" in uris
    assert "nexus://memory/recent" in uris

    # Read pending tasks resource
    read_resp = _rpc_exchange(
        mcp_server_process,
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "resources/read",
            "params": {"uri": "nexus://tasks/pending"},
        },
    )
    assert read_resp.get("id") == 21
    contents = read_resp.get("result", {}).get("contents", [])
    assert len(contents) == 1
    assert contents[0].get("uri") == "nexus://tasks/pending"
    assert contents[0].get("mimeType") == "application/json"
    parsed_tasks = json.loads(contents[0]["text"])
    assert isinstance(parsed_tasks, list)


def test_mcp_subprocess_tool_call_next_task(mcp_server_process):
    """Verify tools/call next_task routes capability-based tasks without corrupting stdout."""
    req = {
        "jsonrpc": "2.0",
        "id": 30,
        "method": "tools/call",
        "params": {
            "name": "next_task",
            "arguments": {"agent_id": "tron"},
        },
    }
    resp = _rpc_exchange(mcp_server_process, req)
    assert resp.get("id") == 30
    assert resp.get("result", {}).get("isError") is False
    content = resp.get("result", {}).get("content", [])
    assert len(content) == 1
    assert content[0]["type"] == "text"
    text = content[0]["text"]
    assert "task" in text.lower() or "no pending tasks" in text.lower()


def test_mcp_subprocess_error_handling(mcp_server_process):
    """Verify malformed JSON returns -32700, unknown method returns -32601, invalid URI returns -32602."""
    # 1. Malformed JSON parse error
    resp = _rpc_exchange(mcp_server_process, "NOT VALID JSON")
    assert resp.get("error", {}).get("code") == -32700
    assert "Parse error" in resp.get("error", {}).get("message", "")

    # 2. Unknown method
    resp = _rpc_exchange(mcp_server_process, {"jsonrpc": "2.0", "id": 40, "method": "non_existent_method"})
    assert resp.get("id") == 40
    assert resp.get("error", {}).get("code") == -32601
    assert "Method not found" in resp.get("error", {}).get("message", "")

    # 3. Invalid resource read URI
    resp = _rpc_exchange(
        mcp_server_process,
        {
            "jsonrpc": "2.0",
            "id": 41,
            "method": "resources/read",
            "params": {"uri": "nexus://nonexistent/uri"},
        },
    )
    assert resp.get("id") == 41
    assert resp.get("error", {}).get("code") == -32602


def test_handle_json_rpc_unit():
    """Unit test handle_json_rpc function directly for notifications and tool errors."""
    # Notifications return None
    assert nexus_mcp.handle_json_rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert nexus_mcp.handle_json_rpc({"jsonrpc": "2.0", "method": "cancelled"}) is None

    # Tool error returns isError: True payload
    resp = nexus_mcp.handle_json_rpc(
        {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {"name": "invalid_tool", "arguments": {}},
        }
    )
    assert resp is not None
    assert resp.get("id") == 99
    assert resp.get("result", {}).get("isError") is True
    assert "Unknown tool" in resp.get("result", {}).get("content", [])[0]["text"]


def test_handle_tool_call_plan_lifecycle_unit():
    """The plan tools must drive the real PlanningBoard API: create (with
    steps), begin (freeze), step (in order), finish - no tuple-unpack errors."""
    board = nexus_mcp._planning_board()  # noqa: SLF001
    title = "mcp lifecycle probe"
    # Clean slate for the probe title.
    for p in board.list_plans():
        if p.title == title:
            board.abandon(p.id, reason="probe reset")

    created = nexus_mcp.handle_tool_call(
        "plan_create",
        {
            "agent_id": "astra",
            "title": title,
            "steps": ["edit the file|src/nexus/probe_tmp.py", "verify it|tests/unit/test_probe_tmp.py"],
        },
    )
    assert "Plan created" in created
    plan_id = created.split("Plan created: ")[1].split(" ")[0]
    plan = board.get(plan_id)
    assert plan is not None and len(plan.steps) == 2

    begun = nexus_mcp.handle_tool_call("plan_begin", {"plan_id": plan_id})
    assert "frozen" in begun
    stepped = nexus_mcp.handle_tool_call("plan_step", {"plan_id": plan_id})
    assert "1/2" in stepped
    stepped2 = nexus_mcp.handle_tool_call("plan_step", {"plan_id": plan_id})
    assert "2/2" in stepped2
    finished = nexus_mcp.handle_tool_call("plan_finish", {"plan_id": plan_id})
    assert "finished" in finished
    assert board.get(plan_id).status == "done"

    # Frozen mid-flight: an in_progress plan refuses new steps via MCP.
    created2 = nexus_mcp.handle_tool_call(
        "plan_create",
        {"agent_id": "astra", "title": "mcp freeze probe", "steps": ["s1|src/nexus/probe_tmp.py"]},
    )
    plan2_id = created2.split("Plan created: ")[1].split(" ")[0]
    nexus_mcp.handle_tool_call("plan_begin", {"plan_id": plan2_id})
    frozen = nexus_mcp.handle_tool_call(
        "plan_create",
        {"agent_id": "astra", "title": "mcp freeze probe", "steps": ["s1|src/nexus/probe_tmp.py"]},
    )
    assert "rejected" in frozen or "already" in frozen
    board.abandon(plan2_id, reason="probe done")

    # Gate check via MCP: uncovered file denied, covered file allowed.
    p3, _ = board.create_plan(
        title="mcp gate probe", agent="astra", steps=[("s", ["src/nexus/probe_tmp.py"])]
    )
    board.begin(p3.id)
    denied = nexus_mcp.handle_tool_call("plan_check_file", {"file_path": "src/nexus/unrelated.py"})
    assert denied.startswith("DENIED")
    allowed = nexus_mcp.handle_tool_call("plan_check_file", {"file_path": "src/nexus/probe_tmp.py"})
    assert allowed.startswith("ALLOWED")
    board.abandon(p3.id, reason="probe done")


def test_handle_tool_call_memory_and_consensus_unit():
    """memory_query returns (chunk, score) in the right order; consensus
    review/vote speak the real ConsensusProtocol keywords."""
    _ = nexus_mcp._agent_memory_store()  # noqa: SLF001
    put = nexus_mcp.handle_tool_call(
        "memory_put",
        {
            "agent_id": "astra",
            "kind": "report",
            "text": f"mcp probe: docker sandbox timeout on fresh runners ({id(None)})",
            "tags": "probe",
        },
    )
    assert "memory chunk" in put
    found = nexus_mcp.handle_tool_call("memory_query", {"query": "docker sandbox timeout", "k": 3})
    assert "Found" in found
    # Score precedes the chunk text in each line (tuple order fixed).
    data_lines = [ln for ln in found.splitlines() if ln.strip().startswith("[")]
    assert data_lines and "mcp probe" in found

    cp = nexus_mcp._consensus_protocol()  # noqa: SLF001
    # The automated reviewers (tests-required, bandit) demand tests/ changes
    # when src/ is touched - the probe includes both to reach approval.
    # Unique draft per run: content-addressed ids make a stale review stick
    # to a repeated draft forever, so each run proposes fresh.
    import uuid

    prop = cp.propose(
        title="mcp consensus probe",
        author="xenom",
        draft=f"d-{uuid.uuid4().hex[:8]}",
        files=["src/nexus/x.py", "tests/unit/test_x.py"],
    )
    reviewed = nexus_mcp.handle_tool_call(
        "consensus_review",
        {"agent_id": "astra", "proposal_id": prop.id, "verdict": "approve", "comment": "lgtm"},
    )
    assert "Reviewed" in reviewed and "astra" in reviewed
    voted = nexus_mcp.handle_tool_call(
        "consensus_vote",
        {"ceo_agent": "ceo", "proposal_id": prop.id, "verdict": "yes"},
    )
    assert "Voted" in voted
    # The MCP handler mutates through its own disk-backed instance; re-read.
    final = nexus_mcp._consensus_protocol().get(prop.id)  # noqa: SLF001
    assert final is not None and final.status == "approved"
    # Unknown proposal returns a clean error, not a traceback.
    bad = nexus_mcp.handle_tool_call(
        "consensus_review", {"agent_id": "astra", "proposal_id": "nope", "verdict": "approve"}
    )
    assert "Error" in bad
