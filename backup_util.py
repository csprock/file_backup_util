#!/usr/bin/env python3
import argparse
import glob
import json
import logging
import os
import shutil
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

__version__ = "0.1.0"


def setup_logging():
    logger = logging.getLogger("backup")
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)
    return logger


_CONFIG_HELP = """
config file format (JSON):
  {
    "backup": [
      {"path": "~/Documents",    "format": "gztar"},
      {"path": "~/Projects/*",   "format": "gztar"},
      {"path": "~/notes.txt",    "format": null}
    ],
    "options": {
      "dry_run":        false,
      "exclude_hidden": true,
      "suffix":         null
    }
  }

  path    : absolute or ~-relative path; glob wildcards supported (each match
            is backed up as a separate artifact)
  format  : "gztar" (.tar.gz) or null (copy without compression). gztar and
            null preserve symlinks and Unix permissions; gztar is recommended
            for directories.
  dry_run : log what would happen without writing any files
  exclude_hidden: skip dotfiles and dot-directories
  suffix  : appended to --destination to form the backup directory name;
            defaults to an ISO timestamp (e.g. 2026-06-16T10-30-00)
"""


def parse_args():
    parser = argparse.ArgumentParser(
        description="File backup and restore utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_CONFIG_HELP,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backup", action="store_true", help="Run in backup mode")
    mode.add_argument("--restore", action="store_true", help="Run in restore mode")
    parser.add_argument("--config", help="Path to backup config file (--backup mode)")
    parser.add_argument("--destination", help="Backup destination root (--backup mode)")
    parser.add_argument("--suffix", default=None, help="Suffix for backup directory name (--backup mode)")
    parser.add_argument("--backup-dir", help="Path to backup directory to restore from (--restore mode)")
    parser.add_argument(
        "--target",
        help="Restore everything under this directory, recreating each item's "
        "original path tree beneath it, instead of restoring to the original "
        "locations (--restore mode)",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_config(path):
    with open(path) as f:
        config = json.load(f)
    valid_formats = {None, "gztar"}
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
        shutil.copytree(src, dest_dir / src.name, ignore=ignore, symlinks=True)
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


def make_archive_file(src, dest_dir, fmt, exclude_hidden, dry_run, logger):
    ext = ".tar.gz"
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
        archive = _archive_tar(src, tmp, exclude_hidden, logger)
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
    # Top-level name the item will occupy under restore_to (the archive name
    # minus its .tar.gz suffix, or the file/dir name as-is for copies).
    final_name = artifact_path.name[: -len(".tar.gz")] if fmt == "gztar" else artifact_path.name
    if (restore_to / final_name).exists():
        logger.warning(f"{restore_to / final_name} already exists; overwriting")
    if fmt is None:
        if item_type == "file":
            shutil.copy2(artifact_path, restore_to / artifact_path.name)
            logger.info(f"Copied {artifact_path} → {restore_to / artifact_path.name}")
        else:
            # symlinks=True keeps symlinks as links; dirs_exist_ok lets a restore
            # overwrite/merge into an existing tree instead of failing.
            shutil.copytree(artifact_path, restore_to / artifact_path.name,
                            symlinks=True, dirs_exist_ok=True)
            logger.info(f"Copied directory {artifact_path} → {restore_to / artifact_path.name}")
    elif fmt == "gztar":
        with tarfile.open(artifact_path) as tf:
            tf.extractall(restore_to)
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

    # With --target, every item is restored under that directory with its
    # original path tree recreated beneath it (e.g. /home/u/Docs becomes
    # <target>/home/u/Docs), instead of restoring to its original location.
    target = Path(args.target).resolve() if args.target else None
    if target:
        logger.info(f"Rerooting all items under {target}")

    for item in manifest["items"]:
        artifact_path = backup_dir / item["artifact"]
        if not artifact_path.exists():
            logger.error(f"Artifact not found: {artifact_path}")
            raise FileNotFoundError(artifact_path)
        original = Path(item["restore_to"])
        if target:
            # Strip the leading "/" so the full original tree is recreated
            # beneath target rather than restoring from the filesystem root.
            parts = original.parts[1:] if original.anchor else original.parts
            restore_to = str(target.joinpath(*parts))
        else:
            restore_to = str(original)
        restore_item(
            artifact_path=artifact_path,
            fmt=item["format"],
            item_type=item["type"],
            restore_to=restore_to,
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
