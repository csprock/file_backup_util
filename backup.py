#!/usr/bin/env python3
import argparse
from genericpath import exists
from re import L
import shutil
import logging
from pathlib import Path
from datetime import datetime
from configparser import ConfigParser


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(level=logging.DEBUG)
handler = logging.StreamHandler()
LOGGER.addHandler(handler)

parser = argparse.ArgumentParser(description="Compress contents of a directory")
parser.add_argument("--config")
parser.add_argument("--mode", default=751)

args = parser.parse_args()

config = ConfigParser()
config.read(args.config)

root = Path(args.config).parent

LOGGER.info(f"Dry run: {config['Options']['dry_run']}")
LOGGER.info(f"Backing up files in {str(root)} using filemode {args.mode}")

try:
    config['Options']['suffix']
except KeyError:
    config['Options']['suffix'] = default=datetime.now().isoformat()

def _bool(value):
    if value == 'True':
        return True
    if value == 'False':
        return False
    else:
        raise TypeError(f"value must be str True or False, found {value} instead")

EXTENTION_MAP = {
    'gztar':'.tar.gz',
    'zip':'.zip'
}

def main():

    output = Path(config['Options']['destination']).resolve() #+ "_" + config['Options']['suffix'])).resolve()
    output.mkdir(mode=args.mode, parents=True, exist_ok=True)


    for file in config['Files']:

        format = config['Files'][file]

        base_name = root / Path(file)

        LOGGER.info(f"Attempting to archive {file} using {format}")
        LOGGER.info(f"Saving archive as {base_name}")

        shutil.make_archive(
            base_name = str(base_name),
            root_dir = str(base_name),
            format=format,
            dry_run = _bool(config['Options']['dry_run']),
            logger=LOGGER
        )
        if not _bool(config['Options']['dry_run']):
            shutil.copy(src=str(base_name) + EXTENTION_MAP[format], dst=output)
    

if __name__ == "__main__":
    main()