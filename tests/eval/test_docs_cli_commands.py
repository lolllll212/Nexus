"""Every command a reader can copy-paste out of the docs must actually parse.

`test_docs_env_vars.py` holds the env vars to the docs. This holds the
**commands**: a flag rename or a removed subcommand should break a doc, not
silently hand the reader an argparse error.

The point is that the check runs the *real* parser (`nexus.cli.build_parser`,
a side-effect-free factory) instead of a hand-maintained list of flags. A
checklist of flags is the same mistake as a checklist of env vars: it drifts.

Fenced blocks are validated strictly with `parse_args` - that is where people
copy-paste from. Inline code spans are validated with `parse_known_args` and
only flag-shaped leftovers are reported, because prose elides argument values
(`--output ... --min-pass-rate ...`) and a strict parse would false-positive on
the ellipsis. Submodule CLIs (`python -m nexus.training.cli`) build their parser
inside `main()`, so those are checked against the module's own source instead.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import re
import shlex
from pathlib import Path

from nexus.cli import build_parser

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

# HANDOFF.md quotes other agents' command lines and records what was once said.
DOC_FILES = sorted(p for p in (REPO_ROOT / "docs").glob("*.md") if p.name != "HANDOFF.md") + [
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "README.md",
]

FENCE = re.compile(r"^\s*```")
INLINE_CODE = re.compile(r"`([^`\n]+)`")
CMD = re.compile(r"^(nexus|python\s+-m\s+nexus[\w.]*)\b(.*)$")
# `nexus train <add|search|...>` - angle brackets mean "one of these", not a token.
ANGLE = re.compile(r"<[^>]*>")


def _strip_comment(line: str) -> str:
    """Drop a trailing `# ...` shell comment; no documented command contains a `#`."""
    return line.split("#", 1)[0]


def _tokenize(text: str) -> list[str] | None:
    """Normalize a documented command into argv, or None if it is not one."""
    line = ANGLE.sub(" ", _strip_comment(text)).replace("[", " ").replace("]", " ")
    match = CMD.match(line.strip())
    if not match:
        return None
    try:
        return shlex.split(line.strip())
    except ValueError:
        return None  # unbalanced quotes; not worth a doc-fix mandate


def _fenced_commands() -> list[tuple[str, list[str]]]:
    """(location, argv) for every command line inside a fenced code block."""
    found: list[tuple[str, list[str]]] = []
    for path in DOC_FILES:
        if not path.exists():
            continue
        inside = False
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FENCE.match(raw):
                inside = not inside
                continue
            if not inside:
                continue
            argv = _tokenize(raw)
            if argv:
                found.append((f"{path.name}:{lineno}", argv))
    return found


def _inline_commands() -> list[tuple[str, list[str]]]:
    """(location, argv) for commands mentioned in inline code spans."""
    found: list[tuple[str, list[str]]] = []
    for path in DOC_FILES:
        if not path.exists():
            continue
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for span in INLINE_CODE.findall(raw):
                argv = _tokenize(span)
                if argv:
                    found.append((f"{path.name}:{lineno}", argv))
    return found


def _main_cli_argv(argv: list[str]) -> list[str] | None:
    """argv for the top-level `nexus` CLI, or None for a submodule CLI."""
    if argv[0] == "nexus":
        return argv[1:]
    if argv[:3] == ["python", "-m", "nexus"]:
        return argv[3:]
    return None


def _submodule(argv: list[str]) -> str | None:
    if len(argv) > 2 and argv[:2] == ["python", "-m"]:
        module = argv[2]
        return module if module.startswith("nexus.") else None
    return None


def _quiet_parse(parser, argv: list[str]):
    """parse_args without letting argparse write usage errors into the test log."""
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        return parser.parse_args(argv)


def test_the_extraction_actually_finds_commands():
    """If the extraction rots, the two real checks below pass on nothing."""
    fenced = _fenced_commands()
    assert len(fenced) >= 8, f"only {len(fenced)} fenced commands found - extraction is stale"
    assert len(_inline_commands()) >= 3, "inline command mentions are no longer being found"
    assert {argv[0] for _, argv in fenced if argv[0] == "nexus"}, "no bare `nexus` commands found"


def test_documented_commands_parse_against_the_real_cli():
    """A copy-pasteable command must be one the CLI accepts."""
    parser = build_parser()
    failures = []
    for where, argv in _fenced_commands():
        main_argv = _main_cli_argv(argv)
        if main_argv is None or not main_argv:
            continue  # submodule CLI, or a bare `python -m nexus`
        try:
            _quiet_parse(parser, main_argv)
        except SystemExit:
            failures.append(f"  {where}: nexus {' '.join(main_argv)}")
    assert (
        not failures
    ), "documented commands the CLI rejects (renamed or removed flag/subcommand?):\n" + "\n".join(failures)


def test_documented_flags_exist():
    """Inline mentions are checked loosely, but an unknown flag is still a bug."""
    parser = build_parser()
    failures = []
    for where, argv in _inline_commands():
        main_argv = _main_cli_argv(argv)
        if main_argv is None or not main_argv:
            continue
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            _, unknown = parser.parse_known_args(main_argv)
        bad = [tok for tok in unknown if tok.startswith("-") and tok != "-"]
        if bad:
            failures.append(f"  {where}: {' '.join(bad)}")
    assert not failures, "documented flags the CLI does not define:\n" + "\n".join(failures)


def test_documented_submodule_commands_exist():
    """`python -m nexus.training.cli ...` must name a real module and real flags."""
    failures = []
    for where, argv in _fenced_commands():
        module = _submodule(argv)
        if module is None:
            continue
        try:
            spec = importlib.util.find_spec(module)
        except (ImportError, ValueError):
            spec = None
        if spec is None or not spec.origin:
            failures.append(f"  {where}: no importable module {module}")
            continue
        source = Path(spec.origin).read_text(encoding="utf-8")
        for flag in (tok for tok in argv[4:] if tok.startswith("-")):
            if f'"{flag}"' not in source and f"'{flag}'" not in source:
                failures.append(f"  {where}: {module} has no {flag}")
    assert not failures, "documented submodule commands that do not exist:\n" + "\n".join(failures)
