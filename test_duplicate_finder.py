import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from pathlib import Path
from unittest import mock

import duplicate_finder
from duplicate_finder import HEAD_SIZE, file_hash, find_duplicates, format_size, iter_files, main, wasted_bytes


def file_hash_of(data):
    return sha256(data).hexdigest()


class TempDirTestCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode() if isinstance(content, str) else content)
        return path


class FindDuplicatesTest(TempDirTestCase):

    def test_groups_identical_files(self):
        a = self.write("a.txt", "hello")
        b = self.write("sub/b.txt", "hello")
        self.write("c.txt", "world")  # same size, different content
        self.assertEqual(find_duplicates([self.root]), [sorted([a, b])])

    def test_no_duplicates(self):
        self.write("a.txt", "one")
        self.write("b.txt", "two!")
        self.assertEqual(find_duplicates([self.root]), [])

    def test_empty_files_skipped_by_default(self):
        self.write("e1", "")
        self.write("e2", "")
        self.assertEqual(find_duplicates([self.root]), [])
        self.assertEqual(len(find_duplicates([self.root], min_size=0)), 1)

    def test_min_size(self):
        self.write("a", "tiny")
        self.write("b", "tiny")
        self.assertEqual(find_duplicates([self.root], min_size=100), [])

    def test_hidden_files(self):
        self.write("a.txt", "same")
        self.write(".hidden/b.txt", "same")
        self.assertEqual(find_duplicates([self.root]), [])
        self.assertEqual(len(find_duplicates([self.root], include_hidden=True)), 1)

    def test_overlapping_roots_not_double_counted(self):
        self.write("sub/a.txt", "only one")
        self.assertEqual(find_duplicates([self.root, self.root / "sub"]), [])

    def test_largest_waste_first(self):
        self.write("s1", "x")
        self.write("s2", "x")
        self.write("l1", "x" * 100)
        self.write("l2", "x" * 100)
        groups = find_duplicates([self.root])
        self.assertEqual([g[0].name for g in groups], ["l1", "s1"])
        self.assertEqual(wasted_bytes(groups), 101)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks not supported")
    def test_symlinks_ignored(self):
        target = self.write("a.txt", "linked")
        try:
            os.symlink(target, self.root / "link.txt")
        except OSError:
            self.skipTest("cannot create symlinks")
        self.assertEqual(list(iter_files([self.root])), [target])


class HelpersTest(TempDirTestCase):

    def test_file_hash_limit(self):
        path = self.root / "f"
        path.write_bytes(b"abcdef")
        self.assertEqual(file_hash(path, chunk_size=4, limit=5), file_hash_of(b"abcde"))
        self.assertEqual(file_hash(path, limit=100), file_hash(path))

    def test_large_files_differing_only_at_end(self):
        head = b"x" * (HEAD_SIZE + 10)
        (self.root / "a").write_bytes(head + b"1")
        (self.root / "b").write_bytes(head + b"2")
        (self.root / "c").write_bytes(head + b"1")
        self.assertEqual(find_duplicates([self.root]), [[self.root / "a", self.root / "c"]])

    def test_large_files_differing_early_are_not_read_in_full(self):
        size = HEAD_SIZE * 3
        (self.root / "a").write_bytes(b"a" * size)
        (self.root / "b").write_bytes(b"b" * size)
        with mock.patch.object(duplicate_finder, "file_hash", wraps=file_hash) as spy:
            self.assertEqual(find_duplicates([self.root]), [])
        self.assertEqual({call.kwargs.get("limit") for call in spy.call_args_list}, {HEAD_SIZE})

    def test_file_hash_small_chunks(self):
        path = self.write("f", "abcdef" * 1000)
        self.assertEqual(file_hash(path), file_hash(path, chunk_size=7))

    def test_format_size(self):
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(1023), "1023 B")
        self.assertEqual(format_size(1536), "1.5 KiB")
        self.assertEqual(format_size(3 * 1024 ** 3), "3.0 GiB")


class MainTest(TempDirTestCase):

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_text_report(self):
        self.write("a", "dup")
        self.write("b", "dup")
        code, out, _ = self.run_main(str(self.root))
        self.assertEqual(code, 0)
        self.assertIn("1 group(s), 1 redundant file(s), 3 B wasted", out)

    def test_json_report(self):
        self.write("a", "dup")
        self.write("b", "dup")
        code, out, _ = self.run_main("--json", str(self.root))
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)[0]), 2)

    def test_nothing_found(self):
        code, out, _ = self.run_main(str(self.root))
        self.assertEqual(code, 0)
        self.assertIn("No duplicates found.", out)

    def test_missing_path(self):
        code, _, err = self.run_main(str(self.root / "nope"))
        self.assertEqual(code, 2)
        self.assertIn("no such file or directory", err)

    def test_negative_min_size(self):
        code, _, err = self.run_main("--min-size", "-1", str(self.root))
        self.assertEqual(code, 2)
        self.assertIn("--min-size", err)


if __name__ == "__main__":
    unittest.main()
