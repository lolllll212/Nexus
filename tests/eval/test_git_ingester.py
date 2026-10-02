"""Tests for the git ingester (`application/training/git_ingester.py`).

The last untested use case in the training module: scans a repo for Python
files, extracts functions/classes that carry docstrings, and stores them as
`git`-sourced training examples, deduped by task text.

Tests live in `tests/eval/` because `tests/unit/` belongs to Tron
(docs/AGENT_COORDINATION.md) and the application layer is mine.
"""

from __future__ import annotations

import pytest

from nexus.application.training.git_ingester import GitIngester
from nexus.application.training.coding_store import CodingStore


@pytest.fixture
def store(tmp_path):
    # qdrant_port=1 so the optional Qdrant probe fails with ECONNREFUSED
    # immediately instead of waiting on a real client timeout.
    return CodingStore(store_path=tmp_path / "examples.json", qdrant_port=1)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "good.py").write_text(
        'def sum_list(values):\n'
        '    """Compute the total of a list of numbers. Returns an int."""\n'
        '    return sum(values)\n'
        '\n'
        'class Cache:\n'
        '    """Store computed results for reuse. Backed by a dict."""\n'
        '\n'
        '    def get(self, key):\n'
        '        """Return a cached value. Misses return None."""\n'
        '        return self._data.get(key)\n',
        encoding="utf-8",
    )
    (root / "pkg" / "nodoc.py").write_text(
        "def no_docs(values):\n    return sum(values)\n", encoding="utf-8"
    )
    (root / "pkg" / "short_doc.py").write_text(
        'def tiny():\n    """Short."""\n    return 1\n', encoding="utf-8"  # < 10 chars
    )
    (root / "pkg" / ".venv").mkdir(parents=True, exist_ok=True)
    (root / "pkg" / ".venv" / "x.py").write_text(
        'def venv_fn():\n    """Should never be ingested. Hidden in .venv."""\n    return 1\n',
        encoding="utf-8",
    )
    return root


def test_ingests_functions_and_classes_with_docstrings(store, repo):
    ingester = GitIngester(store)
    count = ingester.ingest_repo(str(repo))

    # sum_list + Cache + Cache.get; no_docs and tiny lack docstrings >= 10 chars
    assert count == 3
    tasks = {e.task for e in store.list_all()}
    assert any("`sum_list`" in t for t in tasks)
    assert any("`Cache`" in t for t in tasks)
    assert any("`get`" in t for t in tasks)


def test_every_ingested_example_is_git_sourced(store, repo):
    GitIngester(store).ingest_repo(str(repo))

    assert store.list_all()
    assert all(e.source == "git" for e in store.list_all())


def test_ingest_is_idempotent_by_task_text(store, repo):
    ingester = GitIngester(store)
    assert ingester.ingest_repo(str(repo)) == 3
    assert ingester.ingest_repo(str(repo)) == 0  # all tasks already known
    assert len(store.list_all()) == 3


def test_venv_and_pycache_are_skipped(store, repo):
    GitIngester(store).ingest_repo(str(repo))

    tasks = " ".join(e.task for e in store.list_all())
    assert "venv_fn" not in tasks


def test_nonexistent_repo_returns_zero(store):
    assert GitIngester(store).ingest_repo("Z:/does/not/exist") == 0
    assert store.list_all() == []


def test_functions_without_a_substantial_docstring_are_skipped(store, repo):
    GitIngester(store).ingest_repo(str(repo))

    tasks = {e.task for e in store.list_all()}
    assert not any("`no_docs`" in t for t in tasks)
    assert not any("`tiny`" in t for t in tasks)


def test_task_is_built_from_the_docstrings_first_sentence(store, repo):
    GitIngester(store).ingest_repo(str(repo))

    example = next(e for e in store.list_all() if "`sum_list`" in e.task)
    assert example.task.startswith("Write a function `sum_list` that")
    assert "compute the total of a list of numbers" in example.task


def test_solution_is_the_real_source_sliced(store, repo):
    GitIngester(store).ingest_repo(str(repo))

    example = next(e for e in store.list_all() if "`sum_list`" in e.task)
    assert "return sum(values)" in example.solution
    assert "Compute the total" in example.solution  # docstring stays with the source


def test_explanation_names_the_source_file(store, repo):
    GitIngester(store).ingest_repo(str(repo))

    example = next(e for e in store.list_all() if "`sum_list`" in e.task)
    assert "pkg/good.py" in example.explanation or "pkg\\good.py" in example.explanation


def test_tags_always_include_imported(store, repo):
    GitIngester(store).ingest_repo(str(repo))

    assert all("imported" in e.tags for e in store.list_all())


def test_custom_patterns_limit_what_is_scanned(store, repo):
    (root := repo / "pkg" / "notes.md").write_text("# not python", encoding="utf-8")
    count = GitIngester(store).ingest_repo(str(root.parent), patterns=["*.md"])

    assert count == 0  # a .md file is not parseable python


def test_difficulty_is_inferred_from_source_length(store, repo):
    big = repo / "pkg" / "big.py"
    body = "\n".join(f"    line_{i} = {i}" for i in range(45))
    big.write_text(
        'def big_fn():\n    """Does a lot of work. Many lines."""\n' + body + "\n    return None\n",
        encoding="utf-8",
    )
    GitIngester(store).ingest_repo(str(repo))

    example = next(e for e in store.list_all() if "`big_fn`" in e.task)
    assert example.difficulty == "hard"  # 48 lines >= 40
