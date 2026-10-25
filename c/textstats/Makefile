# Makefile — build instructions for the textstats project.
# =========================================================
#
# WHAT IS MAKE?
#   Instead of typing long gcc commands by hand, you describe
#   "targets" (things to build) and the commands that build them.
#   `make` figures out what is out of date and only rebuilds that.
#
#   make              build everything (CLI, shared library, tests)
#   make test         build + run the C unit tests
#   make demo         build + show the CLI on sample input
#   make asan         build + run tests under AddressSanitizer
#                     (catches memory bugs — your best friend in Week 4)
#   make plugin       copy libtextstats.so into the Nexus plugin folder
#                     so Python can load it (or just `make` — the plugin
#                     also finds the .so right here in this folder)
#   make clean        delete everything that was built
#
# IMPORTANT MAKE QUIRK: recipe lines must start with a TAB character,
# not spaces. If make says "missing separator", that's why.

# The C compiler. gcc is standard on Linux; on macOS `gcc` is actually
# clang in disguise, which is fine — the flags below work for both.
CC = gcc

# Compiler flags — learn these, you'll use them on every C project:
#   -std=c11    use the C11 version of the language
#   -Wall       turn on (almost) all warnings
#   -Wextra     even more warnings
#   -Wpedantic  warn about non-standard tricks
#   -g          include debug info (so gdb/asan can show line numbers)
# Warnings are FREE LESSONS: treat every warning as a bug until you
# understand why it is not. Aim for a build with zero warnings.
CFLAGS = -std=c11 -Wall -Wextra -Wpedantic -g

# Where the Nexus plugin wrapper lives (relative to this folder).
PLUGIN_DIR = ../../plugins/c_text_tools

# `all` is the default target: a plain `make` builds these three.
all: textstats libtextstats.so test_textstats

# The command-line program: links main.c with the library code.
# "$@" means "the target name" (textstats). Make fills it in for you.
textstats: main.c textstats.c textstats.h
	$(CC) $(CFLAGS) -o $@ main.c textstats.c

# The shared library (.so) that Python loads through ctypes.
#   -fPIC     "position-independent code" — required for shared libs
#   -shared   build a .so instead of an executable program
# Note there is no main.c here: a library has no main(), it is a
# toolbox other programs borrow from.
libtextstats.so: textstats.c textstats.h
	$(CC) $(CFLAGS) -fPIC -shared -o $@ textstats.c

# The test program: test code + library code (again no main.c —
# test_textstats.c has its own main()).
test_textstats: test_textstats.c textstats.c textstats.h
	$(CC) $(CFLAGS) -o $@ test_textstats.c textstats.c

# Build the tests, then run them.
test: test_textstats
	./test_textstats

# Same tests, but compiled with AddressSanitizer + UndefinedBehavior-
# Sanitizer: they abort loudly the moment your code reads/writes
# memory it shouldn't, with file:line of the crime scene.
asan: textstats.c test_textstats.c textstats.h
	$(CC) $(CFLAGS) -fsanitize=address,undefined -o test_textstats_asan test_textstats.c textstats.c
	./test_textstats_asan

demo: textstats
	@echo "--- stats from stdin ---"
	@echo "hello Nexus world" | ./textstats
	@echo "--- stats for examples/sample.txt ---"
	./textstats examples/sample.txt
	@echo "--- title case ---"
	./textstats --title examples/sample.txt

# Copy the shared library next to the Python plugin. (The plugin can
# also load it straight from this folder; copying is what you'd do
# when "installing" for real.)
plugin: libtextstats.so
	cp libtextstats.so $(PLUGIN_DIR)/libtextstats.so
	@echo "copied libtextstats.so -> $(PLUGIN_DIR)/"
	@echo "Now from the repo root:  PYTHONPATH=src pytest tests/unit/test_c_text_tools_plugin.py -v"

clean:
	rm -f textstats test_textstats test_textstats_asan libtextstats.so *.o

# These targets are commands, not files — tell make so a file named
# e.g. "test" in this folder doesn't confuse it.
.PHONY: all test asan demo plugin clean
