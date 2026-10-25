/*
 * textstats.h — the public "menu" of the textstats library.
 * ==========================================================
 *
 * WHAT IS A HEADER FILE?
 * ----------------------
 * A .h (header) file only *declares* things: it says "these types and
 * functions exist". The matching .c file *defines* them (the real code).
 *
 * Other files (main.c, test_textstats.c, and even Python via ctypes!)
 * only need this header to know how to call the library. Think of it
 * like a restaurant menu: you order from the menu, the kitchen (.c)
 * does the cooking.
 *
 * READ THIS FILE FIRST. It is the whole library in one screen.
 */

#ifndef TEXTSTATS_H   /* "include guard": if some file #includes us twice, */
#define TEXTSTATS_H   /* the second include is skipped. Prevents errors.  */

/*
 * TextStats — a struct: several values bundled into one.
 *
 * In C a function can only return ONE thing, so when our analyzer finds
 * four numbers we pack them into this struct and return the struct.
 *
 * Field meanings (the Python fallback in plugins/c_text_tools implements
 * EXACTLY these rules, so both backends always agree):
 *
 *   chars        - number of bytes in the text (the '\0' terminator is
 *                  NOT counted). For plain ASCII text this equals the
 *                  number of characters. (UTF-8 letters can take 2+
 *                  bytes — handling that is a roadmap exercise!)
 *   words        - number of words. A "word" is a run of characters
 *                  that are not whitespace, e.g. "hi   there" = 2 words.
 *   lines        - number of lines: every '\n' ends a line, and a final
 *                  line without a trailing '\n' still counts.
 *                  "" counts as 0 lines. "a\nb" counts as 2 lines.
 *   longest_word - length (in bytes) of the longest word, 0 if none.
 *
 * NOTE FOR LATER: the field ORDER and types here must match the ctypes
 * Structure in plugins/c_text_tools/__init__.py byte-for-byte. If you
 * add a field here you must add it there too (see EXERCISES.md, E1).
 */
typedef struct {
    long chars;
    long words;
    long lines;
    long longest_word;
} TextStats;

/*
 * textstats_analyze — count chars / words / lines / longest word.
 *
 * `const char *text` means: "a pointer to read-only text". The `const`
 * is a promise: this function will look at the text but never change it.
 *
 * Passing NULL is allowed and returns all zeros (defensive programming:
 * never crash just because a caller handed you nothing).
 */
TextStats textstats_analyze(const char *text);

/*
 * textstats_count_char — how many times does `target` appear in `text`?
 * Example: textstats_count_char("banana", 'a') == 3. NULL text -> 0.
 *
 * This one is NOT exposed as a Nexus tool yet — wiring it up end-to-end
 * is EXERCISES.md E2, your first "full stack C" mission.
 */
long textstats_count_char(const char *text, char target);

/*
 * textstats_title_case — rewrite `text` IN PLACE to Title Case.
 * Example: "hELLO wORLD" becomes "Hello World".
 *
 * Notice there is NO `const` here: this function *modifies* the text it
 * is given. That means the caller must pass a writable buffer
 * (a `char buf[] = "..."` array), never a string literal. See the big
 * warning in test_textstats.c — this is a classic beginner crash.
 *
 * Rules: the first character of each word is upper-cased, the rest of
 * the word is lower-cased. Anything that is not a letter is left alone,
 * so "don't stop" becomes "Don't Stop" (the ' after n stays lower).
 * ASCII only for now. NULL is allowed and does nothing.
 */
void textstats_title_case(char *text);

/*
 * textstats_version — returns the library version as a string, e.g.
 * "1.0.0". Handy to prove from Python that YOUR compiled C code is the
 * thing that is actually loaded.
 */
const char *textstats_version(void);

#endif /* TEXTSTATS_H */
