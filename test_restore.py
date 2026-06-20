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

    def test_target_reroots_original_tree_under_target(self):
        (self.backup_dir / "file.txt").write_text("hello")
        original = self.root / "original_location"
        target = self.root / "elsewhere"
        self._write_manifest([{
            "artifact": "file.txt",
            "format": None,
            "type": "file",
            "restore_to": str(original),
        }])
        with patch("sys.argv", ["backup_util.py", "--restore", "--backup-dir",
                                str(self.backup_dir), "--target", str(target)]):
            backup.main()
        # The full original path is recreated under target (anchor stripped).
        rerooted = target / original.relative_to(original.anchor)
        self.assertTrue((rerooted / "file.txt").exists())
        self.assertFalse(original.exists())

    def test_target_keeps_same_named_items_distinct(self):
        # Two items named "notes.txt" from different parents must not collide.
        (self.backup_dir / "a.txt").write_text("from a")
        (self.backup_dir / "b.txt").write_text("from b")
        parent_a = self.root / "projects" / "a"
        parent_b = self.root / "projects" / "b"
        target = self.root / "elsewhere"
        self._write_manifest([
            {"artifact": "a.txt", "format": None, "type": "file", "restore_to": str(parent_a)},
            {"artifact": "b.txt", "format": None, "type": "file", "restore_to": str(parent_b)},
        ])
        with patch("sys.argv", ["backup_util.py", "--restore", "--backup-dir",
                                str(self.backup_dir), "--target", str(target)]):
            backup.main()
        a = target / parent_a.relative_to(parent_a.anchor) / "a.txt"
        b = target / parent_b.relative_to(parent_b.anchor) / "b.txt"
        self.assertEqual(a.read_text(), "from a")
        self.assertEqual(b.read_text(), "from b")

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
