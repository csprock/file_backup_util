#!/usr/bin/env python3
import argparse
from genericpath import exists
from re import L
import shutil
import logging
from pathlib import Path
from datetime import datetime
import yaml

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
parser.add_argument("--mode", default=511)

args = parser.parse_args()


def load_config_file(path):

    with open(path, mode='rt') as file:
        config = yaml.safe_load(file)

    for file, params in config['files'].items():
        try:
            if params['format'] is not None:
                assert params['format'] in EXTENTION_MAP
        except AssertionError:
            raise AssertionError(f"{file} has an invalid format {params['format']}")

    if config['options']['suffix'] is None:
        config['options']['suffix'] = datetime.now().isoformat().replace(":", "-")

    LOGGER.info(f"Dry run: {(config['options']['dry_run'])}")

    return config

config = load_config_file(args.config)


def main():

    src_root = Path(args.config).parent
    dest_dir = Path(config['options']['destination'] + "_" + config['options']['suffix']).resolve()
    LOGGER.info(f"Making directory {dest_dir}")
    dest_dir.mkdir(mode=args.mode, parents=True, exist_ok=True)

    for file, params in config['files'].items():

        format = params['format']
        src_name = src_root / Path(file)
        LOGGER.info(f"Backing up {src_name}")

        if format is None:
            pass
            dest_name = dest_dir / Path(file)
            LOGGER.info(f"Copying {src_name} without compression to {dest_name}")
            if not config['options']['dry_run']:
                d = shutil.copytree(str(src_name), str(dest_name), dirs_exist_ok=True)
                LOGGER.info(d)
        else:

            LOGGER.info(f"Using {format} compression")

            shutil.make_archive(
                base_name = str(src_name),
                root_dir = str(src_name),
                format=format,
                dry_run = config['options']['dry_run'],
                logger=LOGGER
            )
            if not config['options']['dry_run']:
                archive_name = str(src_name) + EXTENTION_MAP[format]
                LOGGER.info(f"Attempting to move {archive_name} to {dest_dir}")
                dest = shutil.move(src=archive_name, dst=str(dest_dir))

    
if __name__ == "__main__":
    main()