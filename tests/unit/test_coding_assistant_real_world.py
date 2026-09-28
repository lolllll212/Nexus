"""
Comprehensive real-world tests for the NEXUS Coding & Research Studio.

Covers:
- Real-world algorithmic problem solving & execution (LRU Cache, Graph search)
- Real-world automated debugging and sandbox code execution
- Real-world unit test generation and execution via test runner
- Real-world multi-site technical web research synthesis
- Real-world GitHub and repository inspection tools
- Claude artifact generation, language tagging, and thinking process extraction
"""

import json
import pytest
from starlette.testclient import TestClient

from nexus.infrastructure.api.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# 1. Real-World Algorithmic Problem Solving & Execution
# ─────────────────────────────────────────────────────────────────────────────

def test_real_world_lru_cache_algorithm(client):
    """Test implementing and executing an LRU Cache with capacity constraints."""
    lru_code = """
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key: int) -> int:
        if key not in self.cache:
            return -1
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key: int, value: int) -> None:
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

cache = LRUCache(2)
cache.put(1, 100)
cache.put(2, 200)
assert cache.get(1) == 100
cache.put(3, 300) # evicts key 2
assert cache.get(2) == -1
assert cache.get(3) == 300
assert cache.get(1) == 100
print("LRU Cache validation passed successfully.")
"""
    res = client.post("/api/coding/execute", json={"code": lru_code})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "LRU Cache validation passed" in data["output"]
    assert data["execution_time_ms"] > 0


def test_real_world_graph_cycle_detection(client):
    """Test algorithmic graph cycle detection with DFS."""
    graph_code = """
def has_cycle(num_nodes, edges):
    from collections import defaultdict
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
    
    visited = [0] * num_nodes  # 0=unvisited, 1=visiting, 2=visited
    
    def dfs(node):
        visited[node] = 1
        for neighbor in adj[node]:
            if visited[neighbor] == 1:
                return True
            if visited[neighbor] == 0:
                if dfs(neighbor):
                    return True
        visited[node] = 2
        return False

    for i in range(num_nodes):
        if visited[i] == 0:
            if dfs(i):
                return True
    return False

# Graph 1: Cycle 0 -> 1 -> 2 -> 0
assert has_cycle(3, [(0, 1), (1, 2), (2, 0)]) is True
# Graph 2: DAG 0 -> 1 -> 2
assert has_cycle(3, [(0, 1), (1, 2)]) is False
print("Graph cycle detection tests passed.")
"""
    res = client.post("/api/coding/execute", json={"code": graph_code})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "Graph cycle detection tests passed" in data["output"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Real-World Code Debugging and Error Reporting
# ─────────────────────────────────────────────────────────────────────────────

def test_real_world_debugging_syntax_and_logic_error(client):
    """Verify that syntax errors and runtime exceptions in buggy code are properly reported."""
    broken_code = """
def compute_metrics(values):
    # Intentional ZeroDivisionError
    total = sum(values)
    return total / len(values)

print(compute_metrics([]))
"""
    res = client.post("/api/coding/execute", json={"code": broken_code})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert "ZeroDivisionError" in data["error"] or "ZeroDivisionError" in data["output"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. Real-World Unit Test Runner Harness
# ─────────────────────────────────────────────────────────────────────────────

def test_real_world_test_runner_success(client):
    """Test running a full unittest test suite against production code."""
    code = """
def format_currency(amount: float, symbol: str = "$") -> str:
    if amount < 0:
        return f"-{symbol}{abs(amount):,.2f}"
    return f"{symbol}{amount:,.2f}"
"""
    test_code = """
class TestCurrencyFormatter(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(format_currency(1234567.89), "$1,234,567.89")

    def test_negative(self):
        self.assertEqual(format_currency(-50.5), "-$50.50")

    def test_custom_symbol(self):
        self.assertEqual(format_currency(100, "€"), "€100.00")
"""
    res = client.post(
        "/api/coding/test-runner",
        json={"code": code, "test_code": test_code},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["passed"] is True
    assert data["tests_run"] == 3
    assert data["failures"] == 0
    assert "OK" in data["output"]


def test_real_world_test_runner_failure_detection(client):
    """Test that assertions properly fail when code has logical regressions."""
    code = """
def multiply(a, b):
    return a + b  # Bug: adding instead of multiplying
"""
    test_code = """
class TestMultiply(unittest.TestCase):
    def test_multiplication(self):
        self.assertEqual(multiply(3, 4), 12)
"""
    res = client.post(
        "/api/coding/test-runner",
        json={"code": code, "test_code": test_code},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["passed"] is False
    assert data["failures"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 4. Real-World Technical Web Research Integration
# ─────────────────────────────────────────────────────────────────────────────

def test_real_world_coding_chat_with_web_research(client):
    """Test asking for technical documentation/research and verifying tool invocation."""
    res = client.post(
        "/api/coding/chat",
        json={
            "prompt": "Research FastAPI lifespan handlers vs legacy on_event startup events.",
            "enable_web_search": True,
            "enable_code_exec": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert len(data["thinking"]) > 0
    assert len(data["response"]) > 0
    # Check that web_search was executed
    search_tools = [t for t in data["tools_used"] if t["tool"] == "web_search"]
    assert len(search_tools) >= 1
    assert search_tools[0]["status"] == "success"
    # Check that a research artifact was created
    research_artifacts = [a for a in data["artifacts"] if a["type"] == "research"]
    assert len(research_artifacts) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. Real-World GitHub Repository Inspection Integration
# ─────────────────────────────────────────────────────────────────────────────

def test_real_world_coding_chat_with_github_inspection(client):
    """Test inspecting repository git status and metadata."""
    res = client.post(
        "/api/coding/chat",
        json={
            "prompt": "Check git status and current repository branch info for lolllll212/Nexus.",
            "enable_github": True,
            "enable_web_search": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    git_tools = [t for t in data["tools_used"] if t["tool"] == "git_info"]
    assert len(git_tools) >= 1
    assert "branch" in git_tools[0]["result"]


# ─────────────────────────────────────────────────────────────────────────────
# 6. Real-World Python Code Execution from Prompt
# ─────────────────────────────────────────────────────────────────────────────

def test_real_world_coding_chat_executes_python_blocks(client):
    """Test that embedded Python scripts in the prompt are automatically executed in sandbox."""
    prompt = """Please execute python to compute factorial:
```python
def fact(n):
    return 1 if n <= 1 else n * fact(n - 1)
print(f"Fact 6: {fact(6)}")
```
"""
    res = client.post(
        "/api/coding/chat",
        json={
            "prompt": prompt,
            "enable_code_exec": True,
            "enable_web_search": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    exec_tools = [t for t in data["tools_used"] if t["tool"] == "run_python"]
    assert len(exec_tools) >= 1
    assert "Fact 6: 720" in exec_tools[0]["result"].get("output", "")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Claude Artifacts & Templates Endpoints
# ─────────────────────────────────────────────────────────────────────────────

def test_real_world_coding_templates(client):
    """Test fetching pre-configured prompt templates for real-world tasks."""
    res = client.get("/api/coding/templates")
    assert res.status_code == 200
    data = res.json()
    templates = data["templates"]
    assert len(templates) >= 4
    categories = [t["category"] for t in templates]
    assert "Algorithms" in categories
    assert "Deep Research" in categories
    assert "GitHub" in categories
