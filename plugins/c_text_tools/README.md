# c_text_tools — Nexus plugin backed by C

Exposes two tools implemented in C (the `textstats` library in
[`../../c/textstats/`](../../c/textstats/)) and called from Python
through `ctypes`:

| Tool id | What it does |
|---|---|
| `c_text_stats` | Count chars (bytes), words, lines, longest word |
| `c_title_case` | Convert text to Title Case (C modifies the buffer in place) |

## Build the C side

```bash
cd c/textstats
make            # builds libtextstats.so (plugin finds it there)
make plugin     # optional: also copy the .so into this folder
```

If the `.so` is missing, the plugin still loads and answers using a
pure-Python fallback with identical rules. Every result contains
`"backend": "c"` or `"backend": "python-fallback"` so you always know
which implementation ran.

This plugin is Stage 3 of the C learning project — start with
[`../../c/README.md`](../../c/README.md), see
[`../../c/ROADMAP.md`](../../c/ROADMAP.md) for the multi-week plan and
[`../../c/textstats/EXERCISES.md`](../../c/textstats/EXERCISES.md) for
hands-on tasks (E2 wires up a third tool, `c_count_char`, end-to-end).
