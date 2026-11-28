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

## Usage

```bash
# Scan the current directory
python3 duplicate_finder.py

# Scan several directories at once
python3 duplicate_finder.py ~/Pictures ~/Downloads

# Only files of at least 1 MiB, including hidden ones
python3 duplicate_finder.py ~/Documents --min-size 1048576 --hidden

# Machine-readable output
python3 duplicate_finder.py ~/Music --json
```

Example output:

```
2.4 MiB x 3
  /home/me/Downloads/photo (1).jpg
  /home/me/Downloads/photo.jpg
  /home/me/Pictures/holiday/photo.jpg

12.0 KiB x 2
  /home/me/Documents/notes-old.txt
  /home/me/Documents/notes.txt

2 group(s), 3 redundant file(s), 4.8 MiB wasted
```

The tool only reports duplicates; it never deletes or modifies files.

## How it works

1. Walk the given paths and group regular files by size (symlinks are skipped, and a file reached through overlapping paths is counted once).
2. Files with a unique size cannot have a duplicate, so they are dropped without being read.
3. Files larger than 64 KiB are first compared by a SHA-256 hash of their first 64 KiB. Most files that merely share a size differ early, so they are dropped after a small read.
4. The remaining files are hashed in full with SHA-256 in 1 MiB chunks, and files with equal hashes are reported together.

## Tests

```bash
python3 -m unittest
```
