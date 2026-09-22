"""NEXUS eval harness - golden-set grading for the brain.

`python -m nexus.eval` runs the golden set against a real LLM + real tools
(nightly CI job). `from nexus.eval.harness import EvalRunner` runs the same
rubric against fakes inside pytest.
"""

from nexus.eval.harness import EvalCase, EvalResult, EvalRunner, GOLDEN_SET

__all__ = ["EvalCase", "EvalResult", "EvalRunner", "GOLDEN_SET"]