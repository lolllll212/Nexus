"""
Coding system prompt and few-shot retrieval for NEXUS.

Provides coding-specific instructions and retrieves relevant examples
from the training store to inject into the LLM context.
"""

from __future__ import annotations

from typing import Optional

from nexus.application.training.coding_store import CodingStore

CODING_SYSTEM_PROMPT = """You are NEXUS, an expert coding assistant. You write clean, efficient, well-tested code.

## Your capabilities
- Write code in any language (Python, JavaScript, TypeScript, Rust, Go, etc.)
- Debug and fix issues
- Refactor and optimize code
- Write and run tests
- Search and analyze codebases
- Use tools: read_file, write_file, run_python, run_shell, grep, git_info, calculator, diff_text

## Rules
1. Always write complete, runnable code — no placeholders
2. Include error handling where appropriate
3. Add brief docstrings/comments for complex logic
4. Use type hints in Python
5. Prefer standard library over external deps unless asked
6. When fixing bugs, explain the root cause before the fix
7. When multiple approaches exist, pick the most Pythonic/readable one
8. Test your code with the tools available — don't just assume it works

## Tool usage pattern
When writing code:
1. Use read_file to understand existing code first
2. Write the solution with write_file
3. Test it with run_python or run_shell
4. If it fails, read the error, fix, and retry
5. Use diff_text to show what changed

When debugging:
1. Use grep to find relevant code
2. Use read_file to read the context
3. Identify the bug
4. Fix with write_file
5. Verify with run_python
"""


class CodingRAG:
    """Retrieves relevant coding examples for few-shot prompting."""

    def __init__(self, store: CodingStore, max_examples: int = 3) -> None:
        self._store = store
        self._max_examples = max_examples

    def build_coding_prompt(self, task: str, category: Optional[str] = None) -> str:
        """Build a prompt with relevant few-shot examples appended."""
        examples = self._store.search(task, category=category, limit=self._max_examples)

        prompt_parts = [CODING_SYSTEM_PROMPT]

        if examples:
            prompt_parts.append("\n## Relevant examples from training data\n")
            for i, ex in enumerate(examples, 1):
                prompt_parts.append(f"### Example {i}")
                prompt_parts.append(ex.to_prompt())
                prompt_parts.append("")
                ex.use_count += 1

        prompt_parts.append(f"\n## Current task\n{task}")
        return "\n".join(prompt_parts)

    def get_few_shot_context(self, task: str, category: Optional[str] = None) -> str:
        """Get just the few-shot examples text (without the system prompt)."""
        examples = self._store.search(task, category=category, limit=self._max_examples)
        if not examples:
            return ""
        parts = []
        for ex in examples:
            parts.append(ex.to_prompt())
        return "\n---\n".join(parts)
