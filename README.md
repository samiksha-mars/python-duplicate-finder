# Python Duplicate Finder

A command-line tool that finds duplicate files in one or more directories by comparing their contents.
Uses only the Python standard library.

## Features

- Groups files with identical content, regardless of name or location
- Fast: files are first grouped by size, and only same-size files are hashed (SHA-256, read in chunks)
- Skips empty files by default (`--include-empty` to include them)
- Optional minimum size filter (`--min-size 1024`)
- Ignores hidden files and directories unless `--hidden` is given
- Shows how much space the duplicates waste
- JSON output (`--json`) for scripting
