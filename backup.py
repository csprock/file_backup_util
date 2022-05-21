#!/usr/bin/env python3
import argparse
from genericpath import exists
from re import L
import shutil
import logging
from pathlib import Path
from datetime import datetime
from configparser import ConfigParser

EXTENTION_MAP = {
    'gztar':'.tar.gz',
    'zip':'.zip'
}

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(level=logging.DEBUG)
handler = logging.StreamHandler()
LOGGER.addHandler(handler)

parser = argparse.ArgumentParser(description="Compress contents of a directory")
parser.add_argument("--config")

args = parser.parse_args()

config = ConfigParser()
config.read(args.config)

src_root = Path(args.config).parent


def _bool(value):
    if value == 'True':
        return True
    if value == 'False':
        return False
    else:
        raise TypeError(f"value must be str True or False, found {value} instead")
        
try:
    config['Options']['suffix']
except KeyError:
    config['Options']['suffix'] = default=datetime.now().isoformat()

LOGGER.info(f"Dry run: {(config['Options']['dry_run'])}")

def main():

    dest_dir = Path(config['Options']['destination'] + "_" + config['Options']['suffix']).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info(f"Making directory {dest_dir}")


    for file in config['Files']:

        format = config['Files'][file]
        src_name = src_root / Path(file)
        LOGGER.info(f"Backing up {src_name}")

        if format == 'None':
            pass
            dest_name = dest_dir / Path(file)
            LOGGER.info(f"Copying {src_name} without compression to {dest_name}")
            if not _bool(config['Options']['dry_run']):
                d = shutil.copytree(str(src_name), str(dest_name), dirs_exist_ok=True)
                LOGGER.info(d)
        else:

            LOGGER.info(f"Using {format} compression")

            shutil.make_archive(
                base_name = str(src_name),
                root_dir = str(src_name),
                format=format,
                dry_run = _bool(config['Options']['dry_run']),
                logger=LOGGER
            )
            if not _bool(config['Options']['dry_run']):
                archive_name = str(src_name) + EXTENTION_MAP[format]
                LOGGER.info(f"Attempting to move {archive_name} to {dest_dir}")
                dest = shutil.move(src=archive_name, dst=str(dest_dir))

    
if __name__ == "__main__":
    main()