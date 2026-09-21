"""
Git repository ingester — auto-learn coding patterns from codebases.

Scans a git repo for Python files, extracts functions/classes with docstrings,
and creates training examples from them.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import List, Optional

from nexus.application.training.coding_store import CodingExample, CodingStore


class GitIngester:
    """Extracts coding examples from git repositories."""

    def __init__(self, store: CodingStore) -> None:
        self._store = store

    def ingest_repo(self, repo_path: str, patterns: List[str] = None) -> int:
        """Scan a repo and create training examples from its code."""
        patterns = patterns or ["*.py"]
        repo = Path(repo_path)
        if not repo.exists():
            return 0

        existing_tasks = {e.task for e in self._store.list_all()}
        count = 0

        for pattern in patterns:
            for filepath in repo.rglob(pattern):
                if ".venv" in str(filepath) or "__pycache__" in str(filepath):
                    continue
                examples = self._extract_from_file(filepath, repo)
                for ex in examples:
                    if ex.task not in existing_tasks:
                        ex.source = "git"
                        self._store.add(ex)
                        existing_tasks.add(ex.task)
                        count += 1

        return count

    def _extract_from_file(self, filepath: Path, repo_root: Path) -> List[CodingExample]:
        """Extract function/class definitions as training examples."""
        try:
            source = filepath.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (SyntaxError, Exception):
            return []

        examples = []
        relative_path = str(filepath.relative_to(repo_root))

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                ex = self._extract_function(node, source, relative_path)
                if ex:
                    examples.append(ex)
            elif isinstance(node, ast.ClassDef):
                ex = self._extract_class(node, source, relative_path)
                if ex:
                    examples.append(ex)

        return examples

    def _extract_function(self, node, source: str, filepath: str) -> Optional[CodingExample]:
        """Extract a function as a training example."""
        docstring = ast.get_docstring(node) or ""
        if not docstring or len(docstring) < 10:
            return None

        # Extract function source
        lines = source.split("\n")
        start = node.lineno - 1
        end = node.end_lineno or start + 20
        func_source = "\n".join(lines[start:end])

        # Extract type hints for context
        args = []
        for arg in node.args.args:
            if arg.arg != "self" and arg.arg != "cls":
                args.append(arg.arg)

        task = f"Write a function `{node.name}` that {docstring.split('.')[0].lower().rstrip()}"
        explanation = f"From {filepath}. {docstring}"

        return CodingExample(
            task=task,
            solution=func_source,
            language="python",
            category=self._infer_category(node.name, docstring),
            tags=self._extract_tags(node.name, docstring),
            explanation=explanation,
            difficulty=self._infer_difficulty(func_source),
            source="git",
        )

    def _extract_class(self, node, source: str, filepath: str) -> Optional[CodingExample]:
        """Extract a class as a training example."""
        docstring = ast.get_docstring(node) or ""
        if not docstring or len(docstring) < 10:
            return None

        lines = source.split("\n")
        start = node.lineno - 1
        end = node.end_lineno or start + 50
        class_source = "\n".join(lines[start:min(end, start + 80)])

        methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

        task = f"Implement a `{node.name}` class that {docstring.split('.')[0].lower().rstrip()}"
        explanation = f"From {filepath}. Methods: {', '.join(methods)}. {docstring}"

        return CodingExample(
            task=task,
            solution=class_source,
            language="python",
            category=self._infer_category(node.name, docstring),
            tags=self._extract_tags(node.name, docstring),
            explanation=explanation,
            difficulty=self._infer_difficulty(class_source),
            source="git",
        )

    def _infer_category(self, name: str, docstring: str) -> str:
        text = f"{name} {docstring}".lower()
        if any(w in text for w in ["sort", "search", "binary", "traverse"]):
            return "algorithms"
        if any(w in text for w in ["stack", "queue", "tree", "graph", "list", "map", "cache"]):
            return "data-structures"
        if any(w in text for w in ["api", "endpoint", "route", "server", "http"]):
            return "api"
        if any(w in text for w in ["test", "assert", "mock", "fixture"]):
            return "testing"
        if any(w in text for w in ["parse", "read", "write", "file", "csv", "json"]):
            return "data-processing"
        return "general"

    def _extract_tags(self, name: str, docstring: str) -> List[str]:
        tags = []
        text = f"{name} {docstring}".lower()
        keywords = ["async", "decorator", "generator", "context", "dataclass", "enum",
                     "exception", "iterator", "callback", "factory", "singleton", "adapter"]
        for kw in keywords:
            if kw in text:
                tags.append(kw)
        tags.append("imported")
        return tags

    def _infer_difficulty(self, source: str) -> str:
        lines = len(source.split("\n"))
        if lines < 15:
            return "easy"
        if lines < 40:
            return "medium"
        return "hard"
