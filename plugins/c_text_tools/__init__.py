"""
c_text_tools — NEXUS plugin backed by a C library (ctypes).
============================================================

This plugin is the "plug into Nexus" stage of the C learning project
in ``c/textstats/``. The real work is done by ``libtextstats.so``,
compiled from ``c/textstats/textstats.c``::

    cd c/textstats && make          # builds libtextstats.so
    cd c/textstats && make plugin   # (optional) copies it next to here

Conforms to the NEXUS plugin contract:
    TOOLS: list[Tool]
    HANDLERS: dict[str, Callable]

GRACEFUL DEGRADATION (by design)
--------------------------------
If the shared library has not been built yet, this module still
imports fine and every handler falls back to a pure-Python
implementation of the exact same rules. That way Nexus (and CI)
never break just because someone hasn't run ``make`` yet. Each
result includes ``"backend": "c"`` or ``"python-fallback"`` so it is
always obvious which implementation actually ran — seeing ``"c"``
means YOUR compiled C code just executed inside Nexus.

HOW ctypes WORKS, IN ONE PARAGRAPH
----------------------------------
``ctypes`` is Python's built-in way to call C functions in a shared
library. You describe the C types in Python (the ``_TextStats``
Structure below mirrors the struct in textstats.h field-for-field),
load the .so, declare each function's argument/return types, and
then call them almost like Python functions. No C compiler needed
at runtime, no extra dependencies.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.value_objects.schema import JSONSchema

# ----------------------------------------------------------------------
# Step 1: mirror the C struct from textstats.h, field for field.
# `long` in C is ctypes.c_long. ORDER MATTERS — it is a memory layout.
# ----------------------------------------------------------------------


class _TextStats(ctypes.Structure):
    _fields_ = [
        ("chars", ctypes.c_long),
        ("words", ctypes.c_long),
        ("lines", ctypes.c_long),
        ("longest_word", ctypes.c_long),
    ]


# ----------------------------------------------------------------------
# Step 2: find and load libtextstats(.so/.dylib/.dll), if it exists.
# Search order: next to this file (after `make plugin`), then the
# build folder c/textstats/ (after a plain `make`).
# ----------------------------------------------------------------------


def _library_names() -> List[str]:
    if sys.platform.startswith("win"):
        return ["textstats.dll", "libtextstats.dll"]
    if sys.platform == "darwin":
        return ["libtextstats.dylib", "libtextstats.so"]
    return ["libtextstats.so"]


def _load_native() -> Optional[ctypes.CDLL]:
    here = Path(__file__).resolve().parent
    repo_root = here.parents[1]  # plugins/c_text_tools -> repo root
    search_dirs = [here, repo_root / "c" / "textstats"]

    for directory in search_dirs:
        for name in _library_names():
            candidate = directory / name
            if not candidate.exists():
                continue
            try:
                lib = ctypes.CDLL(str(candidate))
            except OSError:
                continue  # wrong arch / corrupt build — try the next one
            # Step 3: declare the C function signatures.
            lib.textstats_analyze.argtypes = [ctypes.c_char_p]
            lib.textstats_analyze.restype = _TextStats
            lib.textstats_count_char.argtypes = [ctypes.c_char_p, ctypes.c_char]
            lib.textstats_count_char.restype = ctypes.c_long
            lib.textstats_title_case.argtypes = [ctypes.c_char_p]
            lib.textstats_title_case.restype = None
            lib.textstats_version.argtypes = []
            lib.textstats_version.restype = ctypes.c_char_p
            return lib
    return None


_LIB = _load_native()

#: "c" when libtextstats was loaded, else "python-fallback".
BACKEND: str = "c" if _LIB is not None else "python-fallback"

#: Version string reported by the C library (None in fallback mode).
NATIVE_VERSION: Optional[str] = (
    _LIB.textstats_version().decode("utf-8") if _LIB is not None else None
)

# ----------------------------------------------------------------------
# Pure-Python fallback: a line-by-line translation of the C rules in
# textstats.h. Keep it in sync with the C code (that is the point of
# the exercise) — tests assert both backends agree.
# ----------------------------------------------------------------------


def _analyze_python(text: str) -> Dict[str, int]:
    if text == "":
        return {"chars": 0, "words": 0, "lines": 0, "longest_word": 0}
    words = text.split()
    return {
        # C counts bytes; encode so non-ASCII counts match the C code.
        "chars": len(text.encode("utf-8")),
        "words": len(words),
        "lines": text.count("\n") + (0 if text.endswith("\n") else 1),
        "longest_word": max((len(w.encode("utf-8")) for w in words), default=0),
    }


def _title_case_python(text: str) -> str:
    out: List[str] = []
    in_word = False
    for ch in text:
        if ch.isspace():
            in_word = False
            out.append(ch)
        elif not in_word:
            in_word = True
            out.append(ch.upper())
        else:
            out.append(ch.lower())
    return "".join(out)


def analyze_text(text: str) -> Dict[str, Any]:
    """Sync helper shared by the async handler (handy for quick tests)."""
    if _LIB is not None:
        # c_char_p needs bytes; the C side sees UTF-8 + a '\0' terminator
        # (ctypes adds the terminator for us).
        stats = _LIB.textstats_analyze(text.encode("utf-8"))
        result: Dict[str, Any] = {
            "chars": int(stats.chars),
            "words": int(stats.words),
            "lines": int(stats.lines),
            "longest_word": int(stats.longest_word),
        }
    else:
        result = dict(_analyze_python(text))
    result["backend"] = BACKEND
    return result


def title_case_text(text: str) -> Dict[str, Any]:
    """Sync helper shared by the async handler (handy for quick tests)."""
    if _LIB is not None:
        # The C function modifies its argument in place, so we must hand
        # it a *writable* buffer — create_string_buffer gives us exactly
        # the `char buf[] = "..."` from the C tests, Python-side.
        buffer = ctypes.create_string_buffer(text.encode("utf-8"))
        _LIB.textstats_title_case(buffer)
        return {"result": buffer.value.decode("utf-8"), "backend": BACKEND}
    return {"result": _title_case_python(text), "backend": BACKEND}


# ----------------------------------------------------------------------
# NEXUS plugin contract: TOOLS + HANDLERS
# ----------------------------------------------------------------------

TOOLS: List[Tool] = [
    Tool(
        id="c_text_stats",
        name="c_text_stats",
        description=(
            "Count chars (bytes), words, lines and longest-word length of a "
            "text using a native C library (libtextstats) when built, with "
            "a pure-Python fallback. Result field 'backend' says which ran."
        ),
        input_schema=JSONSchema(
            type="object",
            properties={"text": {"type": "string", "description": "Text to analyze"}},
            required=["text"],
        ),
        output_schema=JSONSchema(
            type="object",
            properties={
                "chars": {"type": "integer"},
                "words": {"type": "integer"},
                "lines": {"type": "integer"},
                "longest_word": {"type": "integer"},
                "backend": {"type": "string"},
            },
        ),
        status=ToolStatus.READY,
    ),
    Tool(
        id="c_title_case",
        name="c_title_case",
        description=(
            "Convert a text to Title Case using a native C library "
            "(libtextstats) when built, with a pure-Python fallback. "
            "Result field 'backend' says which ran. ASCII rules: first "
            "character of each word upper-cased, the rest lower-cased."
        ),
        input_schema=JSONSchema(
            type="object",
            properties={"text": {"type": "string", "description": "Text to convert"}},
            required=["text"],
        ),
        output_schema=JSONSchema(
            type="object",
            properties={
                "result": {"type": "string"},
                "backend": {"type": "string"},
            },
        ),
        status=ToolStatus.READY,
    ),
]


async def _c_text_stats(params: Dict[str, Any]) -> Dict[str, Any]:
    text = params.get("text")
    if not isinstance(text, str):
        return {"error": "text must be a string"}
    return analyze_text(text)


async def _c_title_case(params: Dict[str, Any]) -> Dict[str, Any]:
    text = params.get("text")
    if not isinstance(text, str):
        return {"error": "text must be a string"}
    return title_case_text(text)


HANDLERS: Dict[str, Any] = {
    "c_text_stats": _c_text_stats,
    "c_title_case": _c_title_case,
}
