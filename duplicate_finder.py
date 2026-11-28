#!/usr/bin/env python3
"""Find files with identical contents."""

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

CHUNK_SIZE = 1024 * 1024
# Same-size files larger than this are first compared by a hash of their first
# HEAD_SIZE bytes, so files that differ early are never read in full.
HEAD_SIZE = 64 * 1024


def iter_files(roots, include_hidden=False):
    """Yield every regular file under the given roots (symlinks are skipped)."""
    for root in roots:
        root = Path(root)
        if root.is_file() and not root.is_symlink():
            yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if not include_hidden:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            dirnames.sort()
            for name in sorted(filenames):
                if not include_hidden and name.startswith("."):
                    continue
                path = Path(dirpath) / name
                if path.is_file() and not path.is_symlink():
                    yield path


def file_hash(path, chunk_size=CHUNK_SIZE, limit=None):
    """Return the SHA-256 hex digest of a file, read in chunks.

    With ``limit``, only the first ``limit`` bytes are hashed.
    """
    digest = hashlib.sha256()
    remaining = limit
    with open(path, "rb") as handle:
        while remaining is None or remaining > 0:
            chunk = handle.read(chunk_size if remaining is None else min(chunk_size, remaining))
            if not chunk:
                break
            digest.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
    return digest.hexdigest()


def _group_by_hash(paths, on_error, limit=None):
    """Split paths into lists with equal hashes, keeping only lists of two or more."""
    by_hash = defaultdict(list)
    for path in paths:
        try:
            by_hash[file_hash(path, limit=limit)].append(path)
        except OSError as error:
            if on_error:
                on_error(path, error)
    return [same for same in by_hash.values() if len(same) > 1]


def find_duplicates(roots, min_size=1, include_hidden=False, on_error=None):
    """Return a list of duplicate groups, each a sorted list of paths with identical content.

    Files smaller than ``min_size`` bytes are ignored (the default of 1 skips empty files).
    The same file reached through overlapping roots is only counted once.
    Groups are sorted by wasted space, largest first.
    """
    by_size = defaultdict(list)
    seen = set()
    for path in iter_files(roots, include_hidden):
        try:
            stat = path.stat()
        except OSError as error:
            if on_error:
                on_error(path, error)
            continue
        key = (stat.st_dev, stat.st_ino)
        if key in seen:
            continue
        seen.add(key)
        if stat.st_size >= min_size:
            by_size[stat.st_size].append(path)

    groups = []
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        # For small files the head hash would cover the whole file, so skip it.
        candidates = _group_by_hash(paths, on_error, limit=HEAD_SIZE) if size > HEAD_SIZE else [paths]
        for candidate in candidates:
            for same in _group_by_hash(candidate, on_error):
                groups.append((size, sorted(same)))

    groups.sort(key=lambda group: (-group[0] * (len(group[1]) - 1), str(group[1][0])))
    return [paths for _, paths in groups]


def wasted_bytes(groups):
    """Bytes that could be freed by keeping only one file from each group."""
    return sum(group[0].stat().st_size * (len(group) - 1) for group in groups)


def format_size(size):
    """Format a byte count for humans, e.g. 1536 -> '1.5 KiB'."""
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def build_parser():
    parser = argparse.ArgumentParser(description="Find files with identical contents.")
    parser.add_argument("paths", nargs="*", default=["."], help="directories or files to scan (default: .)")
    parser.add_argument("--min-size", type=int, default=1, metavar="BYTES",
                        help="ignore files smaller than this (default: 1)")
    parser.add_argument("--include-empty", action="store_true", help="also report empty files")
    parser.add_argument("--hidden", action="store_true", help="include hidden files and directories")
    parser.add_argument("--json", action="store_true", help="print groups as JSON")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.min_size < 0:
        print("error: --min-size must not be negative", file=sys.stderr)
        return 2
    missing = [p for p in args.paths if not Path(p).exists()]
    if missing:
        print(f"error: no such file or directory: {missing[0]}", file=sys.stderr)
        return 2

    min_size = 0 if args.include_empty else max(args.min_size, 1)

    def report(path, error):
        print(f"warning: skipping {path}: {error.strerror or error}", file=sys.stderr)

    groups = find_duplicates(args.paths, min_size=min_size, include_hidden=args.hidden, on_error=report)

    if args.json:
        print(json.dumps([[str(p) for p in group] for group in groups], indent=2))
        return 0

    if not groups:
        print("No duplicates found.")
        return 0
    for group in groups:
        print(f"{format_size(group[0].stat().st_size)} x {len(group)}")
        for path in group:
            print(f"  {path}")
        print()
    extra = sum(len(group) - 1 for group in groups)
    print(f"{len(groups)} group(s), {extra} redundant file(s), {format_size(wasted_bytes(groups))} wasted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
