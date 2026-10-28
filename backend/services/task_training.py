"""Real-task RL training: sandboxed coding tasks with objective verification.

Each task is a piece of real engineering work (write a module, fix a bug,
refactor) executed in a fresh throwaway workspace. The reward is OBJECTIVE:
the task ships with a verification script, and the score is whether the
generated code actually passes it - first try (10.0), after one repair
round (7.5), or not at all (3.0). Passing transcripts are stored as
coding exemplars so the brain literally trains on its own successful work.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.services import llm as llm_service
from backend.services import tools as tools_service
from backend.services import training as training_service

_CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.S)

_TASK_SYSTEM = (
    "You are a senior engineer completing a coding task. Reply with EXACTLY "
    "ONE complete Python code block containing the whole file. No prose "
    "before or after. The file must satisfy the verification exactly."
)


def _extract_code(reply: str) -> str:
    blocks = _CODE_BLOCK.findall(reply or "")
    if blocks:
        return "\n\n".join(b.strip() for b in blocks).strip()
    text = (reply or "").strip()
    return text if ("def " in text or "class " in text) else ""


def _run_verify(workspace: Path, verify: str, timeout: float = 30.0) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-c", verify],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = ((proc.stdout or "") + (proc.stderr or ""))[-800:]
    return proc.returncode == 0, output


TASK_CORPUS = [
    {
        "id": "code-dedupe",
        "category": "coding",
        "instruction": (
            "Create a module 'dedupe.py' with a function dedupe(items) that "
            "removes duplicates from a list while preserving the original order. "
            "It must handle empty lists."
        ),
        "filename": "dedupe.py",
        "verify": (
            "from dedupe import dedupe\n"
            "assert dedupe([3, 1, 3, 2, 1]) == [3, 1, 2]\n"
            "assert dedupe([]) == []\n"
            "assert dedupe(['a', 'a', 'a']) == ['a']\n"
            "print('VERIFY PASS')"
        ),
        "rubric": ["Code runs", "Order preserved", "Empty input handled"],
    },
    {
        "id": "code-fizzbuzz",
        "category": "coding",
        "instruction": (
            "Create 'fizzbuzz.py' with fizzbuzz(n) returning a list of the "
            "strings '1'..n where multiples of 3 become 'Fizz', multiples of 5 "
            "become 'Buzz', and multiples of both become 'FizzBuzz'. Numbers "
            "that are not multiples stay as strings of themselves."
        ),
        "filename": "fizzbuzz.py",
        "verify": (
            "from fizzbuzz import fizzbuzz\n"
            "assert fizzbuzz(15)[14] == 'FizzBuzz'\n"
            "assert fizzbuzz(3) == ['1', '2', 'Fizz']\n"
            "assert fizzbuzz(5)[4] == 'Buzz'\n"
            "assert fizzbuzz(1) == ['1']\n"
            "print('VERIFY PASS')"
        ),
        "rubric": ["Code runs", "Fizz/Buzz rules correct", "Edge case n=1"],
    },
    {
        "id": "debug-off-by-one",
        "category": "debugging",
        "instruction": (
            "The function below is supposed to return the list [1, 2, ..., n] "
            "but is broken. Create 'fix_range.py' containing the CORRECTED "
            "function counts(n).\n\nBROKEN CODE:\n"
            "def counts(n):\n    return list(range(n))\n\n"
            "Example: counts(3) must return [1, 2, 3]."
        ),
        "filename": "fix_range.py",
        "verify": (
            "from fix_range import counts\n"
            "assert counts(3) == [1, 2, 3]\n"
            "assert counts(1) == [1]\n"
            "assert counts(0) == []\n"
            "print('VERIFY PASS')"
        ),
        "rubric": ["Off-by-one fixed", "Edge cases handled", "Code runs"],
    },
    {
        "id": "code-lru",
        "category": "coding",
        "instruction": (
            "Create 'lru_cache.py' with a class LRUCache(capacity) that has "
            "get(key) (returns -1 on miss) and put(key, value). Both operate in "
            "O(1); evicting the least-recently-used entry when over capacity. "
            "Getting a key counts as using it."
        ),
        "filename": "lru_cache.py",
        "verify": (
            "from lru_cache import LRUCache\n"
            "c = LRUCache(2)\n"
            "c.put(1, 1)\n"
            "c.put(2, 2)\n"
            "assert c.get(1) == 1\n"
            "c.put(3, 3)\n"
            "assert c.get(2) == -1\n"
            "c.put(4, 4)\n"
            "assert c.get(1) == -1\n"
            "assert c.get(3) == 3\n"
            "print('VERIFY PASS')"
        ),
        "rubric": ["Evicts least-recently-used", "get refreshes recency", "O(1) design"],
    },
    {
        "id": "code-csv",
        "category": "coding",
        "instruction": (
            "Create 'parse_csv.py' with parse_csv(text) that parses simple "
            "comma-separated text (first line is the header) into a list of "
            "dicts keyed by the header names, with string values stripped."
        ),
        "filename": "parse_csv.py",
        "verify": (
            "from parse_csv import parse_csv\n"
            "rows = parse_csv('name, age\\nAlice, 30\\nBob, 25')\n"
            "assert rows == [{'name': 'Alice', 'age': '30'}, {'name': 'Bob', 'age': '25'}]\n"
            "assert parse_csv('') == []\n"
            "print('VERIFY PASS')"
        ),
        "rubric": ["Header keys correct", "Values stripped", "Empty input handled"],
    },
    {
        "id": "code-emails",
        "category": "coding",
        "instruction": (
            "Create 'emails.py' with extract_emails(text) that returns a "
            "sorted list of unique email addresses found in the text."
        ),
        "filename": "emails.py",
        "verify": (
            "from emails import extract_emails\n"
            "t = 'Contact a@x.com or b@y.org; dup a@x.com. Also c@z.io.'\n"
            "assert extract_emails(t) == ['a@x.com', 'b@y.org', 'c@z.io']\n"
            "assert extract_emails('none here') == []\n"
            "print('VERIFY PASS')"
        ),
        "rubric": ["Regex correct", "Deduplicated", "Sorted output"],
    },
    {
        "id": "debug-none-guard",
        "category": "debugging",
        "instruction": (
            "The function below crashes when 'data' is None or a key is "
            "missing. Create 'safe_get.py' with a FIXED safe_name(data) that "
            "returns data['user']['name'] or the fallback 'unknown' instead of "
            "crashing.\n\nBROKEN CODE:\n"
            "def safe_name(data):\n    return data['user']['name']\n"
        ),
        "filename": "safe_get.py",
        "verify": (
            "from safe_get import safe_name\n"
            "assert safe_name({'user': {'name': 'Ash'}}) == 'Ash'\n"
            "assert safe_name(None) == 'unknown'\n"
            "assert safe_name({}) == 'unknown'\n"
            "assert safe_name({'user': {}}) == 'unknown'\n"
            "print('VERIFY PASS')"
        ),
        "rubric": ["None handled", "Missing keys handled", "Valid input still works"],
    },
    {
        "id": "code-retry",
        "category": "coding",
        "instruction": (
            "Create 'retry_call.py' with retry_call(fn, times=3) that calls "
            "fn() up to `times` times, returning the first successful result "
            "(fn returns a truthy value), and None if all attempts fail. Each "
            "failed call must actually re-invoke fn."
        ),
        "filename": "retry_call.py",
        "verify": (
            "from retry_call import retry_call\n"
            "calls = {'n': 0}\n"
            "def flaky():\n"
            "    calls['n'] += 1\n"
            "    return 'ok' if calls['n'] >= 3 else None\n"
            "assert retry_call(flaky) == 'ok'\n"
            "assert calls['n'] == 3\n"
            "assert retry_call(lambda: None) is None\n"
            "print('VERIFY PASS')"
        ),
        "rubric": ["Retries on falsy", "Returns first success", "All-fail returns None"],
    },
    {
        "id": "code-anagrams",
        "category": "coding",
        "instruction": (
            "Create 'anagrams.py' with group_anagrams(words) that groups a list "
            "of words into a list of sorted lists of anagrams."
        ),
        "filename": "anagrams.py",
        "verify": (
            "from anagrams import group_anagrams\n"
            "g = group_anagrams(['eat', 'tea', 'tan', 'ate', 'nat', 'bat'])\n"
            "assert sorted(sorted(gr) for gr in g) == [['ate', 'eat', 'tea'], ['bat'], ['nat', 'tan']]\n"
            "assert group_anagrams([]) == []\n"
            "print('VERIFY PASS')"
        ),
        "rubric": ["Grouping correct", "Groups sorted", "Empty input handled"],
    },
    {
        "id": "code-wordcount",
        "category": "coding",
        "instruction": (
            "Create 'wordcount.py' with word_counts(text) returning a dict of "
            "lowercased word -> count, ignoring punctuation."
        ),
        "filename": "wordcount.py",
        "verify": (
            "from wordcount import word_counts\n"
            "wc = word_counts('The cat, the dog. THE end!')\n"
            "assert wc == {'the': 3, 'cat': 1, 'dog': 1, 'end': 1}\n"
            "assert word_counts('') == {}\n"
            "print('VERIFY PASS')"
        ),
        "rubric": ["Case-insensitive", "Punctuation ignored", "Counts correct"],
    },
]


def _store_exemplar(instruction: str, code: str) -> int:
    known = {e.get("instruction") for e in training_service._load_examples()}
    if instruction in known:
        return 0
    training_service._save_examples(
        training_service._load_examples()
        + [{"instruction": instruction, "input": instruction, "output": code[:1200]}]
    )
    return 1


async def _run_single(task: dict, workspace: Path, repair: bool) -> dict:
    attempts: list[dict] = []
    feedback = ""
    final_code = ""
    passed = False
    max_attempts = 2 if repair else 1

    for attempt in range(1, max_attempts + 1):
        user = task["instruction"]
        if feedback:
            user += (
                "\n\nPREVIOUS ATTEMPT FAILED VERIFICATION. Error output:\n"
                + feedback[:800]
                + "\n\nYour previous code:\n"
                + (final_code or "(none)")[:1500]
                + "\n\nReturn the FIXED complete file as one Python code block."
            )
        content, _r = await llm_service._call_llm(_TASK_SYSTEM, [{"role": "user", "content": user}])
        code = _extract_code(content)
        if not code:
            attempts.append({"attempt": attempt, "passed": False, "output": "no code block in reply"})
            feedback = "no code block found in the reply"
            continue

        (workspace / task["filename"]).write_text(code, encoding="utf-8")
        passed, output = _run_verify(workspace, task["verify"])
        attempts.append({"attempt": attempt, "passed": passed, "output": output[-400:]})
        final_code = code
        if passed:
            break
        feedback = output

    score = 10.0 if (passed and len(attempts) == 1) else (7.5 if passed else 3.0)
    return {
        "passed": passed,
        "score": score,
        "attempts": attempts,
        "final_code": final_code,
        "verify_output": attempts[-1]["output"] if attempts else "",
    }


async def run_task_round(n: int = 2, repair: bool = True) -> dict:
    """Run n not-yet-attempted real tasks: code -> verify -> repair -> reward."""
    pool = list(TASK_CORPUS)
    scored_qs = {p.get("q") for p in training_service.RL_STATE["pairs"]}
    done = []
    exemplars = 0

    for task in pool:
        if len(done) >= max(1, min(n, len(pool))):
            break
        if task["instruction"] in scored_qs:
            continue

        workspace = Path(tempfile.mkdtemp(prefix="nexus-task-"))
        try:
            outcome = await _run_single(task, workspace, repair)
        except Exception as exc:
            outcome = {
                "passed": False,
                "score": 0.0,
                "attempts": [],
                "final_code": "",
                "verify_output": "runner error: " + str(exc)[:200],
            }
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

        tools_service.bb_put("task:" + task["id"], outcome)
        entry = training_service._record_training_pair(
            task["instruction"],
            outcome["final_code"][:1200] or "(no code produced)",
            outcome["score"],
            outcome["verify_output"][-400:],
            "task-" + task["category"],
            llm_service.LLM_STATE.get("model", ""),
            "verification",
        )
        if outcome["passed"]:
            exemplars += _store_exemplar(task["instruction"], outcome["final_code"])
        done.append(
            {
                "id": task["id"],
                "score": entry["score"],
                "passed": outcome["passed"],
                "attempts": len(outcome["attempts"]),
                "verify_tail": outcome["verify_output"][-120:],
            }
        )
    return {"ok": True, "trained": len(done), "exemplars_stored": exemplars, "results": done}
