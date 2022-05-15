#!/usr/bin/env python3
import argparse
import shutil
import logging
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)

parser = argparse.ArgumentParser(description="Compress contents of a directory")
parser.add_argument("--input")
parser.add_argument("--exclude_hidden", action="store_true", default=False)

args = parser.parse_args()

def list_directories(path):
    if args.exclude_hidden:
        return [Path(x) for x in Path(path).iterdir() if x.is_dir() and not x.match(".*")]
    else: 
        return [Path(x) for x in Path(path).iterdir() if x.is_dir()]



def main(input, output=None):
    input = Path(input).expanduser()
    directories = list_directories(input)

    for dir in directories:
        logging.debug(dir)

        if not dir.match(".*"):
            shutil.make_archive(
                base_name = dir.name,
                format='gztar',
                dry_run = True
            )

    return directories
    

if __name__ == "__main__":
    main(args.input)