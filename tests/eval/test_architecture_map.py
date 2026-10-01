"""Keeps docs/architecture-map.md honest.

The map claims a specific adapter is bound to each port. That claim is only
worth anything if something checks it, so this test parses the port->adapter
table out of the markdown and cross-checks it against the DI container.

It runs in tests/eval/ (opencode's area) because it is a verification harness
over real code, not a unit test of a single function. No LLM, no infra: the
container is inspected via `__new__` so nothing is actually built.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nexus.infrastructure.di.container import Container

DOC = Path(__file__).resolve().parents[2] / "docs" / "architecture-map.md"

PORT_MODULE = re.compile(r"^ports/[\w/]+\.py$")
BACKTICKED = re.compile(r"`([^`]+)`")


def _port_rows() -> list[dict[str, str]]:
    """Parse the port table out of the markdown.

    Cell-based rather than one big regex: the port column carries parenthetical
    extras (`EventBus` (`EventPublisher` + `EventSubscriber`)) and the memory
    column may be a backticked class, the word `same`, or an em dash.
    """
    assert DOC.exists(), f"missing {DOC}"
    rows: list[dict[str, str]] = []
    for line in DOC.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        module = BACKTICKED.search(cells[0])
        if not module or not PORT_MODULE.match(module.group(1)):
            continue
        port = BACKTICKED.search(cells[1])
        if not port:
            continue
        rows.append(
            {
                "module": module.group(1),
                "port": port.group(1),
                # The raw cell too: `port` is already unbackticked, so the
                # documented-set test below needs the original to find the
                # extra type names (`EventBus` (`EventPublisher` + ...)).
                "port_cell": cells[1],
                "external": cells[2],
                "memory": cells[3],
            }
        )
    return rows


def _names(cell: str) -> list[str]:
    """Backticked identifiers in a table cell, in order."""
    return BACKTICKED.findall(cell)


def _container_sources() -> str:
    """The DI container's source - the authority for every binding."""
    import inspect

    return inspect.getsource(Container)


def test_architecture_map_exists_and_parses():
    rows = _port_rows()
    assert len(rows) >= 20, f"expected the full port table, parsed {len(rows)} rows"
    modules = {r["module"] for r in rows}
    for expected in (
        "ports/llm_provider.py",
        "ports/memory_repository.py",
        "ports/execution.py",
        "ports/event_bus.py",
        "ports/tool_registry.py",
    ):
        assert expected in modules, f"{expected} missing from the port table"


def test_every_abstract_port_type_is_documented():
    """A new port that nobody documents is a new port nobody knows about."""
    documented: set[str] = set()
    for row in _port_rows():
        documented.update(_names(row["port_cell"]))

    import inspect

    from nexus.domain import ports as ports_pkg

    found: set[str] = set()
    for module_name in (
        "auth",
        "autonomy",
        "cognition",
        "deployment",
        "execution",
        "llm_provider",
        "memory_repository",
        "sandbox",
        "secrets",
        "speech",
        "swarm",
        "tool_registry",
    ):
        module = getattr(ports_pkg, module_name, None)
        if module is None:
            continue
        source = inspect.getsource(module)
        for name in re.findall(r"^class (\w+)\(", source, re.MULTILINE):
            if name.startswith("Noop") or name.endswith("Status"):
                continue
            found.add(name)

    # StreamingLLMProvider is a capability mixin, not a bound port.
    found.discard("StreamingLLMProvider")
    undocumented = found - documented
    assert not undocumented, f"ports missing from docs/architecture-map.md: {sorted(undocumented)}"


def test_documented_adapters_exist_in_the_container_source():
    """Every adapter the map names must be constructed by the container."""
    source = _container_sources()
    checked = 0
    for row in _port_rows():
        for column in ("external", "memory"):
            if row[column].strip() == "—":
                continue
            for adapter in _names(row[column]):
                adapter = adapter.split(" or ")[0].strip()
                checked += 1
                assert (
                    adapter in source
                ), f"{row['port']} -> {adapter} is documented but the container never builds it"
    assert checked > 30, f"only checked {checked} adapter names; the table probably stopped parsing"


def test_memory_backend_column_matches_the_container_branches():
    """`NEXUS_INFRA_BACKEND=memory` swaps exactly the documented set."""
    memory_adapters = {
        "InMemoryRateLimiter",
        "InMemoryEventBus",
        "InMemoryEmbedder",
        "InMemoryMemoryRepository",
        "InMemoryConceptRepository",
        "InMemoryShortTermMemory",
    }
    source = _container_sources()

    for adapter in memory_adapters:
        assert adapter in source, f"{adapter} no longer exists"

    # Every one of them must sit behind an `infra_backend == "memory"` check.
    branches = len(re.findall(r'infra_backend\s*==\s*"memory"', source))
    assert branches == len(
        memory_adapters
    ), f"container has {branches} memory-backend branches, expected {len(memory_adapters)}"

    # Every port backed by an external store must document its in-memory swap.
    external = ("Redis", "Qdrant", "Neo4j", "OpenAIEmbedder")
    for row in _port_rows():
        if not any(adapter in row["external"] for adapter in external):
            continue
        if "StreamingLLMProvider" in row["port"]:
            continue  # capability mixin, never bound on its own
        assert (
            "InMemory" in row["memory"]
        ), f"{row['port']} uses an external store but its memory column says {row['memory']!r}"


def test_sandbox_default_is_docker():
    """AGENTS.md claims DockerSandbox is the default. Keep the claim true."""
    source = _container_sources()
    build = source[source.index("def _build_sandbox") :]
    build = build[: build.index("\n    def ", 10)]
    assert 'if self.config.sandbox_backend != "subprocess"' in build
    assert "DockerSandbox" in build
    assert "SubprocessSandbox" in build


def test_tool_count_matches_the_handler_registry():
    """The map's tool list must equal EXTENDED_HANDLERS, no more, no less."""
    from nexus.infrastructure.adapters.execution.extended_tools import EXTENDED_HANDLERS

    text = DOC.read_text(encoding="utf-8")
    block = text.split("## Built-in tools")[1].split("##")[0]
    documented = set(re.findall(r"`(\w+)`", block))

    assert documented == set(EXTENDED_HANDLERS), (
        f"docs list {sorted(documented - set(EXTENDED_HANDLERS))} extra / "
        f"omits {sorted(set(EXTENDED_HANDLERS) - documented)}"
    )
    assert len(EXTENDED_HANDLERS) == 21


def test_route_module_list_matches_disk():
    """The map's route list must match the files actually on disk."""
    routes_dir = Path(__file__).resolve().parents[2] / "src/nexus/infrastructure/api/routes"
    on_disk = {p.stem for p in routes_dir.glob("*.py") if p.stem != "__init__"}

    text = DOC.read_text(encoding="utf-8")
    block = text.split("## API route modules")[1].split("##")[0]
    documented = set(re.findall(r"`(\w+)`", block))

    assert (
        documented == on_disk
    ), f"docs list {sorted(documented - on_disk)} extra / omit {sorted(on_disk - documented)}"


@pytest.mark.parametrize(
    "doc",
    [
        "dual-loop.md",
        "memory.md",
        "dreaming.md",
        "swarm.md",
        "self-evolution.md",
        "autonomous-goals.md",
        "backup-dr.md",
        "architecture-map.md",
        "agent-onboarding.md",
    ],
)
def test_ops_config_families_are_documented(doc):
    """NEXUS_INFRA_BACKEND, the quota family, goals cap, and backup CLI must be written down."""
    text = (DOC.parent / doc).read_text(encoding="utf-8")
    # Each doc covers the families relevant to it; the map must cover all of them.
    required = {
        "architecture-map.md": [
            "NEXUS_INFRA_BACKEND",
            "NEXUS_QUOTA_CHAT_PER_DAY",
            "NEXUS_QUOTA_TOOL_GEN_PER_DAY",
            "NEXUS_QUOTA_MEMORIES_PER_DAY",
            "NEXUS_GOALS_MAX_ACTIVE",
        ],
        "backup-dr.md": ["NEXUS_INFRA_BACKEND", "nexus backup"],
        "memory.md": ["NEXUS_INFRA_BACKEND"],
        "dual-loop.md": ["NEXUS_INFRA_BACKEND"],
    }.get(doc, [])
    for token in required:
        assert token in text, f"{doc} does not mention {token}"


def test_docs_have_no_mojibake():
    """The pre-2026 docs shipped UTF-8 read as CP1252 ('â?' garbage). Catch a relapse."""
    bad = {"\ufffd", "â€", "Â ", "Ã©", "â€™", "â€œ", "â€\x9d"}
    for path in sorted(DOC.parent.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        offenders = [token for token in bad if token in text]
        assert not offenders, f"{path.name} contains mojibake: {offenders}"


def test_docs_are_utf8_clean_not_cp1252():
    """Belt and braces: the file must decode as strict UTF-8 with no surrogates."""
    for path in sorted(DOC.parent.glob("*.md")):
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:  # pragma: no cover - only on regression
            pytest.fail(f"{path.name} is not valid UTF-8: {exc}")
        assert "�" not in text, f"{path.name} contains U+FFFD replacement characters"
