#!/usr/bin/env python3
import argparse
import glob
import json
import logging
import os
import shutil
import tarfile
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


def setup_logging():
    logger = logging.getLogger("backup")
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)
    return logger


def parse_args():
    parser = argparse.ArgumentParser(description="File backup and restore utility")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backup", action="store_true", help="Run in backup mode")
    mode.add_argument("--restore", action="store_true", help="Run in restore mode")
    parser.add_argument("--config", help="Path to backup config file (--backup mode)")
    parser.add_argument("--destination", help="Backup destination root (--backup mode)")
    parser.add_argument("--suffix", default=None, help="Suffix for backup directory name (--backup mode)")
    parser.add_argument("--backup-dir", help="Path to backup directory to restore from (--restore mode)")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_config(path):
    with open(path) as f:
        config = json.load(f)
    valid_formats = {None, "gztar", "zip"}
    for entry in config["backup"]:
        if entry["format"] not in valid_formats:
            raise ValueError(
                f"{entry['path']!r} has invalid format {entry['format']!r}; "
                f"must be one of {valid_formats}"
            )
    return config


def expand_paths(pattern):
    expanded = os.path.expanduser(pattern)
    matches = glob.glob(expanded)
    if not matches:
        raise FileNotFoundError(
            f"No files matched pattern {pattern!r} (expanded: {expanded!r})"
        )
    return [Path(m) for m in matches]


def dir_size(path, exclude_hidden):
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        if exclude_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            filenames = [f for f in filenames if not f.startswith(".")]
        for filename in filenames:
            fp = os.path.join(dirpath, filename)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def copy_item(src, dest_dir, exclude_hidden, dry_run, logger):
    entry = {
        "artifact": src.name,
        "format": None,
        "type": "file" if src.is_file() else "dir",
        "restore_to": str(src.parent),
    }
    if dry_run:
        logger.info(f"[dry-run] would copy {src} → {dest_dir / src.name}")
        return entry
    if src.is_file():
        shutil.copy2(src, dest_dir / src.name)
        logger.info(f"Copied file {src} → {dest_dir / src.name}")
    elif src.is_dir():
        ignore = shutil.ignore_patterns(".*") if exclude_hidden else None
        shutil.copytree(src, dest_dir / src.name, ignore=ignore)
        logger.info(f"Copied directory {src} → {dest_dir / src.name}")
    return entry


def _archive_tar(src, output_dir, exclude_hidden, logger):
    archive_name = src.name + ".tar.gz"
    output_path = Path(output_dir) / archive_name

    def _filter(tarinfo):
        if exclude_hidden and os.path.basename(tarinfo.name).startswith("."):
            return None
        return tarinfo

    with tarfile.open(output_path, "w:gz") as tf:
        tf.add(src, arcname=src.name, filter=_filter)

    logger.info(f"Created tar archive {output_path}")
    return output_path


def _archive_zip(src, output_dir, exclude_hidden, logger):
    archive_name = src.name + ".zip"
    output_path = Path(output_dir) / archive_name

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if src.is_file():
            if not (exclude_hidden and src.name.startswith(".")):
                zf.write(src, src.name)
        else:
            for dirpath, dirnames, filenames in os.walk(src):
                if exclude_hidden:
                    dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                    filenames = [f for f in filenames if not f.startswith(".")]
                for filename in filenames:
                    full_path = Path(dirpath) / filename
                    arcname = full_path.relative_to(src.parent)
                    zf.write(full_path, arcname)

    logger.info(f"Created zip archive {output_path}")
    return output_path


def make_archive_file(src, dest_dir, fmt, exclude_hidden, dry_run, logger):
    ext = ".tar.gz" if fmt == "gztar" else ".zip"
    entry = {
        "artifact": src.name + ext,
        "format": fmt,
        "type": "file" if src.is_file() else "dir",
        "restore_to": str(src.parent),
    }
    if dry_run:
        logger.info(f"[dry-run] would archive {src} → {dest_dir / (src.name + ext)}")
        return entry
    with tempfile.TemporaryDirectory() as tmp:
        if fmt == "gztar":
            archive = _archive_tar(src, tmp, exclude_hidden, logger)
        else:
            archive = _archive_zip(src, tmp, exclude_hidden, logger)
        dest = shutil.move(str(archive), str(dest_dir))
        logger.info(f"Moved archive to {dest}")
    return entry


def archive_large_dir(src, dest_dir, fmt, exclude_hidden, dry_run, logger, size_limit):
    logger.info(f"{src} exceeds size limit; archiving children individually")
    entries = []
    for child in sorted(src.iterdir()):
        if exclude_hidden and child.name.startswith("."):
            continue
        child_size = dir_size(child, exclude_hidden) if child.is_dir() else child.stat().st_size
        if child_size <= size_limit:
            entries.append(make_archive_file(child, dest_dir, fmt, exclude_hidden, dry_run, logger))
        elif child.is_dir():
            entries.extend(archive_large_dir(child, dest_dir, fmt, exclude_hidden, dry_run, logger, size_limit))
        else:
            logger.warning(
                f"{child} is a single file exceeding {size_limit} bytes; archiving as-is"
            )
            entries.append(make_archive_file(child, dest_dir, fmt, exclude_hidden, dry_run, logger))
    return entries


def backup_path(src, dest_dir, fmt, exclude_hidden, dry_run, logger, size_limit=1_073_741_824):
    if fmt is None:
        return [copy_item(src, dest_dir, exclude_hidden, dry_run, logger)]
    elif src.is_file():
        return [make_archive_file(src, dest_dir, fmt, exclude_hidden, dry_run, logger)]
    else:
        size = dir_size(src, exclude_hidden)
        if size <= size_limit:
            return [make_archive_file(src, dest_dir, fmt, exclude_hidden, dry_run, logger)]
        else:
            return archive_large_dir(src, dest_dir, fmt, exclude_hidden, dry_run, logger, size_limit)


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


def run_backup(args, logger):
    if not args.config:
        raise SystemExit("--config is required with --backup")
    if not args.destination:
        raise SystemExit("--destination is required with --backup")

    config = load_config(Path(args.config))
    options = config.get("options", {})
    dry_run = args.dry_run or options.get("dry_run", False)
    exclude_hidden = options.get("exclude_hidden", False)
    suffix = args.suffix or options.get("suffix") or datetime.now().isoformat().replace(":", "-")

    dest_dir = Path(args.destination + "_" + suffix).resolve()
    logger.info(f"Destination: {dest_dir}")
    logger.info(f"Dry run: {dry_run}")

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    manifest_items = []
    for entry in config["backup"]:
        fmt = entry["format"]
        try:
            paths = expand_paths(entry["path"])
        except FileNotFoundError as e:
            logger.error(str(e))
            continue
        for src in paths:
            logger.info(f"Backing up {src}")
            manifest_items.extend(backup_path(src, dest_dir, fmt, exclude_hidden, dry_run, logger))

    if not dry_run:
        manifest = {
            "dest_dir": str(dest_dir),
            "created": datetime.now().isoformat(),
            "items": manifest_items,
        }
        manifest_path = dest_dir / "restore.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        logger.info(f"Wrote manifest to {manifest_path}")


def run_restore(args, logger):
    if not args.backup_dir:
        raise SystemExit("--backup-dir is required with --restore")

    backup_dir = Path(args.backup_dir)
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


def main():
    logger = setup_logging()
    args = parse_args()
    if args.backup:
        run_backup(args, logger)
    else:
        run_restore(args, logger)


if __name__ == "__main__":
    main()
