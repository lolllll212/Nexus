# textstats roadmap — growing your first C project over weeks

You chose the long road (good). This is the staged plan:
each week adds **one new C concept** and **one visible improvement**
to the project. Tick the boxes as you go; commit after each exercise.

> Rule zero, every week: `cd c/textstats && make clean && make test`
> — zero warnings, all tests green — and
> `PYTHONPATH=src pytest tests/unit/test_c_text_tools_plugin.py`
> still passes from the repo root.

Exercise numbers (E1, E2, …) refer to [textstats/EXERCISES.md](textstats/EXERCISES.md),
which has the detailed task + hints for each.

---

## Week 0 — Toolchain & reading the code *(today, ~1 hour)*

**Concepts:** compiler, `make`, warnings, what linking means.

- [ ] Install gcc + make; `gcc --version` works
- [ ] `make`, `make test`, `make demo` all run
- [ ] Read `textstats.h` fully, then `textstats.c`; for every line you
      can't explain, write the question down (then re-read the comments)
- [ ] Explain (out loud!) the difference between `char *p` and `*p`
- [ ] Run the "prove it runs in Nexus" snippet from
      [README.md](README.md) and see `"backend": "c"`

**Done when:** you can predict `textstats_analyze("a bb\nccc")`
by hand before running it.

## Week 1 — Loops, conditions, counters

**Concepts:** state variables (`in_word`), single-pass algorithms,
writing tests first.

- [ ] **E1 — vowel count.** Add a `vowels` field end-to-end
      (C struct → ctypes → Python fallback → tests). This one teaches
      why ABI layout matters.
- [ ] **E3 — sentence count.** Count `.`, `!`, `?` (decide the rules,
      document them in the header, test them).
- [ ] Hand-trace `textstats_analyze("  hi\n")` on paper: char by char,
      what is `in_word` / `word_length` after each step?

**Done when:** C and Python agree on 5+ new test strings you invented,
including empty, all-whitespace, and no-trailing-newline cases.

## Week 2 — Pointers & strings, for real

**Concepts:** writing through a pointer, in-place algorithms,
writable arrays vs string literals.

- [ ] **E4 — reverse words in place** (`"hello world"` → `"olleh dlrow"`),
      no extra buffer allowed. Two-pointer swap.
- [ ] Add `textstats_uppercase(char *text)` using the title-case
      function as your template; expose it in the CLI as `--upper`.
- [ ] Deliberately pass a string literal to a modifying function in a
      scratch file, watch it crash, and explain *why* in a comment.

**Done when:** you can explain what `const` in a signature protects,
and every pointer loop in the file feels boring to read.

## Week 3 — Dynamic memory: `malloc`, `realloc`, `free`

**Concepts:** heap vs stack, growing buffers, memory leaks,
"who owns this memory?" — *the* core C skill.

- [ ] **E5 — remove the 8192-byte limit in `main.c`:** read the whole
      input with a `malloc`'d buffer that doubles via `realloc`;
      `free` it exactly once on every exit path.
- [ ] Feed the CLI a 1 MB generated file
      (`python3 -c "print('word ' * 200000)" > /tmp/big.txt`) — counts correct?
- [ ] Check every `malloc` return value for NULL. Every time. Forever.

**Done when:** `make asan` on the big file is clean and
`valgrind ./textstats /tmp/big.txt` (if installed) reports 0 leaks.

## Week 4 — Build & debugging craft

**Concepts:** separate compilation (`.o` files), `gdb` basics,
sanitizers, reading stack traces.

- [ ] Change the Makefile to compile `textstats.o` separately and link
      it into each program (notice how only changed files rebuild).
- [ ] **E9 — bug hunt drill:** with a partner/stash, introduce an
      off-by-one (e.g. drop the `buffer[bytes_read] = '\0'`), find it
      with `make asan` and a `gdb` breakpoint instead of guessing.
- [ ] Learn 5 gdb commands: `break`, `run`, `next`, `print`, `bt`.

**Done when:** a segfault no longer scares you — your first move is
"rebuild with sanitizers", not "stare at the code".

## Week 5 — Shared libraries & the Python bridge *(the Nexus milestone)*

**Concepts:** `.so` loading, ctypes signatures, struct layout/ABI,
keeping two implementations in sync.

- [ ] **E2 — ship `c_count_char` as a real Nexus tool:** the C function
      already exists; add the Tool, handler, fallback, and tests.
- [ ] Load the plugin through Nexus's real `PluginLoader` (see
      `tests/unit/test_c_text_tools_plugin.py`) and try the tool from
      the API/CLI like any built-in tool.
- [ ] Break the ABI on purpose in a branch (swap two struct fields on
      the Python side only), see garbage numbers, revert. Now you
      *know* why E1's warning exists.

**Done when:** `"backend": "c"` and `"backend": "python-fallback"`
give byte-identical results on your whole test corpus.

## Week 6 — Data structures: word frequencies

**Concepts:** arrays of structs, sorting (`qsort`), and your first
hash map — the jump from "C syntax" to "C programming".

- [ ] **E6 — top-5 most frequent words:** v1 with a fixed array of
      `{char word[32]; long count;}` + linear search. It's O(n²) and
      that's fine — measure where it starts to hurt.
- [ ] v2: replace linear search with a simple open-addressing hash
      table you wrote yourself (djb2 hash is a fine start).
- [ ] Expose as a `c_top_words` Nexus tool. Handle the
      "who frees the returned strings?" question explicitly in the
      header comment.

**Done when:** top-words on a book-sized text is instant in C and you
can draw your hash table on a whiteboard.

## Week 7+ — Choose your adventure

Pick ONE based on what you enjoyed most; each is a real Nexus upgrade:

| Direction | Project | New concepts |
|---|---|---|
| **Performance** | **E8** benchmark C vs Python on 10 MB text; then a minimal **CPython C extension** (`PyArg_ParseTuple`…) replacing ctypes, compare overhead | profiling, reference counting |
| **Correctness** | **E10** UTF-8-aware `chars` (count code points, not bytes) + tests with é/emoji | encodings, bit masks, careful spec-reading |
| **CLI craft** | **E7** `--json` output + multiple files + per-file + total rows (a real `wc` rival) | output formatting, `getopt`, exit-code discipline |
| **Systems** | New `c/mini_redis/`: a tiny TCP key-value server Nexus's memory layer could talk to | sockets, `fork`/event loops — the next big project |
| **Vectors (Nexus-flavoured)** | `c/vecsearch/`: cosine-similarity top-k over float arrays, exposed as a tool next to Nexus's vector memory | `float` math, file formats, numerical care |

**Graduation criterion:** a feature you designed yourself — spec in the
header, failing tests first, C implementation, sanitizers clean,
Python bridge + fallback, docs updated — merged as one tidy PR.

---

## Version milestones (tag these in git as you hit them)

- **v1.0** *(shipped)* — analyze + title-case, CLI, tests, `.so`, Nexus plugin + fallback
- **v1.1** — E1 + E3 (vowels, sentences) — *end of Week 1*
- **v1.2** — E5 unlimited input size — *end of Week 3*
- **v2.0** — E2 + E6 tools live in Nexus (`c_count_char`, `c_top_words`) — *Weeks 5–6*
- **v3.0** — your Week 7+ adventure
