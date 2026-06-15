#!/usr/bin/env python3
import argparse
import json
import logging
import shutil
import tarfile
import zipfile
from pathlib import Path


def setup_logging():
    logger = logging.getLogger("restore")
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)
    return logger


def parse_args():
    parser = argparse.ArgumentParser(description="Restore files from a backup")
    parser.add_argument("--backup", required=True, help="Path to the backup directory")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def restore_item(artifact_path, fmt, item_type, restore_to, dry_run, logger):
    restore_to = Path(restore_to)
    if dry_run:
        logger.info(f"[dry-run] would restore {artifact_path} → {restore_to}")
        return
    restore_to.mkdir(parents=True, exist_ok=True)
    if fmt is None:
        if item_type == "file":
            shutil.copy2(artifact_path, restore_to / artifact_path.name)
            logger.info(f"Copied {artifact_path} → {restore_to / artifact_path.name}")
        else:
            shutil.copytree(artifact_path, restore_to / artifact_path.name)
            logger.info(f"Copied directory {artifact_path} → {restore_to / artifact_path.name}")
    elif fmt == "gztar":
        with tarfile.open(artifact_path) as tf:
            tf.extractall(restore_to)
        logger.info(f"Extracted {artifact_path} → {restore_to}")
    elif fmt == "zip":
        with zipfile.ZipFile(artifact_path) as zf:
            zf.extractall(restore_to)
        logger.info(f"Extracted {artifact_path} → {restore_to}")


def main():
    logger = setup_logging()
    args = parse_args()
    backup_dir = Path(args.backup)
    manifest_path = backup_dir / "restore.json"

    with open(manifest_path) as f:
        manifest = json.load(f)

    for item in manifest["items"]:
        artifact_path = backup_dir / item["artifact"]
        if not artifact_path.exists():
            logger.error(f"Artifact not found: {artifact_path}")
            raise FileNotFoundError(artifact_path)
        restore_item(
            artifact_path=artifact_path,
            fmt=item["format"],
            item_type=item["type"],
            restore_to=item["restore_to"],
            dry_run=args.dry_run,
            logger=logger,
        )


if __name__ == "__main__":
    main()
