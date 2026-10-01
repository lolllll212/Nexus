"""Keeps the docs navigable: no dead file links, no dead anchors, no orphan pages.

`test_architecture_map.py` checks that `docs/architecture-map.md` tells the
truth about the *code*. This file checks the quieter failure mode: documentation
that is structurally broken — a link that 404s, an anchor that lands nowhere, a
page nobody links to. None of that shows up in review, and all of it rots
silently.

The anchor check earned its place immediately: `architecture-map.md` carried a
`[Ops configuration](#ops-configuration)` link for the whole life of the file
while the section it pointed at did not exist. Nobody noticed for months
because clicking a dead `#fragment` just scrolls nowhere.

Runs in tests/eval/ (Astra's area) for the same reason as its sibling: it is a
verification harness over real content, not a unit test of a single function.
No LLM, no infra, no network.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"

# docs/index.md is the human front door, so every other page must be reachable
# from it. Three files are exempt by design, not by convenience:
#   index.md   - it is the index
#   README.md  - the index of this directory
#   HANDOFF.md - an append-only agent board, not documentation
ORPHAN_EXEMPT = {"index.md", "README.md", "HANDOFF.md"}
MARKER_EXEMPT = {"HANDOFF.md"}

# [label](target) - the target stops at whitespace or the closing paren, and an
# optional "title" is dropped.
LINK = re.compile(r"\[([^\]]*)\]\(\s*<?([^\s)<>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$", re.MULTILINE)
EXPLICIT_ANCHOR = re.compile(r"<a\s+(?:name|id)=[\"']([^\"']+)[\"']")
UNRESOLVED = re.compile(r"\b(?:TODO|FIXME|TBD|WIP)\b")

FENCE = re.compile(r"^(?:```|~~~).*?^(?:```|~~~)\s*$", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")
INLINE_DELIMS = re.compile(r"(`+)")


def _sources() -> list[Path]:
    """Every markdown file whose links we hold to account for."""
    return sorted(DOCS.glob("*.md")) + [REPO_ROOT / "AGENTS.md", REPO_ROOT / "README.md"]


def _body(path: Path) -> str:
    """File text with fenced code blocks removed.

    A ```` ```bash ```` sample full of `# comments` would otherwise invent
    headings, and a commented-out path in a snippet would invent dead links.
    """
    return FENCE.sub("", path.read_text(encoding="utf-8"))


def _local_links(path: Path) -> list[tuple[str, str]]:
    """(label, target) for every non-http link in the file.

    Inline code spans are dropped first: a doc that *shows* link syntax, e.g.
    ``` `[Ops configuration](#ops-configuration)` ```, is quoting a link, not
    shipping one. GitHub does not render links inside code spans either, so
    counting them produces false alarms on prose about links.
    """
    text = INLINE_CODE.sub("", _body(path))
    return [
        (label, target)
        for label, target in LINK.findall(text)
        if not target.startswith(("http://", "https://", "mailto:", "tel:"))
    ]


def _anchor(text: str) -> str:
    """GitHub's heading -> anchor rule.

    Lowercase, delete everything that is not a word character / space / hyphen,
    then turn *each* remaining space into its own hyphen. Collapsing runs of
    whitespace would be tidier and wrong: "Architecture & Dependency" loses the
    ampersand and keeps both spaces, so GitHub's real id is
    ``architecture--dependency``, not ``architecture-dependency``.
    """
    text = INLINE_DELIMS.sub(r"\1", text)  # keep the code, drop the backticks
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"\s", "-", text.strip())


def _anchors(path: Path) -> set[str]:
    """Every anchor a link may target: heading slugs plus explicit <a id> tags.

    Repeated headings get GitHub's ``-1``/``-2`` suffixes, so they are counted
    rather than collapsed.
    """
    body = _body(path)
    found: set[str] = set()
    seen: dict[str, int] = {}
    for _, title in HEADING.findall(body):
        slug = _anchor(title)
        seen[slug] = seen.get(slug, 0) + 1
        found.add(slug if seen[slug] == 1 else f"{slug}-{seen[slug] - 1}")
    found.update(m.group(1).lower() for m in EXPLICIT_ANCHOR.finditer(body))
    return found


def _resolve(source: Path, target: str) -> tuple[Path | None, str]:
    """Split a link target into (file, fragment). The file may not exist."""
    file_part, _, fragment = target.partition("#")
    if not file_part:
        return source, fragment
    candidate = (source.parent / file_part).resolve()
    return (candidate if candidate.exists() else None), fragment


def test_docs_directory_is_populated():
    """Guard against the glob silently matching nothing after a docs/ move."""
    found = sorted(p.name for p in DOCS.glob("*.md"))
    assert len(found) >= 10, f"docs/ looks wrong: only {found}"
    assert "index.md" in found, "docs/index.md is the entry point and must exist"


def test_anchor_slugs_follow_github_rules(tmp_path):
    """The slug logic itself, pinned to GitHub's behaviour.

    Without this the anchor check is only as trustworthy as my memory of how
    GitHub turns a heading into an id.
    """
    page = tmp_path / "page.md"
    page.write_text(
        "## Ops configuration\n"
        "\n"
        "## Ops Configuration\n"  # duplicate heading -> -1 suffix
        "\n"
        "## The `NEXUS_QUOTA_*` family\n"  # backticks drop, inner text stays
        "\n"
        "## Clean Architecture & Dependency Rule\n"  # punctuation and & drop
        "\n"
        '<a id="handbook"></a>\n',
        encoding="utf-8",
    )
    assert _anchors(page) == {
        "ops-configuration",
        "ops-configuration-1",
        "the-nexus_quota_-family",
        "clean-architecture--dependency-rule",
        "handbook",
    }


def test_links_inside_code_spans_are_not_links(tmp_path):
    """Prose that quotes link syntax must not be counted as a shipped link."""
    page = tmp_path / "page.md"
    page.write_text(
        "```bash\ncurl http://localhost:8000/docs/gone.md\n```\n"
        "\n"
        "See `[gone](nowhere.md)` for the old path.\n",
        encoding="utf-8",
    )
    assert _local_links(page) == []


def test_relative_file_links_resolve():
    """Every local link points at a file that exists."""
    broken = [
        f"{path.relative_to(REPO_ROOT)}: [{label}]({target}) -> {target_path} does not exist"
        for path in _sources()
        for label, target in _local_links(path)
        if (target_path := _resolve(path, target)[0]) is None
    ]
    assert not broken, "dead doc links:\n" + "\n".join(sorted(broken))


def test_anchor_links_resolve():
    """Every ``#fragment`` matches a heading (or explicit id) in the file it points at.

    Only checked for markdown targets — a fragment on a non-markdown file is
    somebody else's business.
    """
    cache: dict[Path, set[str]] = {}
    dangling: list[str] = []

    for path in _sources():
        for label, target in _local_links(path):
            dest, fragment = _resolve(path, target)
            if not fragment or dest is None or dest.suffix.lower() != ".md":
                continue
            if dest not in cache:
                cache[dest] = _anchors(dest)
            if fragment.lower() not in cache[dest]:
                dangling.append(
                    f"{path.relative_to(REPO_ROOT)}: [{label}]({target})"
                    f" -> no heading slug '{fragment}' in {dest.relative_to(REPO_ROOT)}"
                )

    assert not dangling, "dangling anchors:\n" + "\n".join(sorted(dangling))


def test_no_orphan_docs():
    """Every doc is reachable from docs/index.md.

    Cross-links between pages are not enough: index.md is what a human opens
    first, so a page only reachable from a sibling is effectively invisible.
    """
    index_targets = {target for _, target in _local_links(DOCS / "index.md")}
    index_targets |= set(EXPLICIT_ANCHOR.findall(_body(DOCS / "index.md")))

    orphans = sorted(
        path.name
        for path in DOCS.glob("*.md")
        if path.name not in ORPHAN_EXEMPT and not any(Path(t).name == path.name for t in index_targets if t)
    )
    assert not orphans, f"docs not linked from docs/index.md: {orphans}"


def test_no_unresolved_markers_in_docs():
    """No TODO/FIXME/TBD/WIP left in shipped documentation.

    HANDOFF.md is exempt: it is a live board whose whole job is to hold open
    work, so "TODO" there is information, not rot.
    """
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{line_no}: {line.strip()}"
        for path in _sources()
        if path.name not in MARKER_EXEMPT
        for line_no, line in enumerate(_body(path).splitlines(), 1)
        if UNRESOLVED.search(line)
    ]
    assert not offenders, "unresolved markers in docs:\n" + "\n".join(offenders)
