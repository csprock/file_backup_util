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

    def test_restore_zip(self):
        src_dir = self.root / "src"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("zipped")
        archive = self.backup_dir / "src.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.write(src_dir / "file.txt", "src/file.txt")
        backup.restore_item(archive, fmt="zip", item_type="dir",
                            restore_to=self.restore_to, dry_run=False, logger=logger)
        self.assertTrue((self.restore_to / "src" / "file.txt").exists())
        self.assertEqual((self.restore_to / "src" / "file.txt").read_text(), "zipped")

    def test_dry_run_writes_nothing(self):
        artifact = self.backup_dir / "file.txt"
        artifact.write_text("hello")
        backup.restore_item(artifact, fmt=None, item_type="file",
                            restore_to=self.restore_to, dry_run=True, logger=logger)
        self.assertFalse(self.restore_to.exists())


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
