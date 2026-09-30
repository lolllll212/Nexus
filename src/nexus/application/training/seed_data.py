"""
Seed coding examples — foundational knowledge for NEXUS coding tasks.
"""

from __future__ import annotations

from nexus.application.training.coding_store import CodingExample

SEED_EXAMPLES = [
    # ── Algorithms ──────────────────────────────────────────
    CodingExample(
        task="Write a binary search function",
        solution="""def binary_search(arr, target):
    \"\"\"Find target in sorted array. Returns index or -1.\"\"\"
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1""",
        language="python",
        category="algorithms",
        difficulty="easy",
        tags=["search", "array", "divide-and-conquer"],
        explanation="Divide search space in half each step. O(log n) time, O(1) space.",
        test_cases="""assert binary_search([1, 2, 3, 4, 5], 3) == 2
assert binary_search([1, 2, 3, 4, 5], 6) == -1
assert binary_search([], 1) == -1
assert binary_search([1], 1) == 0""",
    ),
    CodingExample(
        task="Implement merge sort",
        solution="""def merge_sort(arr):
    \"\"\"Sort array using merge sort. O(n log n) time.\"\"\"
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return merge(left, right)

def merge(left, right):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result""",
        language="python",
        category="algorithms",
        difficulty="medium",
        tags=["sort", "divide-and-conquer", "recursive"],
        explanation="Recursively split array in half, merge sorted halves. Stable sort.",
        test_cases="""assert merge_sort([3, 1, 4, 1, 5, 9]) == [1, 1, 3, 4, 5, 9]
assert merge_sort([]) == []
assert merge_sort([1]) == [1]""",
    ),
    CodingExample(
        task="Implement a hash map from scratch",
        solution="""class HashMap:
    \"\"\"Simple hash map using separate chaining.\"\"\"
    def __init__(self, capacity=16):
        self.capacity = capacity
        self.size = 0
        self.buckets = [[] for _ in range(capacity)]

    def _hash(self, key):
        return hash(key) % self.capacity

    def put(self, key, value):
        idx = self._hash(key)
        bucket = self.buckets[idx]
        for i, (k, v) in enumerate(bucket):
            if k == key:
                bucket[i] = (key, value)
                return
        bucket.append((key, value))
        self.size += 1
        if self.size > self.capacity * 0.75:
            self._resize()

    def get(self, key, default=None):
        idx = self._hash(key)
        for k, v in self.buckets[idx]:
            if k == key:
                return v
        return default

    def _resize(self):
        old = self.buckets
        self.capacity *= 2
        self.buckets = [[] for _ in range(self.capacity)]
        self.size = 0
        for bucket in old:
            for k, v in bucket:
                self.put(k, v)""",
        language="python",
        category="data-structures",
        difficulty="hard",
        tags=["hashmap", "hash-table", "data-structure"],
        explanation="Array of buckets (linked lists). Hash key to bucket index. Resize at 75% load.",
        test_cases="""hm = HashMap()
hm.put("a", 1)
hm.put("b", 2)
assert hm.get("a") == 1
assert hm.get("b") == 2
assert hm.get("c") is None""",
    ),
    # ── Data Structures ─────────────────────────────────────
    CodingExample(
        task="Implement a stack with O(1) push, pop, and get_min",
        solution="""class MinStack:
    \"\"\"Stack that tracks minimum element in O(1).\"\"\"
    def __init__(self):
        self.stack = []
        self.min_stack = []

    def push(self, val):
        self.stack.append(val)
        if not self.min_stack or val <= self.min_stack[-1]:
            self.min_stack.append(val)

    def pop(self):
        if not self.stack:
            raise IndexError("pop from empty stack")
        val = self.stack.pop()
        if val == self.min_stack[-1]:
            self.min_stack.pop()
        return val

    def get_min(self):
        if not self.min_stack:
            raise IndexError("stack is empty")
        return self.min_stack[-1]

    def peek(self):
        return self.stack[-1] if self.stack else None

    def is_empty(self):
        return len(self.stack) == 0""",
        language="python",
        category="data-structures",
        difficulty="medium",
        tags=["stack", "min-stack", "data-structure"],
        explanation="Parallel min-stack mirrors the main stack. Push to min-stack only when value <= current min.",
        test_cases="""s = MinStack()
s.push(3); s.push(1); s.push(4)
assert s.get_min() == 1
s.pop()
assert s.get_min() == 1
s.pop()
assert s.get_min() == 3""",
    ),
    CodingExample(
        task="Implement a LRU cache",
        solution="""from collections import OrderedDict

class LRUCache:
    \"\"\"Least Recently Used cache with O(1) get/put.\"\"\"
    def __init__(self, capacity):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key):
        if key not in self.cache:
            return -1
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)""",
        language="python",
        category="data-structures",
        difficulty="medium",
        tags=["cache", "lru", "ordered-dict"],
        explanation="OrderedDict with move_to_end. Evict oldest when over capacity.",
        test_cases="""c = LRUCache(2)
c.put(1, 1); c.put(2, 2)
assert c.get(1) == 1
c.put(3, 3)  # evicts key 2
assert c.get(2) == -1""",
    ),
    # ── String manipulation ─────────────────────────────────
    CodingExample(
        task="Check if a string is a valid palindrome",
        solution="""def is_palindrome(s):
    \"\"\"Check palindrome ignoring non-alphanumeric chars and case.\"\"\"
    cleaned = ''.join(c.lower() for c in s if c.isalnum())
    return cleaned == cleaned[::-1]""",
        language="python",
        category="strings",
        difficulty="easy",
        tags=["palindrome", "string", "two-pointers"],
        explanation="Clean string, compare with reverse. Two-pointer approach is more efficient.",
        test_cases="""assert is_palindrome("A man, a plan, a canal: Panama") == True
assert is_palindrome("race a car") == False
assert is_palindrome("") == True""",
    ),
    CodingExample(
        task="Find the longest common substring between two strings",
        solution="""def longest_common_substring(s1, s2):
    \"\"\"Find longest common substring using dynamic programming.\"\"\"
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    max_len = 0
    end_pos = 0
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i-1] == s2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
                if dp[i][j] > max_len:
                    max_len = dp[i][j]
                    end_pos = i
    return s1[end_pos - max_len:end_pos]""",
        language="python",
        category="strings",
        difficulty="medium",
        tags=["substring", "dynamic-programming", "dp"],
        explanation="2D DP table. dp[i][j] = length of common substring ending at s1[i-1], s2[j-1].",
        test_cases="""assert longest_common_substring("abcdef", "zbcdf") == "bcd"
assert longest_common_substring("abc", "def") == ""
assert longest_common_substring("abc", "abc") == "abc""",
    ),
    # ── Trees ───────────────────────────────────────────────
    CodingExample(
        task="Implement a binary search tree with insert, search, and in-order traversal",
        solution="""class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right

class BST:
    def __init__(self):
        self.root = None

    def insert(self, val):
        self.root = self._insert(self.root, val)

    def _insert(self, node, val):
        if not node:
            return TreeNode(val)
        if val < node.val:
            node.left = self._insert(node.left, val)
        elif val > node.val:
            node.right = self._insert(node.right, val)
        return node

    def search(self, val):
        return self._search(self.root, val)

    def _search(self, node, val):
        if not node or node.val == val:
            return node
        if val < node.val:
            return self._search(node.left, val)
        return self._search(node.right, val)

    def inorder(self):
        result = []
        self._inorder(self.root, result)
        return result

    def _inorder(self, node, result):
        if node:
            self._inorder(node.left, result)
            result.append(node.val)
            self._inorder(node.right, result)""",
        language="python",
        category="trees",
        difficulty="medium",
        tags=["bst", "binary-tree", "tree"],
        explanation="Recursive insert/search. In-order traversal gives sorted order.",
        test_cases="""bst = BST()
for v in [5, 3, 7, 1, 4]:
    bst.insert(v)
assert bst.inorder() == [1, 3, 4, 5, 7]
assert bst.search(4).val == 4
assert bst.search(8) is None""",
    ),
    # ── Graphs ──────────────────────────────────────────────
    CodingExample(
        task="Implement BFS and DFS for a graph",
        solution="""from collections import defaultdict, deque

class Graph:
    def __init__(self):
        self.adj = defaultdict(list)

    def add_edge(self, u, v):
        self.adj[u].append(v)
        self.adj[v].append(u)

    def bfs(self, start):
        visited = set([start])
        queue = deque([start])
        order = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in self.adj[node]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return order

    def dfs(self, start):
        visited = set()
        order = []
        def _dfs(node):
            visited.add(node)
            order.append(node)
            for neighbor in self.adj[node]:
                if neighbor not in visited:
                    _dfs(neighbor)
        _dfs(start)
        return order""",
        language="python",
        category="graphs",
        difficulty="medium",
        tags=["bfs", "dfs", "graph", "traversal"],
        explanation="BFS uses queue (level-order). DFS uses stack/recursion (depth-first).",
        test_cases="""g = Graph()
for u, v in [(0,1),(0,2),(1,3),(2,3)]:
    g.add_edge(u, v)
assert 0 in g.bfs(0)
assert 0 in g.dfs(0)""",
    ),
    # ── Dynamic Programming ─────────────────────────────────
    CodingExample(
        task="Solve the coin change problem",
        solution="""def coin_change(coins, amount):
    \"\"\"Find minimum coins to make amount. Returns -1 if impossible.\"\"\"
    dp = [float('inf')] * (amount + 1)
    dp[0] = 0
    for i in range(1, amount + 1):
        for coin in coins:
            if coin <= i and dp[i - coin] + 1 < dp[i]:
                dp[i] = dp[i - coin] + 1
    return dp[amount] if dp[amount] != float('inf') else -1""",
        language="python",
        category="dynamic-programming",
        difficulty="medium",
        tags=["dp", "coin-change", "optimization"],
        explanation="Bottom-up DP. dp[i] = min coins to make amount i. Try each coin.",
        test_cases="""assert coin_change([1, 5, 10, 25], 30) == 2
assert coin_change([2], 3) == -1
assert coin_change([1], 0) == 0""",
    ),
    CodingExample(
        task="Find the longest increasing subsequence",
        solution="""def longest_increasing_subsequence(arr):
    \"\"\"Find length of LIS using patience sorting. O(n log n).\"\"\"
    import bisect
    tails = []
    for num in arr:
        pos = bisect.bisect_left(tails, num)
        if pos == len(tails):
            tails.append(num)
        else:
            tails[pos] = num
    return len(tails)""",
        language="python",
        category="dynamic-programming",
        difficulty="hard",
        tags=["dp", "lis", "binary-search", "patience-sorting"],
        explanation="Maintain tails array where tails[i] = smallest tail of all increasing subsequences of length i+1.",
        test_cases="""assert longest_increasing_subsequence([10, 9, 2, 5, 3, 7, 101, 18]) == 4
assert longest_increasing_subsequence([0, 1, 0, 3, 2, 3]) == 4
assert longest_increasing_subsequence([7, 7, 7, 7]) == 1""",
    ),
    # ── System Design ───────────────────────────────────────
    CodingExample(
        task="Implement a rate limiter using token bucket algorithm",
        solution="""import time

class TokenBucket:
    \"\"\"Token bucket rate limiter.\"\"\"
    def __init__(self, capacity, refill_rate):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.last_refill = time.monotonic()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def allow(self):
        self._refill()
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False""",
        language="python",
        category="system-design",
        difficulty="medium",
        tags=["rate-limiter", "token-bucket", "concurrency"],
        explanation="Tokens refill at constant rate. Each request consumes one token. Bucket has max capacity.",
        test_cases="""b = TokenBucket(5, 10)
assert b.allow() == True
for _ in range(4):
    b.allow()
assert b.allow() == False  # bucket empty""",
    ),
    # ── DevOps / Shell ──────────────────────────────────────
    CodingExample(
        task="Write a Python script to find large files in a directory",
        solution="""import os
from pathlib import Path

def find_large_files(directory, min_size_mb=10):
    \"\"\"Find files larger than min_size_mb in directory.\"\"\"
    results = []
    for path in Path(directory).rglob("*"):
        if path.is_file():
            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb >= min_size_mb:
                results.append((path, size_mb))
    results.sort(key=lambda x: -x[1])
    return results

if __name__ == "__main__":
    import sys
    directory = sys.argv[1] if len(sys.argv) > 1 else "."
    for path, size in find_large_files(directory):
        print(f"{size:8.1f} MB  {path}")""",
        language="python",
        category="devops",
        difficulty="easy",
        tags=["file-system", "cli", "utilities"],
        explanation="Walk directory tree, check file sizes, sort by size descending.",
        test_cases="""from pathlib import Path
Path("_test_big.txt").write_text("x" * 10 * 1024 * 1024)
results = find_large_files(".", min_size_mb=5)
assert len(results) >= 1
Path("_test_big.txt").unlink()""",
    ),
    # ── Testing ─────────────────────────────────────────────
    CodingExample(
        task="Write comprehensive unit tests for a function",
        solution="""import pytest

def add(a, b):
    \"\"\"Add two numbers.\"\"\"
    return a + b

class TestAdd:
    \"\"\"Comprehensive tests for the add function.\"\"\"

    def test_positive_integers(self):
        assert add(2, 3) == 5

    def test_negative_integers(self):
        assert add(-1, -1) == -2

    def test_mixed_sign(self):
        assert add(-1, 1) == 0

    def test_zero(self):
        assert add(0, 5) == 5
        assert add(0, 0) == 0

    def test_floats(self):
        assert add(0.1, 0.2) == pytest.approx(0.3)

    def test_string_concatenation(self):
        assert add("hello", " world") == "hello world"

    def test_type_error(self):
        with pytest.raises(TypeError):
            add("a", 1)""",
        language="python",
        category="testing",
        difficulty="easy",
        tags=["pytest", "testing", "unit-tests"],
        explanation="Test edge cases: zeros, negatives, floats, different types. Use pytest.approx for floats.",
        test_cases="""# Run with: pytest test_add.py -v
# All tests should pass""",
    ),
    # ── API / HTTP ──────────────────────────────────────────
    CodingExample(
        task="Build a simple REST API with FastAPI",
        solution="""from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float
    in_stock: bool = True

items: dict[int, Item] = {}
next_id = 0

@app.get("/items")
def list_items() -> List[dict]:
    return [{"id": k, **v.model_dump()} for k, v in items.items()]

@app.get("/items/{item_id}")
def get_item(item_id: int):
    if item_id not in items:
        raise HTTPException(404, "Item not found")
    return {"id": item_id, **items[item_id].model_dump()}

@app.post("/items")
def create_item(item: Item):
    global next_id
    items[next_id] = item
    next_id += 1
    return {"id": next_id - 1, **item.model_dump()}

@app.delete("/items/{item_id}")
def delete_item(item_id: int):
    if item_id not in items:
        raise HTTPException(404, "Item not found")
    del items[item_id]
    return {"deleted": True}""",
        language="python",
        category="api",
        difficulty="medium",
        tags=["fastapi", "rest", "api", "web"],
        explanation="Pydantic models for validation. In-memory dict storage. CRUD endpoints.",
        test_cases="""from fastapi.testclient import TestClient
client = TestClient(app)
r = client.post("/items", json={"name": "Test", "price": 9.99})
assert r.status_code == 200
item_id = r.json()["id"]
r = client.get(f"/items/{item_id}")
assert r.json()["name"] == "Test"
""",
    ),
    # ── Data Processing ─────────────────────────────────────
    CodingExample(
        task="Parse and analyze a CSV file with Python",
        solution="""import csv
from collections import Counter
from pathlib import Path

def analyze_csv(filepath):
    \"\"\"Read CSV and return summary statistics.\"\"\"
    with open(filepath, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return {"error": "Empty CSV"}

    columns = list(rows[0].keys())
    stats = {"rows": len(rows), "columns": columns, "numeric_stats": {}}

    for col in columns:
        values = [row[col] for row in rows]
        try:
            nums = [float(v) for v in values if v]
            if nums:
                stats["numeric_stats"][col] = {
                    "mean": sum(nums) / len(nums),
                    "min": min(nums),
                    "max": max(nums),
                    "count": len(nums),
                }
        except ValueError:
            freq = Counter(values)
            stats["numeric_stats"][col] = {"unique": len(freq), "top": freq.most_common(3)}

    return stats""",
        language="python",
        category="data-processing",
        difficulty="medium",
        tags=["csv", "data-analysis", "file-io"],
        explanation="Use csv.DictReader for automatic header parsing. Try numeric conversion, fall back to frequency count.",
        test_cases="""import tempfile, os
path = tempfile.mktemp(suffix='.csv')
with open(path, 'w') as f:
    f.write("name,score\\nAlice,95\\nBob,87\\nCarol,92\\n")
stats = analyze_csv(path)
assert stats["rows"] == 3
assert stats["numeric_stats"]["score"]["mean"] == 91.0
os.unlink(path)""",
    ),
]
