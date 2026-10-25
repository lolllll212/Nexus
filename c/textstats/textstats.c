/*
 * textstats.c — the implementation ("kitchen") of the textstats library.
 * =======================================================================
 *
 * HOW TO READ THIS FILE (beginner edition)
 * ----------------------------------------
 * Every function here is built from just three ingredients you may
 * already know: variables, if/else, and a loop walking over a string.
 *
 * THE ONE BIG IDEA — how C strings work:
 *   A C string is just characters in memory, one after another, ending
 *   with a special zero byte written '\0' (the "null terminator").
 *
 *       "hi"  in memory:   'h'  'i'  '\0'
 *                           ^    ^     ^
 *                         text[0] text[1] text[2]
 *
 *   To process a string you walk from the first character until you
 *   meet '\0'. You will see this loop shape everywhere in C:
 *
 *       for (const char *p = text; *p != '\0'; p++) { ... }
 *
 *   `p` is a POINTER — a variable holding the *address* of a character.
 *   `*p` means "the character p currently points at", and `p++` moves
 *   to the next character. It is exactly equivalent to indexing:
 *
 *       for (long i = 0; text[i] != '\0'; i++) { ... text[i] ... }
 *
 *   Same thing, two spellings. We use the pointer spelling because it
 *   is what real C code looks like — but whenever it confuses you,
 *   translate it to the text[i] version in your head.
 */

#include "textstats.h"  /* our own menu: TextStats + function declarations */

#include <ctype.h>       /* isspace(), toupper(), tolower()               */
#include <stddef.h>      /* NULL                                            */


/* ------------------------------------------------------------------ */
/* textstats_analyze                                                  */
/* ------------------------------------------------------------------ */
TextStats textstats_analyze(const char *text)
{
    /* Start with every counter at zero. If anything goes wrong below
     * we can return this safely. */
    TextStats stats = {0, 0, 0, 0};

    /* Defensive check: a NULL pointer points at nothing. Touching it
     * would crash the program (a "segfault"), so bail out early. */
    if (text == NULL) {
        return stats;
    }

    int in_word = 0;        /* 1 while we are inside a word, 0 between words  */
    long word_length = 0;   /* length of the word we are currently inside     */

    /* Walk the string one character at a time until the terminator. */
    for (const char *p = text; *p != '\0'; p++) {
        stats.chars++;

        if (*p == '\n') {
            stats.lines++;
        }

        /*
         * Is this character whitespace (space, tab, newline, ...)?
         *
         * TRICKY DETAIL worth learning: the <ctype.h> functions want an
         * `unsigned char`, but plain `char` can be negative for bytes
         * >= 128. Passing a negative value is officially "undefined
         * behaviour". Hence the (unsigned char) cast — you will see it
         * in all careful C code.
         */
        if (isspace((unsigned char)*p)) {
            /* Whitespace: any word we were in has ended. */
            in_word = 0;
            word_length = 0;
        } else {
            if (!in_word) {
                /* First character of a brand-new word. */
                in_word = 1;
                stats.words++;
                word_length = 0;
            }
            word_length++;
            if (word_length > stats.longest_word) {
                stats.longest_word = word_length;
            }
        }
    }

    /*
     * Line-count fix-up: "a\nb" contains only one '\n' but is clearly
     * two lines, because the text after the newline is a (partial)
     * final line. So: if the text is non-empty and does NOT end with
     * '\n', add that last partial line.
     *
     * text[stats.chars - 1] is the last real character of the string.
     */
    if (stats.chars > 0 && text[stats.chars - 1] != '\n') {
        stats.lines++;
    }

    return stats;
}


/* ------------------------------------------------------------------ */
/* textstats_count_char                                               */
/* ------------------------------------------------------------------ */
long textstats_count_char(const char *text, char target)
{
    if (text == NULL) {
        return 0;
    }

    long count = 0;
    for (const char *p = text; *p != '\0'; p++) {
        if (*p == target) {
            count++;
        }
    }
    return count;
}


/* ------------------------------------------------------------------ */
/* textstats_title_case                                               */
/*                                                                    */
/* This function WRITES through its pointer (`*p = ...`), changing    */
/* the caller's buffer in place. That is why its parameter is         */
/* `char *text` (writable) while analyze takes `const char *text`     */
/* (read-only). `const` is how C spells "I promise not to touch".     */
/* ------------------------------------------------------------------ */
void textstats_title_case(char *text)
{
    if (text == NULL) {
        return;
    }

    int in_word = 0;

    for (char *p = text; *p != '\0'; p++) {
        unsigned char c = (unsigned char)*p;  /* see cast note above */

        if (isspace(c)) {
            in_word = 0;                     /* between words      */
        } else if (!in_word) {
            *p = (char)toupper(c);           /* first char of word */
            in_word = 1;
        } else {
            *p = (char)tolower(c);           /* rest of the word   */
        }
    }
}


/* ------------------------------------------------------------------ */
/* textstats_version                                                  */
/* ------------------------------------------------------------------ */
const char *textstats_version(void)
{
    return "1.0.0";
}
