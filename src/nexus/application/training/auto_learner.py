"""
Auto-learner — extracts training examples from successful coding sessions.

When NEXUS successfully completes a coding task, this module captures
the task + solution as a new training example for future reference.
"""

from __future__ import annotations

from typing import List, Optional

from nexus.application.training.coding_store import CodingExample, CodingStore


class AutoLearner:
    """Learns from successful coding sessions."""

    def __init__(self, store: CodingStore) -> None:
        self._store = store
        self._min_solution_length = 50
        self._min_quality_score = 0.6

    def should_learn(self, task: str, solution: str, tools_used: list) -> bool:
        """Decide if this session is worth learning from."""
        if len(solution) < self._min_solution_length:
            return False
        # Must have used at least one coding tool
        coding_tools = {"run_python", "write_file", "read_file", "run_shell", "grep"}
        if not coding_tools.intersection(tools_used):
            return False
        # Check if we already have a very similar example
        existing = self._store.search(task, limit=1)
        if existing and existing[0].success_rate > 0.9 and existing[0].use_count > 5:
            return False  # Already have a good example for this
        return True

    def learn(
        self,
        task: str,
        solution: str,
        language: str = "python",
        category: str = "general",
        explanation: str = "",
        test_cases: str = "",
        tools_used: list = None,
        succeeded: bool = True,
        rating: float = 0.0,
    ) -> Optional[CodingExample]:
        """Capture a successful coding session as a training example."""
        if not self.should_learn(task, solution, tools_used or []):
            return None

        # Extract tags from the task
        tags = self._extract_tags(task)

        example = CodingExample(
            task=task,
            solution=solution,
            language=language,
            category=category,
            tags=tags,
            explanation=explanation or "Auto-learned from successful session",
            test_cases=test_cases,
            difficulty=self._infer_difficulty(solution),
            source="auto-learned",
        )
        example.record_use(succeeded, rating)
        self._store.add(example)
        return example

    def learn_from_feedback(
        self,
        example_id: str,
        succeeded: bool,
        rating: float = 0.0,
        improved_solution: Optional[str] = None,
    ) -> bool:
        """Update an existing example based on feedback."""
        ex = self._store.get(example_id)
        if not ex:
            return False

        ex.record_use(succeeded, rating)

        # If the user provided an improved solution, update it
        if improved_solution and len(improved_solution) > len(ex.solution) * 0.5:
            ex.solution = improved_solution
            ex.version += 1

        self._store.update(ex)
        return True

    def _extract_tags(self, task: str) -> List[str]:
        tags = []
        task_lower = task.lower()
        # Language detection
        lang_keywords = {
            "python": ["python", "def ", "class ", "import ", "pip"],
            "javascript": ["javascript", "js", "const ", "let ", "npm"],
            "typescript": ["typescript", "ts", "interface ", "type "],
            "rust": ["rust", "fn ", "struct ", "impl ", "cargo"],
            "go": ["go ", "func ", "package ", "goroutine"],
        }
        for lang, keywords in lang_keywords.items():
            if any(kw in task_lower for kw in keywords):
                tags.append(lang)
                break

        # Pattern detection
        patterns = {
            "sorting": ["sort", "order"],
            "searching": ["search", "find", "lookup"],
            "recursion": ["recursive", "recursion"],
            "dp": ["dynamic", "memoization", "tabulation"],
            "graph": ["graph", "node", "edge", "bfs", "dfs"],
            "tree": ["tree", "binary", "node"],
            "string": ["string", "substring", "palindrome"],
            "api": ["api", "endpoint", "http", "rest"],
            "database": ["sql", "query", "database", "orm"],
            "testing": ["test", "assert", "mock"],
        }
        for tag, keywords in patterns.items():
            if any(kw in task_lower for kw in keywords):
                tags.append(tag)

        return tags or ["general"]

    def _infer_difficulty(self, solution: str) -> str:
        lines = len(solution.split("\n"))
        if lines < 15:
            return "easy"
        if lines < 40:
            return "medium"
        return "hard"
