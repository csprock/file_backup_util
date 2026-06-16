#!/usr/bin/env python3
import json
import logging
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import backup

logger = logging.getLogger("test")
logger.addHandler(logging.NullHandler())


class TestLoadConfig(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_config(self, data):
        path = self.root / "config.json"
        path.write_text(json.dumps(data))
        return path

    def test_valid_formats_load(self):
        path = self._write_config({
            "backup": [
                {"path": "/a", "format": "gztar"},
                {"path": "/b", "format": "zip"},
                {"path": "/c", "format": None},
            ],
            "options": {}
        })
        config = backup.load_config(path)
        self.assertEqual(len(config["backup"]), 3)

    def test_invalid_format_raises(self):
        path = self._write_config({
            "backup": [{"path": "/a", "format": "bzip2"}],
            "options": {}
        })
        with self.assertRaises(ValueError):
            backup.load_config(path)

    def test_null_format_accepted(self):
        path = self._write_config({
            "backup": [{"path": "/a", "format": None}],
            "options": {}
        })
        config = backup.load_config(path)
        self.assertIsNone(config["backup"][0]["format"])


class TestExpandPaths(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_simple_path_returns_one(self):
        f = self.root / "file.txt"
        f.write_text("x")
        result = backup.expand_paths(str(f))
        self.assertEqual(result, [f])

    def test_glob_returns_multiple(self):
        (self.root / "a.txt").write_text("x")
        (self.root / "b.txt").write_text("x")
        result = backup.expand_paths(str(self.root / "*.txt"))
        self.assertEqual(len(result), 2)

    def test_no_match_raises(self):
        with self.assertRaises(FileNotFoundError):
            backup.expand_paths(str(self.root / "nonexistent_*.xyz"))


class TestDirSize(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name) / "src"
        self.src.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_returns_total_size(self):
        (self.src / "a.txt").write_bytes(b"x" * 10)
        (self.src / "b.txt").write_bytes(b"x" * 20)
        self.assertEqual(backup.dir_size(self.src, exclude_hidden=False), 30)

    def test_exclude_hidden_skips_dotfiles(self):
        (self.src / "visible.txt").write_bytes(b"x" * 10)
        (self.src / ".hidden").write_bytes(b"x" * 20)
        self.assertEqual(backup.dir_size(self.src, exclude_hidden=True), 10)

    def test_exclude_hidden_skips_dotdirs(self):
        dotdir = self.src / ".hiddendir"
        dotdir.mkdir()
        (dotdir / "file.txt").write_bytes(b"x" * 15)
        (self.src / "visible.txt").write_bytes(b"x" * 5)
        self.assertEqual(backup.dir_size(self.src, exclude_hidden=True), 5)

    def test_include_hidden_counts_dotfiles(self):
        (self.src / "visible.txt").write_bytes(b"x" * 10)
        (self.src / ".hidden").write_bytes(b"x" * 20)
        self.assertEqual(backup.dir_size(self.src, exclude_hidden=False), 30)


class TestCopyItem(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src_dir = self.root / "src"
        self.dest_dir = self.root / "dest"
        self.src_dir.mkdir()
        self.dest_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_copy_file_lands_in_dest(self):
        f = self.src_dir / "file.txt"
        f.write_text("hello")
        entry = backup.copy_item(f, self.dest_dir, exclude_hidden=False, dry_run=False, logger=logger)
        self.assertTrue((self.dest_dir / "file.txt").exists())

    def test_copy_file_entry(self):
        f = self.src_dir / "file.txt"
        f.write_text("hello")
        entry = backup.copy_item(f, self.dest_dir, exclude_hidden=False, dry_run=False, logger=logger)
        self.assertEqual(entry["artifact"], "file.txt")
        self.assertIsNone(entry["format"])
        self.assertEqual(entry["type"], "file")
        self.assertEqual(entry["restore_to"], str(self.src_dir))

    def test_copy_directory_lands_in_dest(self):
        d = self.src_dir / "mydir"
        d.mkdir()
        (d / "file.txt").write_text("hi")
        entry = backup.copy_item(d, self.dest_dir, exclude_hidden=False, dry_run=False, logger=logger)
        self.assertTrue((self.dest_dir / "mydir" / "file.txt").exists())
        self.assertEqual(entry["type"], "dir")
        self.assertEqual(entry["restore_to"], str(self.src_dir))

    def test_exclude_hidden_omits_dotfiles(self):
        d = self.src_dir / "mydir"
        d.mkdir()
        (d / "visible.txt").write_text("hi")
        (d / ".hidden").write_text("secret")
        backup.copy_item(d, self.dest_dir, exclude_hidden=True, dry_run=False, logger=logger)
        self.assertTrue((self.dest_dir / "mydir" / "visible.txt").exists())
        self.assertFalse((self.dest_dir / "mydir" / ".hidden").exists())

    def test_dry_run_writes_nothing(self):
        f = self.src_dir / "file.txt"
        f.write_text("hello")
        backup.copy_item(f, self.dest_dir, exclude_hidden=False, dry_run=True, logger=logger)
        self.assertFalse((self.dest_dir / "file.txt").exists())

    def test_dry_run_returns_entry(self):
        f = self.src_dir / "file.txt"
        f.write_text("hello")
        entry = backup.copy_item(f, self.dest_dir, exclude_hidden=False, dry_run=True, logger=logger)
        self.assertEqual(entry["artifact"], "file.txt")
        self.assertEqual(entry["type"], "file")


class TestArchiveTar(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root / "mydir"
        self.src.mkdir()
        self.out = self.root / "out"
        self.out.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_archive(self):
        (self.src / "file.txt").write_text("hello")
        result = backup._archive_tar(self.src, self.out, exclude_hidden=False, logger=logger)
        self.assertTrue(result.exists())
        self.assertEqual(result.name, "mydir.tar.gz")

    def test_archive_contains_files(self):
        (self.src / "file.txt").write_text("hello")
        result = backup._archive_tar(self.src, self.out, exclude_hidden=False, logger=logger)
        with tarfile.open(result) as tf:
            names = tf.getnames()
        self.assertIn("mydir/file.txt", names)

    def test_exclude_hidden(self):
        (self.src / "visible.txt").write_text("hi")
        (self.src / ".hidden").write_text("secret")
        result = backup._archive_tar(self.src, self.out, exclude_hidden=True, logger=logger)
        with tarfile.open(result) as tf:
            names = tf.getnames()
        self.assertIn("mydir/visible.txt", names)
        self.assertFalse(any(".hidden" in n for n in names))


class TestArchiveZip(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root / "mydir"
        self.src.mkdir()
        self.out = self.root / "out"
        self.out.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_archive(self):
        (self.src / "file.txt").write_text("hello")
        result = backup._archive_zip(self.src, self.out, exclude_hidden=False, logger=logger)
        self.assertTrue(result.exists())
        self.assertEqual(result.name, "mydir.zip")

    def test_archive_contains_files(self):
        (self.src / "file.txt").write_text("hello")
        result = backup._archive_zip(self.src, self.out, exclude_hidden=False, logger=logger)
        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
        self.assertIn("mydir/file.txt", names)

    def test_exclude_hidden(self):
        (self.src / "visible.txt").write_text("hi")
        (self.src / ".hidden").write_text("secret")
        result = backup._archive_zip(self.src, self.out, exclude_hidden=True, logger=logger)
        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
        self.assertIn("mydir/visible.txt", names)
        self.assertNotIn("mydir/.hidden", names)


class TestMakeArchiveFile(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root / "mydir"
        self.src.mkdir()
        (self.src / "file.txt").write_text("hello")
        self.dest = self.root / "dest"
        self.dest.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_archive_lands_in_dest_not_source(self):
        backup.make_archive_file(self.src, self.dest, "gztar", exclude_hidden=False, dry_run=False, logger=logger)
        self.assertTrue((self.dest / "mydir.tar.gz").exists())
        self.assertFalse((self.root / "mydir.tar.gz").exists())

    def test_returns_correct_entry(self):
        entry = backup.make_archive_file(self.src, self.dest, "gztar", exclude_hidden=False, dry_run=False, logger=logger)
        self.assertEqual(entry["artifact"], "mydir.tar.gz")
        self.assertEqual(entry["format"], "gztar")
        self.assertEqual(entry["type"], "dir")
        self.assertEqual(entry["restore_to"], str(self.root))

    def test_zip_format(self):
        backup.make_archive_file(self.src, self.dest, "zip", exclude_hidden=False, dry_run=False, logger=logger)
        self.assertTrue((self.dest / "mydir.zip").exists())

    def test_dry_run_writes_nothing(self):
        backup.make_archive_file(self.src, self.dest, "zip", exclude_hidden=False, dry_run=True, logger=logger)
        self.assertFalse(any(self.dest.iterdir()))

    def test_dry_run_returns_entry(self):
        entry = backup.make_archive_file(self.src, self.dest, "zip", exclude_hidden=False, dry_run=True, logger=logger)
        self.assertEqual(entry["artifact"], "mydir.zip")
        self.assertEqual(entry["type"], "dir")


class TestArchiveLargeDir(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root / "bigdir"
        self.src.mkdir()
        self.dest = self.root / "dest"
        self.dest.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_archives_each_child(self):
        (self.src / "child1.txt").write_bytes(b"x" * 5)
        (self.src / "child2.txt").write_bytes(b"x" * 5)
        entries = backup.archive_large_dir(
            self.src, self.dest, "gztar",
            exclude_hidden=False, dry_run=False,
            logger=logger, size_limit=100,
        )
        self.assertEqual(len(entries), 2)
        self.assertTrue((self.dest / "child1.txt.tar.gz").exists())
        self.assertTrue((self.dest / "child2.txt.tar.gz").exists())

    def test_restore_to_is_child_parent(self):
        (self.src / "child.txt").write_bytes(b"x" * 5)
        entries = backup.archive_large_dir(
            self.src, self.dest, "gztar",
            exclude_hidden=False, dry_run=False,
            logger=logger, size_limit=100,
        )
        self.assertEqual(entries[0]["restore_to"], str(self.src))

    def test_skips_hidden_children(self):
        (self.src / "visible.txt").write_bytes(b"x" * 5)
        (self.src / ".hidden").write_bytes(b"x" * 5)
        entries = backup.archive_large_dir(
            self.src, self.dest, "gztar",
            exclude_hidden=True, dry_run=False,
            logger=logger, size_limit=100,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["artifact"], "visible.txt.tar.gz")

    def test_recurses_into_oversized_subdir(self):
        subdir = self.src / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").write_bytes(b"x" * 5)
        # size_limit=1: subdir (5 bytes) > 1, recurse; file.txt (5 bytes) > 1
        # but it's a single file so archived as-is
        entries = backup.archive_large_dir(
            self.src, self.dest, "gztar",
            exclude_hidden=False, dry_run=False,
            logger=logger, size_limit=1,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["artifact"], "file.txt.tar.gz")
        self.assertEqual(entries[0]["restore_to"], str(subdir))


class TestBackupPath(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dest = self.root / "dest"
        self.dest.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_null_format_copies_file(self):
        f = self.root / "file.txt"
        f.write_text("hello")
        entries = backup.backup_path(f, self.dest, fmt=None, exclude_hidden=False, dry_run=False, logger=logger)
        self.assertTrue((self.dest / "file.txt").exists())
        self.assertEqual(entries[0]["type"], "file")

    def test_gztar_archives_directory(self):
        d = self.root / "mydir"
        d.mkdir()
        (d / "file.txt").write_text("hello")
        entries = backup.backup_path(d, self.dest, fmt="gztar", exclude_hidden=False, dry_run=False, logger=logger)
        self.assertTrue((self.dest / "mydir.tar.gz").exists())
        self.assertEqual(len(entries), 1)

    def test_oversized_dir_splits_into_children(self):
        d = self.root / "bigdir"
        d.mkdir()
        (d / "child1.txt").write_bytes(b"x" * 5)
        (d / "child2.txt").write_bytes(b"x" * 5)
        entries = backup.backup_path(
            d, self.dest, fmt="zip",
            exclude_hidden=False, dry_run=False,
            logger=logger, size_limit=1,
        )
        self.assertEqual(len(entries), 2)


class TestMain(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_config(self, data):
        path = self.root / "config.json"
        path.write_text(json.dumps(data))
        return path

    def test_creates_dest_and_manifest(self):
        src_file = self.root / "source.txt"
        src_file.write_text("hello")
        dest_base = str(self.root / "backup")
        config_path = self._write_config({
            "backup": [{"path": str(src_file), "format": None}],
            "options": {"dry_run": False, "exclude_hidden": False, "suffix": None},
        })
        with patch("sys.argv", ["backup.py", "--config", str(config_path),
                                "--destination", dest_base, "--suffix", "test"]):
            backup.main()
        dest_dir = Path(dest_base + "_test")
        self.assertTrue(dest_dir.exists())
        manifest_path = dest_dir / "restore.json"
        self.assertTrue(manifest_path.exists())
        with open(manifest_path) as f:
            manifest = json.load(f)
        self.assertEqual(len(manifest["items"]), 1)
        self.assertEqual(manifest["items"][0]["artifact"], "source.txt")

    def test_dry_run_skips_dest_and_manifest(self):
        src_file = self.root / "source.txt"
        src_file.write_text("hello")
        dest_base = str(self.root / "backup")
        config_path = self._write_config({
            "backup": [{"path": str(src_file), "format": None}],
            "options": {"dry_run": False, "exclude_hidden": False, "suffix": None},
        })
        with patch("sys.argv", ["backup.py", "--config", str(config_path),
                                "--destination", dest_base, "--suffix", "test",
                                "--dry-run"]):
            backup.main()
        dest_dir = Path(dest_base + "_test")
        self.assertFalse(dest_dir.exists())


if __name__ == "__main__":
    unittest.main()
