/*
 * main.c — the `textstats` command-line program.
 * ==============================================
 *
 * This file is a THIN shell around the library in textstats.c:
 * it only reads input, calls the library, and prints the result.
 * Keeping the "thinking" (library) separate from the "talking to the
 * terminal" (this file) is what lets the SAME library code also be
 * reused by the test program and by Python/Nexus later.
 *
 * Usage:
 *   ./textstats [file]            stats for a file (or stdin if omitted)
 *   ./textstats --title [file]    print the text converted to Title Case
 *   echo "hello world" | ./textstats
 *   ./textstats --help
 *   ./textstats --version
 */

#include <stdio.h>        /* FILE, fopen, fread, printf, perror, stdin  */
#include <string.h>       /* strcmp                                     */

#include "textstats.h"    /* TextStats, textstats_analyze, ...          */

/*
 * KNOWN LIMITATION (on purpose — it is EXERCISES.md E5):
 * input is read into a fixed 8192-byte buffer, so files bigger than
 * 8191 bytes are silently truncated. Fixing this properly needs
 * malloc()/realloc(), which is the Week 3 topic in ../ROADMAP.md.
 */
#define BUFFER_SIZE 8192

static void print_usage(const char *program_name)
{
    printf("textstats %s — count chars, words and lines\n\n",
           textstats_version());
    printf("Usage:\n");
    printf("  %s [file]           stats for [file], or stdin if no file\n", program_name);
    printf("  %s --title [file]   print the text in Title Case\n", program_name);
    printf("  %s --version        print version\n", program_name);
    printf("  %s --help           print this help\n", program_name);
    printf("\nExamples:\n");
    printf("  echo \"hello world\" | %s\n", program_name);
    printf("  %s examples/sample.txt\n", program_name);
}

int main(int argc, char *argv[])
{
    /*
     * argc = how many command-line words there are (including the
     * program name itself), argv = array of those words as strings.
     * argv[0] is always the program name, so real arguments start
     * at argv[1].
     */
    int title_mode = 0;
    const char *path = NULL;   /* NULL means "read from stdin" */

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            print_usage(argv[0]);
            return 0;
        } else if (strcmp(argv[i], "--version") == 0) {
            printf("textstats %s\n", textstats_version());
            return 0;
        } else if (strcmp(argv[i], "--title") == 0) {
            title_mode = 1;
        } else {
            path = argv[i];    /* anything else is treated as a filename */
        }
    }

    /* --- Open the input: a file, or stdin when no file was given. --- */
    FILE *input = stdin;
    if (path != NULL) {
        input = fopen(path, "r");
        if (input == NULL) {
            /* perror prints "path: <reason>" using the OS error. */
            perror(path);
            return 1;          /* non-zero exit code = "something failed" */
        }
    }

    /* --- Read up to BUFFER_SIZE - 1 bytes, then terminate the string. */
    char buffer[BUFFER_SIZE];
    size_t bytes_read = fread(buffer, 1, sizeof(buffer) - 1, input);
    buffer[bytes_read] = '\0';   /* fread does NOT add this for us! */

    if (path != NULL) {
        fclose(input);
    }

    /* --- Do the actual work by calling the library. --- */
    if (title_mode) {
        textstats_title_case(buffer);   /* rewrites buffer in place */
        fputs(buffer, stdout);
        if (bytes_read == 0 || buffer[bytes_read - 1] != '\n') {
            putchar('\n');
        }
        return 0;
    }

    TextStats stats = textstats_analyze(buffer);

    printf("chars:         %ld\n", stats.chars);
    printf("words:         %ld\n", stats.words);
    printf("lines:         %ld\n", stats.lines);
    printf("longest word:  %ld\n", stats.longest_word);

    return 0;   /* 0 = success, by universal C/Unix convention */
}
