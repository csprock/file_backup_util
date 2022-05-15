#!/usr/bin/env python3
import argparse
import shutil
import logging
from pathlib import Path


logger = logging.getLogger(name=__name__)
logger.setLevel(level=logging.DEBUG)
handler = logging.StreamHandler()
logger.addHandler(handler)

parser = argparse.ArgumentParser(description="Compress contents of a directory")
parser.add_argument("--input")
parser.add_argument("--output", default=None)
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

def main(input, output=None):
    input = Path(input).expanduser()
    directories = list_directories(input)

    if args.output:
        base_name = args.output
    else:
        base_name = args.input

    for dir in directories:
        logger.info(dir)

        if not dir.match(".*"):
            shutil.make_archive(
                base_name = base_name,
                root_dir = dir.name,
                format='gztar',
                dry_run = args.dry_run,
                logger=logger
            )
    

if __name__ == "__main__":
    main(args.input)