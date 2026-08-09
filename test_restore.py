#!/usr/bin/env python3
import json
import logging
import os
import stat
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backup_util as backup

logger = logging.getLogger("test")
logger.addHandler(logging.NullHandler())


class TestRestoreItem(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.backup_dir = self.root / "backup"
        self.backup_dir.mkdir()
        self.restore_to = self.root / "restored"

    def tearDown(self):
        self.tmp.cleanup()

    def test_restore_file(self):
        artifact = self.backup_dir / "file.txt"
        artifact.write_text("hello")
        backup.restore_item(artifact, fmt=None, item_type="file",
                            restore_to=self.restore_to, dry_run=False, logger=logger)
        self.assertTrue((self.restore_to / "file.txt").exists())
        self.assertEqual((self.restore_to / "file.txt").read_text(), "hello")

    def test_restore_directory(self):
        artifact_dir = self.backup_dir / "mydir"
        artifact_dir.mkdir()
        (artifact_dir / "file.txt").write_text("world")
        backup.restore_item(artifact_dir, fmt=None, item_type="dir",
                            restore_to=self.restore_to, dry_run=False, logger=logger)
        self.assertTrue((self.restore_to / "mydir" / "file.txt").exists())

    def test_restore_tar(self):
        src_dir = self.root / "src"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("compressed")
        archive = self.backup_dir / "src.tar.gz"
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(src_dir, arcname="src")
        backup.restore_item(archive, fmt="gztar", item_type="dir",
                            restore_to=self.restore_to, dry_run=False, logger=logger)
        self.assertTrue((self.restore_to / "src" / "file.txt").exists())
        self.assertEqual((self.restore_to / "src" / "file.txt").read_text(), "compressed")

    def test_dry_run_writes_nothing(self):
        artifact = self.backup_dir / "file.txt"
        artifact.write_text("hello")
        backup.restore_item(artifact, fmt=None, item_type="file",
                            restore_to=self.restore_to, dry_run=True, logger=logger)
        self.assertFalse(self.restore_to.exists())


class TestRestoreFidelity(unittest.TestCase):
    """Round-trip (backup then restore) preserves symlinks and permissions."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.backup_dir = self.root / "backup"
        self.backup_dir.mkdir()
        self.restore_to = self.root / "restored"
        self.src = self.root / "src"
        self.src.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_null_copy_preserves_symlink(self):
        (self.src / "real.txt").write_text("data")
        os.symlink("real.txt", self.src / "link.txt")
        backup.backup_path(self.src, self.backup_dir, fmt=None,
                           exclude_hidden=False, dry_run=False, logger=logger)
        backup.restore_item(self.backup_dir / "src", fmt=None, item_type="dir",
                            restore_to=self.restore_to, dry_run=False, logger=logger)
        self.assertTrue((self.restore_to / "src" / "link.txt").is_symlink())

    def test_gztar_preserves_permissions(self):
        script = self.src / "run.sh"
        script.write_text("#!/bin/sh\n")
        os.chmod(script, 0o751)
        backup.backup_path(self.src, self.backup_dir, fmt="gztar",
                           exclude_hidden=False, dry_run=False, logger=logger)
        backup.restore_item(self.backup_dir / "src.tar.gz", fmt="gztar", item_type="dir",
                            restore_to=self.restore_to, dry_run=False, logger=logger)
        restored = self.restore_to / "src" / "run.sh"
        self.assertEqual(stat.S_IMODE(restored.stat().st_mode), 0o751)

    def test_gztar_preserves_symlink(self):
        (self.src / "real.txt").write_text("data")
        os.symlink("real.txt", self.src / "link.txt")
        backup.backup_path(self.src, self.backup_dir, fmt="gztar",
                           exclude_hidden=False, dry_run=False, logger=logger)
        backup.restore_item(self.backup_dir / "src.tar.gz", fmt="gztar", item_type="dir",
                            restore_to=self.restore_to, dry_run=False, logger=logger)
        self.assertTrue((self.restore_to / "src" / "link.txt").is_symlink())


class TestRestoreMain(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.backup_dir = self.root / "backup"
        self.backup_dir.mkdir()
        self.restore_to = self.root / "restored"

    def tearDown(self):
        self.tmp.cleanup()

    def _write_manifest(self, items):
        manifest = {
            "dest_dir": str(self.backup_dir),
            "created": "2026-01-01T00:00:00",
            "items": items,
        }
        (self.backup_dir / "restore.json").write_text(json.dumps(manifest))

    def test_restores_all_items(self):
        (self.backup_dir / "file.txt").write_text("hello")
        self._write_manifest([{
            "artifact": "file.txt",
            "format": None,
            "type": "file",
            "restore_to": str(self.restore_to),
        }])
        with patch("sys.argv", ["backup_util.py", "--restore", "--backup-dir", str(self.backup_dir)]):
            backup.main()
        self.assertTrue((self.restore_to / "file.txt").exists())

    def test_target_restores_directly_under_target(self):
        (self.backup_dir / "file.txt").write_text("hello")
        original = self.root / "original_location"
        target = self.root / "elsewhere"
        self._write_manifest([{
            "artifact": "file.txt",
            "format": None,
            "type": "file",
            "restore_to": str(original),
            "restore_root": str(original),
        }])
        with patch("sys.argv", ["backup_util.py", "--restore", "--backup-dir",
                                str(self.backup_dir), "--target", str(target)]):
            backup.main()
        # The original parent path is discarded; the item lands directly under target.
        self.assertTrue((target / "file.txt").exists())
        self.assertFalse(original.exists())

    def test_target_places_each_item_directly_under_target(self):
        (self.backup_dir / "a.txt").write_text("from a")
        (self.backup_dir / "b.txt").write_text("from b")
        parent_a = self.root / "projects" / "a"
        parent_b = self.root / "projects" / "b"
        target = self.root / "elsewhere"
        self._write_manifest([
            {"artifact": "a.txt", "format": None, "type": "file",
             "restore_to": str(parent_a), "restore_root": str(parent_a)},
            {"artifact": "b.txt", "format": None, "type": "file",
             "restore_to": str(parent_b), "restore_root": str(parent_b)},
        ])
        with patch("sys.argv", ["backup_util.py", "--restore", "--backup-dir",
                                str(self.backup_dir), "--target", str(target)]):
            backup.main()
        self.assertEqual((target / "a.txt").read_text(), "from a")
        self.assertEqual((target / "b.txt").read_text(), "from b")

    def test_target_preserves_relative_subtree_for_split_items(self):
        # An item that was split off deep inside a large backed-up directory
        # (restore_root is the top-level entry's parent, restore_to is the
        # item's true, deeper original parent) should keep that intermediate
        # structure under --target rather than landing flat.
        (self.backup_dir / "deep.txt").write_text("nested")
        top_level_parent = self.root / "home" / "user1"
        deep_original_parent = top_level_parent / "Documents" / "subdirA" / "nested"
        target = self.root / "elsewhere"
        self._write_manifest([{
            "artifact": "deep.txt",
            "format": None,
            "type": "file",
            "restore_to": str(deep_original_parent),
            "restore_root": str(top_level_parent),
        }])
        with patch("sys.argv", ["backup_util.py", "--restore", "--backup-dir",
                                str(self.backup_dir), "--target", str(target)]):
            backup.main()
        self.assertEqual(
            (target / "Documents" / "subdirA" / "nested" / "deep.txt").read_text(), "nested"
        )

    def test_missing_artifact_raises(self):
        self._write_manifest([{
            "artifact": "missing.txt",
            "format": None,
            "type": "file",
            "restore_to": str(self.restore_to),
        }])
        with patch("sys.argv", ["backup_util.py", "--restore", "--backup-dir", str(self.backup_dir)]):
            with self.assertRaises(FileNotFoundError):
                backup.main()


if __name__ == "__main__":
    unittest.main()
