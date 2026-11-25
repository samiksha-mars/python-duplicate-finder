#!/usr/bin/env python3
"""Find files with identical contents."""

import hashlib
import os
from collections import defaultdict
from pathlib import Path

CHUNK_SIZE = 1024 * 1024


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


def file_hash(path, chunk_size=CHUNK_SIZE):
    """Return the SHA-256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


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
        by_hash = defaultdict(list)
        for path in paths:
            try:
                by_hash[file_hash(path)].append(path)
            except OSError as error:
                if on_error:
                    on_error(path, error)
        for same in by_hash.values():
            if len(same) > 1:
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
