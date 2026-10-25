# Learning C inside Nexus — the `textstats` project

> **Goal:** learn real C by building something Nexus can actually use —
> a small C library that counts and transforms text, first as a
> standalone command-line program, then as a **native Nexus tool**
> called from Python. Beginner-friendly, multi-week, no toy throwaway
> code: everything you write here ships in the repo.

Nexus already has pure-Python text tools (`plugins/sample_text_tools/`:
`word_count`, `capitalize`). Your project is their native twin, written
in C from scratch. By the end you will understand pointers, structs,
strings, Makefiles, shared libraries, and how Python talks to C.

## The stages

```
 Stage 1              Stage 2                Stage 3               Stage 4+
 pure C CLI    ──▶    shared library  ──▶    Nexus plugin   ──▶    grow it
 c/textstats/         libtextstats.so        plugins/              ROADMAP.md
 ./textstats          (same .c file!)        c_text_tools/         EXERCISES.md
```

Stages 1–3 already work today at a beginner-readable level — your job
is to *understand every line*, then grow the project along
[ROADMAP.md](ROADMAP.md) doing the tasks in
[textstats/EXERCISES.md](textstats/EXERCISES.md).

## Layout

```
c/
├── README.md                 ← you are here
├── ROADMAP.md                ← the multi-week plan (v1 → v2 → v3…)
└── textstats/
    ├── textstats.h           ← READ FIRST: the library "menu" (types + functions)
    ├── textstats.c           ← the library itself (the real learning)
    ├── main.c                ← the CLI program (thin shell over the library)
    ├── test_textstats.c      ← unit tests in plain C, run with `make test`
    ├── Makefile              ← build recipes (read its comments too)
    ├── EXERCISES.md          ← E1…E10: hands-on tasks, easiest first
    └── examples/sample.txt   ← demo input

plugins/c_text_tools/
├── __init__.py               ← ctypes bridge: TOOLS + HANDLERS for Nexus
└── README.md

tests/unit/test_c_text_tools_plugin.py  ← Python tests (pass with OR without the .so)
```

## Quickstart (5 minutes)

You need a C compiler and make:

- **Linux:** `sudo apt install build-essential` (Debian/Ubuntu)
- **macOS:** `xcode-select --install`
- **Windows:** use WSL2 (Ubuntu) — by far the smoothest path for this repo

```bash
cd c/textstats

make                       # build CLI + libtextstats.so + tests
make test                  # run the C unit tests
make demo                  # see it work

echo "hello Nexus world" | ./textstats
./textstats examples/sample.txt
./textstats --title examples/sample.txt
```

Then prove your C code runs inside Nexus (from the repo root):

```bash
PYTHONPATH=src python3 - <<'EOF'
import asyncio
from plugins.c_text_tools import HANDLERS, BACKEND, NATIVE_VERSION
print("backend:", BACKEND, "| C library version:", NATIVE_VERSION)
print(asyncio.run(HANDLERS["c_text_stats"]({"text": "hello Nexus world"})))
print(asyncio.run(HANDLERS["c_title_case"]({"text": "hELLO nEXUS"})))
EOF
```

`"backend": "c"` means the bytes went Python → ctypes → **your
compiled C function** → back. Delete `libtextstats.so` (or run
`make clean`) and the same script still works via a pure-Python
fallback (`"backend": "python-fallback"`) — keep reading to see why.

Run the Python test suite for the plugin:

```bash
PYTHONPATH=src pytest tests/unit/test_c_text_tools_plugin.py -v
```

## How the pieces connect

```
            ┌────────────────────────── Nexus (Python) ──────────────────────────┐
            │  PluginLoader discovers plugins/* → registers TOOLS + HANDLERS     │
            │                                                                    │
  ReAct /   │   plugins/c_text_tools/__init__.py                                 │
  API call  │     handler({"text": ...})                                         │
     ───────┼──▶    ├─ .so found? ──▶ ctypes ──▶ libtextstats.so  (your C)       │
            │     └─ otherwise ─────▶ pure-Python fallback (same rules)        │
            │                                                                    │
            │   result: {"words": 3, ..., "backend": "c"}                        │
            └────────────────────────────────────────────────────────────────────┘

  Standalone, no Python anywhere:
    main.c ──calls──▶ textstats.c        test_textstats.c ──calls──▶ textstats.c
         (the same library code is reused three ways — that is the lesson)
```

## Concept map — where each C idea lives in this code

| Concept | Where to see it | One-line summary |
|---|---|---|
| Variables, `if/else`, loops | `textstats.c` everywhere | The only ingredients the analyzer needs |
| Strings = chars + `'\0'` | top comment of `textstats.c` | No length stored; you walk to the terminator |
| Pointers `*p`, `p++` | every loop in `textstats.c` | `*p` = char at address `p`; equals `text[i]` style |
| `const char *` vs `char *` | `textstats.h` signatures | Read-only promise vs "I will modify this" |
| `struct` return values | `TextStats` in `textstats.h` | Bundle 4 results into one return value |
| Header vs source files | `textstats.h` / `textstats.c` | Declarations (menu) vs definitions (kitchen) |
| `NULL` checks / segfaults | start of each library function | Never dereference a pointer you haven't checked |
| `(unsigned char)` cast + `<ctype.h>` | `isspace`/`toupper` calls | Avoid undefined behaviour on bytes ≥ 128 |
| Arrays vs string literals | warning box in `test_textstats.c` | `char s[]="…"` writable; `char *s="…"` read-only — crash! |
| `argc`/`argv`, exit codes | `main.c` | How the OS hands your program its arguments |
| `FILE*`, `fopen`/`fread`/`fclose` | `main.c` | `fread` does not add `'\0'` — you do |
| `#define`, header guards | `main.c`, `textstats.h` | Constants and double-include protection |
| Warnings as lessons | `Makefile` (`-Wall -Wextra`) | Zero warnings is the goal, always |
| Shared library `.so` | `Makefile` (`-fPIC -shared`) | Code other programs (Python!) load at runtime |
| Python ↔ C ABI | `plugins/c_text_tools/__init__.py` | ctypes `Structure` must mirror the C struct exactly |

Concepts deliberately NOT used yet — they are your roadmap:
`malloc/free` (Week 3), dynamic arrays & hash maps (Week 6),
threads/sockets (choose-your-adventure, Week 7+).

## Rules of the project (how to work like a C programmer)

1. **After every change:** `make test` must stay green and warning-free.
2. **Test first:** write a failing `CHECK(...)` in `test_textstats.c`,
   then write C until it passes. Do the same in Python when you touch
   the plugin.
3. **Keep the twins in sync:** the C library and the Python fallback in
   `plugins/c_text_tools/__init__.py` implement identical rules, and
   the ctypes struct mirrors `textstats.h` field-for-field. If you
   change one side, change the other (E1 makes you practice this).
4. **Read compiler warnings.** They are the cheapest C tutor that exists.
5. **Small commits:** one exercise per commit, message like
   `c(textstats): E1 add vowel count`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `make: gcc: No such file or directory` | Install a compiler (see Quickstart) |
| `missing separator` from make | Recipe lines in the Makefile need a real TAB, not spaces |
| Python says `"backend": "python-fallback"` but you ran `make` | Run Python from the repo so `c/textstats/libtextstats.so` is found, or `make plugin` to copy it into `plugins/c_text_tools/`; check with `ls c/textstats/*.so` |
| `Segmentation fault` | You touched memory you don't own — usually a NULL/invalid pointer or writing to a string literal. Run `make asan`; it prints the exact file:line |
| Test passes in C but Python numbers differ | The twins drifted: compare `textstats.c` rules with `_analyze_python`, and the struct with `_TextStats` |
| Weird counts on text with é/emoji | Expected in v1: `chars` counts **bytes** (UTF-8 letters = 2+ bytes). E10 is the fix |

## Where to go next

1. Read `textstats.h`, then `textstats.c` top to bottom (30 min).
2. `make test`, `make demo` — then break something on purpose and watch a test fail.
3. Open [ROADMAP.md](ROADMAP.md) and start Week 1 + E1.
