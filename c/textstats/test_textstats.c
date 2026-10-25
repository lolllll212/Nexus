/*
 * test_textstats.c — unit tests for the textstats library.
 * ========================================================
 *
 * No test framework needed: a CHECK macro that records failures,
 * prints where they happened, and makes the program exit non-zero
 * if anything failed. `make test` runs this file.
 *
 * WHY TESTS MATTER FOR LEARNING:
 * when you do the exercises in EXERCISES.md you will change
 * textstats.c. Run `make test` after every change — green means
 * "your change didn't break the old behaviour". Professional C
 * programmers work exactly like this.
 *
 * Write the test for your new feature BEFORE writing the feature.
 * Watch it fail, then make it pass. That loop is called TDD.
 */

#include <stdio.h>    /* printf                    */
#include <stdlib.h>   /* EXIT_SUCCESS, EXIT_FAILURE */
#include <string.h>   /* strcmp                    */

#include "textstats.h"

static int checks_run = 0;
static int checks_failed = 0;

/*
 * CHECK(condition): if the condition is false, report the file and
 * line and count a failure — but keep running the remaining tests so
 * you see ALL problems at once, not just the first.
 * (__FILE__ and __LINE__ are filled in automatically by the compiler.)
 */
#define CHECK(condition)                                            \
    do {                                                            \
        checks_run++;                                               \
        if (!(condition)) {                                         \
            checks_failed++;                                        \
            printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
        }                                                           \
    } while (0)

int main(void)
{
    /* ---- textstats_analyze: the basics --------------------------- */

    TextStats hello = textstats_analyze("hello world");
    CHECK(hello.chars == 11);
    CHECK(hello.words == 2);
    CHECK(hello.lines == 1);
    CHECK(hello.longest_word == 5);

    /* Empty string: everything zero, and (by our rule) 0 lines. */
    TextStats empty = textstats_analyze("");
    CHECK(empty.chars == 0);
    CHECK(empty.words == 0);
    CHECK(empty.lines == 0);
    CHECK(empty.longest_word == 0);

    /* NULL must be safe (no crash) and return zeros. */
    TextStats nothing = textstats_analyze(NULL);
    CHECK(nothing.chars == 0 && nothing.words == 0 && nothing.lines == 0);

    /* ---- lines ---------------------------------------------------- */

    CHECK(textstats_analyze("one\ntwo three\n").lines == 2);
    CHECK(textstats_analyze("one\ntwo").lines == 2);   /* no trailing \n */
    CHECK(textstats_analyze("\n").lines == 1);
    CHECK(textstats_analyze("a\n\nb").lines == 3);

    /* ---- words / longest word with messy whitespace ---------------- */

    TextStats messy = textstats_analyze("  a   bb\tccc  \n");
    CHECK(messy.words == 3);
    CHECK(messy.longest_word == 3);
    CHECK(textstats_analyze("one\ntwo three\n").words == 3);
    CHECK(textstats_analyze("one\ntwo three\n").longest_word == 5);

    /* ---- textstats_count_char --------------------------------------- */

    CHECK(textstats_count_char("banana", 'a') == 3);
    CHECK(textstats_count_char("banana", 'z') == 0);
    CHECK(textstats_count_char("", 'a') == 0);
    CHECK(textstats_count_char(NULL, 'a') == 0);

    /* ---- textstats_title_case ----------------------------------------
     *
     * WARNING — THE classic beginner C crash:
     *
     *    char *s = "hello";        // s points at a READ-ONLY literal
     *    textstats_title_case(s);  // BOOM: segfault, undefined behaviour
     *
     *    char s[] = "hello";       // s is your own writable array: OK!
     *    textstats_title_case(s);  // fine
     *
     * String literals live in read-only memory. Anything a function
     * will modify must be in an array (or malloc'd memory) you own.
     */
    char a[] = "hELLO wORLD";
    textstats_title_case(a);
    CHECK(strcmp(a, "Hello World") == 0);

    char b[] = "don't stop";
    textstats_title_case(b);
    CHECK(strcmp(b, "Don't Stop") == 0);

    char c[] = "";
    textstats_title_case(c);
    CHECK(strcmp(c, "") == 0);

    textstats_title_case(NULL);   /* must simply do nothing, not crash */

    /* ---- verdict ------------------------------------------------------ */

    printf("%d checks, %d failed\n", checks_run, checks_failed);
    if (checks_failed == 0) {
        printf("ALL TESTS PASSED\n");
        return EXIT_SUCCESS;
    }
    return EXIT_FAILURE;
}
