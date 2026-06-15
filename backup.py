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
    parser = argparse.ArgumentParser(description="Back up files and directories")
    parser.add_argument("--config", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--suffix", default=None)
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
    if dry_run:
        logger.info(f"[dry-run] would copy {src} → {dest_dir / src.name}")
        return
    if src.is_file():
        shutil.copy2(src, dest_dir / src.name)
        logger.info(f"Copied file {src} → {dest_dir / src.name}")
    elif src.is_dir():
        ignore = shutil.ignore_patterns(".*") if exclude_hidden else None
        shutil.copytree(src, dest_dir / src.name, ignore=ignore)
        logger.info(f"Copied directory {src} → {dest_dir / src.name}")


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
    if dry_run:
        logger.info(f"[dry-run] would archive {src} → {dest_dir / (src.name + ext)}")
        return
    with tempfile.TemporaryDirectory() as tmp:
        if fmt == "gztar":
            archive = _archive_tar(src, tmp, exclude_hidden, logger)
        else:
            archive = _archive_zip(src, tmp, exclude_hidden, logger)
        dest = shutil.move(str(archive), str(dest_dir))
        logger.info(f"Moved archive to {dest}")


def archive_large_dir(src, dest_dir, fmt, exclude_hidden, dry_run, logger, size_limit):
    logger.info(f"{src} exceeds size limit; archiving children individually")
    for child in sorted(src.iterdir()):
        if exclude_hidden and child.name.startswith("."):
            continue
        child_size = dir_size(child, exclude_hidden) if child.is_dir() else child.stat().st_size
        if child_size <= size_limit:
            make_archive_file(child, dest_dir, fmt, exclude_hidden, dry_run, logger)
        elif child.is_dir():
            archive_large_dir(child, dest_dir, fmt, exclude_hidden, dry_run, logger, size_limit)
        else:
            logger.warning(
                f"{child} is a single file exceeding {size_limit} bytes; archiving as-is"
            )
            make_archive_file(child, dest_dir, fmt, exclude_hidden, dry_run, logger)


def backup_path(src, dest_dir, fmt, exclude_hidden, dry_run, logger, size_limit=1_073_741_824):
    if fmt is None:
        copy_item(src, dest_dir, exclude_hidden, dry_run, logger)
    elif src.is_file():
        make_archive_file(src, dest_dir, fmt, exclude_hidden, dry_run, logger)
    else:
        size = dir_size(src, exclude_hidden)
        if size <= size_limit:
            make_archive_file(src, dest_dir, fmt, exclude_hidden, dry_run, logger)
        else:
            archive_large_dir(src, dest_dir, fmt, exclude_hidden, dry_run, logger, size_limit)


def main():
    logger = setup_logging()
    args = parse_args()
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

    for entry in config["backup"]:
        fmt = entry["format"]
        try:
            paths = expand_paths(entry["path"])
        except FileNotFoundError as e:
            logger.error(str(e))
            continue
        for src in paths:
            logger.info(f"Backing up {src}")
            backup_path(src, dest_dir, fmt, exclude_hidden, dry_run, logger)


if __name__ == "__main__":
    main()
