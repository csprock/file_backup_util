#!/usr/bin/env python3
import argparse
from re import L
import shutil
import logging
from pathlib import Path
from datetime import datetime
from configparser import ConfigParser


logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
handler = logging.StreamHandler()
logger.addHandler(handler)

parser = argparse.ArgumentParser(description="Compress contents of a directory")
parser.add_argument("--config")

args = parser.parse_args()

config = ConfigParser()
config.read(args.config)

try:
    config['Options']['suffix']
except KeyError:
    config['Options']['suffix'] = default=datetime.now().isoformat()

def parse_list(text_list):
    file_list = text_list.replace('[', '').replace(']', '').split()
    file_list = [f.strip() for f in file_list]
    return file_list

def _bool(value):
    if value == 'True':
        return True
    if value == 'False':
        return False
    else:
        raise TypeError(f"value must be str True or False, found {value} instead")

def list_directories(path):
    if bool(config['Options']['exclude_hidden']):
        logger.info("Excluding hidden files")
        return [Path(x) for x in Path(path).iterdir() if x.is_dir() and not x.match(".*")]
    else: 
        return [Path(x) for x in Path(path).iterdir() if x.is_dir()]

logger.info(f"Dry run: {config['Options']['dry_run']}")


def main(input):
    input = Path(input).resolve()
    output = Path(config['Options']['destination']).resolve()

    if not output.is_dir():
        raise FileExistsError(f"{str(output)} is not a directory.")

    directories = list_directories(input)

    try:
        directories.remove(output)
        logger.info("Destination path found in compression target, skipping")
    except ValueError:
        pass

    for dir in directories:
        logger.info(f"Attempting to archive {dir}")

        if not dir.match(".*"):
            base_name = Path(dir.name + "_" + config['Options']['suffix']).resolve()
            logger.info(f"Saving archive as {base_name}")
            shutil.make_archive(
                base_name = base_name.name,
                root_dir = dir.name,
                format='gztar',
                dry_run = _bool(config['Options']['dry_run']),
                logger=logger
            )
            if not _bool(config['Options']['dry_run']):
                shutil.move(src=base_name.name + ".tar.gz", dst=output)
    

if __name__ == "__main__":
    main(Path.cwd())