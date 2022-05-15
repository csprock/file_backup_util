#!/usr/bin/env python3
import argparse
from re import L
import shutil
import logging
from pathlib import Path
from datetime import datetime


logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
handler = logging.StreamHandler()
logger.addHandler(handler)

parser = argparse.ArgumentParser(description="Compress contents of a directory")
parser.add_argument("--input")
parser.add_argument("--output")
parser.add_argument("--suffix", default=datetime.now().isoformat())
parser.add_argument("--exclude_hidden", action="store_true", default=False)
parser.add_argument("--dry-run", action="store_true", default=False)

args = parser.parse_args()

def list_directories(path):
    if args.exclude_hidden:
        logger.info("Excluding hidden files")
        return [Path(x) for x in Path(path).iterdir() if x.is_dir() and not x.match(".*")]
    else: 
        return [Path(x) for x in Path(path).iterdir() if x.is_dir()]

logger.info(f"Dry run: {args.dry_run}")


def main(input, output):
    input = Path(input).resolve()
    output = Path(output).resolve()

    if not output.is_dir():
        raise FileExistsError(f"{str(output)} is not a directory.")

    directories = list_directories(input)

    try:
        directories.remove(output)
        logger.info("Destination path found in compression target, skipping")
    except ValueError:
        pass

    for dir in directories:
        logger.info(dir)

        if not dir.match(".*"):
            base_name = dir.name + "_" + args.suffix
            shutil.make_archive(
                base_name = base_name,
                root_dir = dir.name,
                format='gztar',
                dry_run = args.dry_run,
                logger=logger
            )
            if Path(base_name + ".tar.gz").exists():
                shutil.move(src=base_name + ".tar.gz", dst=args.output)
    

if __name__ == "__main__":
    main(args.input, args.output)