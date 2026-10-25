# Exercises — do them in order, one commit each

Each exercise says **what** to build, **which files** you'll touch, and
hides hints under "details" folds — try for at least 20 minutes before
peeking. Difficulty: ⭐ warm-up · ⭐⭐ core skill · ⭐⭐⭐ stretch.

**The ritual for every exercise**

1. Write a failing test first (`CHECK(...)` in `test_textstats.c`,
   and/or a case in `tests/unit/test_c_text_tools_plugin.py`).
2. `make test` → watch it fail.
3. Write the smallest C that makes it pass.
4. Update the Python twin so both backends agree.
5. `make clean && make test` (zero warnings) + pytest. Commit:
   `c(textstats): E1 add vowel count`.

---

## E1 ⭐⭐ — Add a `vowels` counter, end-to-end

Count vowels (`aeiouAEIOU`) in `textstats_analyze`.

**Touch:** `textstats.h` (new struct field — **at the end** of the
struct), `textstats.c`, `test_textstats.c`, `main.c` (print it),
`plugins/c_text_tools/__init__.py` (`_TextStats`, `_analyze_python`,
output schema, result dict), `tests/unit/test_c_text_tools_plugin.py`.

**Why it matters:** the ctypes `_TextStats` must match the C struct's
memory layout byte-for-byte. Add the field in one place and not the
other and Python will read garbage (or shifted values) with *no error
message*. This is the single most important lesson of the project.

<details><summary>Hint</summary>

Write a tiny helper `static int is_vowel(char c)` in `textstats.c`
using `strchr("aeiouAEIOU", c) != NULL`, or a chain of `||` — both
fine. Call it inside the existing walk; don't loop twice.
Expected: `"hello Nexus"` → vowels 4 (e, o, e, u).
</details>

## E2 ⭐⭐ — Ship `c_count_char` as a Nexus tool

`textstats_count_char()` exists in C and is already declared in the
ctypes setup, but no Nexus tool calls it. Add one: input
`{"text": str, "char": str}` (exactly one character, else
`{"error": ...}` like the math plugin), output `{"count", "backend"}`.

**Touch:** `plugins/c_text_tools/__init__.py` only (TOOLS + HANDLERS +
a `_count_char_python` fallback), plus Python tests. Zero C changes —
feel how the earlier struct/signature work pays off.

<details><summary>Hint</summary>

ctypes: `_LIB.textstats_count_char(text.encode(), char.encode())`.
Fallback: `text.count(char)` — for a single ASCII char this matches
the C byte-loop exactly.
</details>

## E3 ⭐ — Sentence counting

Add `sentences` to the stats: count of `.` `!` `?` that are followed
by whitespace or end-of-string (so `3.14` is not a sentence end).
Document your exact rule in `textstats.h` and mirror it in Python.

<details><summary>Hint</summary>

Inside the walk you can peek at the *next* char with `*(p + 1)` —
safe because the string always ends with `'\0'`, so `p + 1` is never
past valid memory. That peek-ahead trick is everywhere in parsers.
</details>

## E4 ⭐⭐ — Reverse each word in place

`void textstats_reverse_words(char *text)`:
`"hello Nexus"` → `"olleh suxeN"`. No second buffer, no `malloc`.

<details><summary>Hint</summary>

Find a word's start and end pointers, then swap from both ends
toward the middle with a temp `char`. Sketch it on paper for a
3-letter word first. Whitespace runs (leading/double/trailing
spaces) are where the bugs hide — test them.
</details>

## E5 ⭐⭐⭐ — Remove the 8192-byte input limit (your first `malloc`)

`main.c` reads into a fixed array. Replace it with a heap buffer:
start at 4096 bytes, double with `realloc` whenever it fills, NUL-terminate,
`free` before **every** `return`. Test with a multi-MB file; run `make asan`.

<details><summary>Hint</summary>

```c
size_t cap = 4096, len = 0;
char *buf = malloc(cap);
if (buf == NULL) { perror("malloc"); return 1; }
// loop: if len + chunk + 1 > cap → cap *= 2 → realloc (into a TEMP
// pointer first! `buf = realloc(buf, ...)` leaks/loses data on failure)
```

Ownership rule of thumb to internalise: *every `malloc` in your code
should have exactly one obvious `free` you can point at.*
</details>

## E6 ⭐⭐⭐ — Top-5 most frequent words

v1 (this week): fixed table, no hash map yet.

```c
#define MAX_WORDS 1024
#define MAX_WORD_LEN 32
typedef struct { char word[MAX_WORD_LEN]; long count; } WordCount;
```

Tokenise (reuse the whitespace logic), lower-case each word, linear-search
the table, bump or insert; then pick the top 5 (`qsort` with a comparator
is a great stretch goal). Print from a new `--top` CLI mode. Decide and
document: what happens to punctuation (`"dog."` vs `"dog"`)? Words longer
than 31 chars? (Truncate *safely* — never overflow `word[]`.)

v2 (Week 6 of the roadmap): swap linear search for your own hash table.

## E7 ⭐⭐ — `--json` output for the CLI

`./textstats --json file` prints
`{"chars":…,"words":…,"lines":…,"longest_word":…}` on one line.
Start with plain `printf`; notice there's nothing magic about JSON —
it's just carefully printed text. Bonus: multiple file arguments with
a `total` line, like `wc`.

## E8 ⭐⭐ — Benchmark: is C actually faster?

Generate ~10 MB of text, time: the CLI vs a Python one-liner using
`plugins.c_text_tools._analyze_python` vs the ctypes path
(`time.perf_counter`, 20 runs, report median). Write results into
`c/textstats/BENCH.md` with your machine specs and one paragraph:
*where does ctypes overhead show up, and for which input sizes does
the Python fallback win?*

## E9 ⭐⭐ — Bug-hunt drill (debugging craft)

In a throwaway branch, introduce ONE classic bug — delete the
`buffer[bytes_read] = '\0';` line, or change `<` to `<=` somewhere
subtle. Then find it *without reading the diff*: `make asan`, a `gdb`
session (`break textstats_analyze`, `run`, `print`, `next`), and your
tests. Write down the exact moment the tool told you the answer.

## E10 ⭐⭐⭐ — UTF-8-aware character counting

Today `chars` counts bytes, so `"héllo"` reports 6. Add
`codepoints` counting real Unicode characters: in UTF-8, a byte with
high bits `10xxxxxx` is a *continuation* byte, everything else starts
a new character. `(byte & 0xC0) != 0x80` → new character.
Mirror in Python with `len(text)` and add é/emoji tests to both suites.
(Title-casing non-ASCII correctly is a much bigger job — leave it,
document it.)

---

*Finished E1–E10? You are no longer a C beginner. Pick a direction
from "Week 7+ — Choose your adventure" in [../ROADMAP.md](../ROADMAP.md)
(a mini-Redis server and a cosine-similarity tool are waiting).*
