"""Tests for the coding-training use cases: `CodingStore`, `CodingExample`, `AutoLearner`.

These live in `tests/eval/` because `tests/unit/` belongs to Tron (see
docs/AGENT_COORDINATION.md) and the application layer is mine. Do not move them
without checking that lane first.

Both of these modules were untested, and writing the tests turned up two real
defects, each pinned by a test below:

* `CodingStore.add_batch` stamped `updated_at` on the first example only. It
  looped `for e in examples` but did `self._examples.extend(examples)` and
  `return` inside that loop, so only `examples[0]` ever got its timestamp
  refreshed and the remaining iterations were dead code.
* `AutoLearner.learn_from_feedback` bumped `version` itself and then called
  `CodingStore.update`, which bumps it again - every improved solution jumped
  two versions instead of one.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nexus.application.training.auto_learner import AutoLearner
from nexus.application.training.coding_store import CodingExample, CodingStore

STALE = "2000-01-01T00:00:00+00:00"


@pytest.fixture
def store(tmp_path):
    # qdrant_port=1 so the optional Qdrant probe fails with ECONNREFUSED
    # immediately instead of waiting on a real client timeout.
    return CodingStore(store_path=tmp_path / "examples.json", qdrant_port=1)


def _example(task: str = "sort a list", **kwargs) -> CodingExample:
    return CodingExample(task=task, solution="print(sorted(values))", **kwargs)


# --------------------------------------------------------------------------
# CodingExample
# --------------------------------------------------------------------------


def test_success_rate_is_one_when_never_used():
    assert CodingExample().success_rate == 1.0


def test_record_use_tracks_counts_and_smooths_rating():
    ex = CodingExample()
    ex.record_use(succeeded=True, rating=1.0)
    assert (ex.use_count, ex.success_count, ex.fail_count) == (1, 1, 0)
    assert ex.avg_rating == pytest.approx(0.2)  # alpha = 0.2 into a 0.0 prior
    ex.record_use(succeeded=False, rating=0.0)
    assert ex.fail_count == 1
    assert ex.success_rate == pytest.approx(0.5)
    assert ex.avg_rating == pytest.approx(0.2)  # rating 0.0 is ignored entirely, not averaged in


def test_to_dict_drops_the_embedding_and_from_dict_ignores_unknown_keys():
    ex = _example()
    ex.embedding = [0.1, 0.2, 0.3]
    assert "embedding" not in ex.to_dict()
    restored = CodingExample.from_dict({**ex.to_dict(), "embedding": [0.1], "who_is_this": "nobody"})
    assert restored.id == ex.id
    assert restored.embedding == [0.1]  # from_dict is lenient: takes an embedding back if given
    assert not hasattr(restored, "who_is_this")


def test_to_prompt_and_search_text():
    ex = _example(tags=["sorting"], category="algorithms", explanation="Use built-in sort")
    prompt = ex.to_prompt()
    assert "Task: sort a list" in prompt
    assert "Approach: Use built-in sort" in prompt
    assert "```python" in prompt
    assert "Test:" not in prompt  # test_cases is empty

    ex.test_cases = "assert f([]) == []"
    assert "Test:" in ex.to_prompt()
    assert "sorting algorithms" in ex.search_text()


# --------------------------------------------------------------------------
# CodingStore
# --------------------------------------------------------------------------


def test_add_get_and_reload_from_disk(tmp_path):
    store = CodingStore(store_path=tmp_path / "examples.json", qdrant_port=1)
    added = store.add(_example())
    assert store.get(added.id) is added

    reopened = CodingStore(store_path=tmp_path / "examples.json", qdrant_port=1)
    assert [e.id for e in reopened.list_all()] == [added.id]


def test_update_bumps_version_once_and_replaces_the_entry(store):
    ex = store.add(_example())
    ex.solution = "print('updated')"
    assert store.update(ex) is True
    assert store.get(ex.id).solution == "print('updated')"
    assert store.get(ex.id).version == ex.version


def test_update_and_delete_report_missing_ids(store):
    ghost = CodingExample(id="nope", task="t")
    assert store.update(ghost) is False
    assert store.delete("nope") is False


def test_delete_removes_the_entry_and_persists(tmp_path):
    store = CodingStore(store_path=tmp_path / "examples.json", qdrant_port=1)
    keep = store.add(_example(task="keep me"))
    drop = store.add(_example(task="drop me"))

    assert store.delete(drop.id) is True
    assert [e.id for e in store.list_all()] == [keep.id]

    reopened = CodingStore(store_path=tmp_path / "examples.json", qdrant_port=1)
    assert [e.id for e in reopened.list_all()] == [keep.id]


def test_add_batch_stamps_every_example_not_just_the_first(store):
    """Regression: only `examples[0]` used to get a fresh `updated_at`."""
    examples = [_example(task=f"task {i}") for i in range(3)]
    for ex in examples:
        ex.updated_at = STALE

    assert store.add_batch(examples) == 3

    assert len(store.list_all()) == 3
    fresh = [e for e in store.list_all() if e.updated_at != STALE]
    assert len(fresh) == 3, f"only {len(fresh)}/3 examples got a refreshed updated_at"


def test_add_batch_of_nothing_is_a_no_op(store):
    assert store.add_batch([]) == 0
    assert store.list_all() == []


def test_search_filters_by_category_and_honours_limit(store):
    algo = store.add(_example(task="sort a list", category="algorithms", tags=["sorting"]))
    store.add(_example(task="build a REST endpoint", category="web", tags=["api"]))

    assert [e.id for e in store.search("sort")] == [algo.id]
    assert [e.id for e in store.search("sort", category="web")] == []
    assert len(store.search("a list REST", limit=1)) == 1
    assert store.search("nothing matches this") == []


def test_search_boosts_better_used_examples(store):
    plain = store.add(_example(task="sort a list"))
    proven = store.add(_example(task="sort a list"))
    for _ in range(6):
        proven.record_use(succeeded=True, rating=1.0)

    assert [e.id for e in store.search("sort")] == [proven.id, plain.id]


def test_record_outcome_updates_the_stored_example(store):
    ex = store.add(_example())
    assert store.record_outcome(ex.id, succeeded=True, rating=0.5) is True
    stored = store.get(ex.id)
    assert stored.use_count == 1 and stored.success_count == 1
    assert store.record_outcome("nope", succeeded=True) is False


def test_quality_filters_and_deprecate(store):
    good = store.add(_example(task="good"))
    for _ in range(6):
        good.record_use(succeeded=True, rating=1.0)
    bad = store.add(_example(task="bad"))
    for _ in range(4):
        bad.record_use(succeeded=False)
    unused = store.add(_example(task="unused"))

    # Quirk, pinned on purpose: success_rate defaults to 1.0 for a never-used
    # example, so `unused` (1.0) outranks `bad` (0.0 + 4 uses = 0.4).
    assert [e.id for e in store.get_top_rated(limit=2)] == [good.id, unused.id]
    assert [e.id for e in store.get_underused(min_uses=2)] == [unused.id]
    assert [e.id for e in store.get_low_quality(min_success_rate=0.5)] == [bad.id]

    assert store.deprecate(unused.id) is True
    assert store.get(unused.id).difficulty == "deprecated"
    assert store.deprecate("nope") is False


def test_export_version_writes_a_snapshot_file(store, tmp_path):
    store.add(_example())
    path = store.export_version("v1")
    assert path == tmp_path / "coding_examples_v1.json"
    assert "sort a list" in path.read_text(encoding="utf-8")


def test_stats_aggregates(store):
    store.add(_example(task="a", category="algorithms", language="python"))
    store.add(_example(task="b", category="web", language="go"))
    store.record_outcome(store.list_all()[0].id, succeeded=True)

    stats = store.stats()
    assert stats["total"] == 2
    assert stats["categories"] == {"algorithms": 1, "web": 1}
    assert stats["languages"] == {"python": 1, "go": 1}
    assert stats["total_uses"] == 1
    assert stats["overall_success_rate"] == pytest.approx(1.0)
    assert stats["qdrant_connected"] is False


# --------------------------------------------------------------------------
# AutoLearner
# --------------------------------------------------------------------------

LONG_SOLUTION = "def sort(values):\n    return sorted(values)\n" + "# padding\n" * 10
EASY_SOLUTION = "def sort(values):\n    return sorted(values)\n" * 2  # 6 lines, still >= 50 chars


def test_should_learn_requires_a_substantial_solution_and_a_coding_tool(store):
    learner = AutoLearner(store)
    assert learner.should_learn("task", "too short", ["run_python"]) is False
    assert learner.should_learn("task", LONG_SOLUTION, []) is False
    assert learner.should_learn("task", LONG_SOLUTION, ["get_weather"]) is False
    assert learner.should_learn("task", LONG_SOLUTION, ["run_python"]) is True


def test_should_learn_declines_when_a_strong_duplicate_already_exists(store):
    learner = AutoLearner(store)
    existing = store.add(CodingExample(task="sort a python list", solution=LONG_SOLUTION))
    for _ in range(6):
        existing.record_use(succeeded=True, rating=1.0)

    assert learner.should_learn("sort a python list", LONG_SOLUTION, ["run_python"]) is False


def test_learn_stores_a_tagged_example(store):
    learner = AutoLearner(store)
    learned = learner.learn(
        task="write a python function to sort a list",
        solution=LONG_SOLUTION,
        tools_used=["run_python"],
    )

    assert learned is not None
    assert learned.source == "auto-learned"
    assert learned.use_count == 1 and learned.success_count == 1
    assert "python" in learned.tags
    assert "sorting" in learned.tags
    assert learned.difficulty in {"easy", "medium", "hard"}
    assert [e.id for e in store.list_all()] == [learned.id]


def test_learn_returns_none_when_the_session_is_not_worth_learning_from(store):
    learner = AutoLearner(store)
    assert learner.learn(task="t", solution="short", tools_used=["run_python"]) is None
    assert store.list_all() == []


def test_learn_from_feedback_bumps_the_version_exactly_once(store):
    """Regression: `AutoLearner` and `CodingStore.update` both bumped `version`."""
    ex = store.add(CodingExample(task="task", solution=LONG_SOLUTION))
    assert ex.version == 1

    assert AutoLearner(store).learn_from_feedback(ex.id, True, 0.8, LONG_SOLUTION * 2) is True

    stored = store.get(ex.id)
    assert stored.version == 2, f"version went 1 -> {stored.version}; exactly one bump was intended"
    assert stored.solution == LONG_SOLUTION * 2


def test_learn_from_feedback_bumps_version_once_even_without_a_new_solution(store):
    ex = store.add(CodingExample(task="task", solution=LONG_SOLUTION))
    AutoLearner(store).learn_from_feedback(ex.id, succeeded=False, rating=0.0)
    stored = store.get(ex.id)
    assert stored.version == 2
    assert stored.fail_count == 1


def test_learn_from_feedback_ignores_a_trivial_rewrite(store):
    ex = store.add(CodingExample(task="task", solution=LONG_SOLUTION))
    AutoLearner(store).learn_from_feedback(ex.id, True, 0.5, "x")
    assert store.get(ex.id).solution == LONG_SOLUTION


def test_learn_from_feedback_reports_an_unknown_id(store):
    assert AutoLearner(store).learn_from_feedback("nope", True) is False


def test_difficulty_is_inferred_from_solution_length(store):
    learner = AutoLearner(store)
    easy = learner.learn(task="sort list", solution=EASY_SOLUTION, tools_used=["grep"])
    medium = learner.learn(
        task="sort list", solution="\n".join(f"line {i}" for i in range(20)), tools_used=["grep"]
    )
    hard = learner.learn(
        task="sort list", solution="\n".join(f"line {i}" for i in range(50)), tools_used=["grep"]
    )
    assert easy is not None and easy.difficulty == "easy"
    assert medium is not None and medium.difficulty == "medium"
    assert hard is not None and hard.difficulty == "hard"


def test_updated_at_is_recent_iso_utc_after_a_write(store):
    before = datetime.now(UTC)
    ex = store.add(_example())
    assert datetime.fromisoformat(ex.updated_at) >= before
