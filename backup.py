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

args = parser.parse_args()

config = ConfigParser()
config.read(args.config)

root = Path(args.config).parent

LOGGER.info(f"Dry run: {config['Options']['dry_run']}")
LOGGER.info(f"Backing up files in {str(root)}.")

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



def main(input):

    input = Path(input).resolve()
    output = (Path(config['Options']['destination'] + "_" + config['Options']['suffix'])).resolve()

    

    Path.mkdir(output, parents=True, exist_ok=False)


    for file in config['Files']:

        filemode = config['Files'][file]

        dir = root / Path(file)

        LOGGER.info(f"Attempting to archive {file} using {filemode}")

        if not dir.match(".*"):
            base_name = Path(dir.name).resolve()
            LOGGER.info(f"Saving archive as {base_name}")
            shutil.make_archive(
                base_name = base_name.name,
                root_dir = dir.name,
                format='gztar',
                dry_run = _bool(config['Options']['dry_run']),
                logger=LOGGER
            )
            if not _bool(config['Options']['dry_run']):
                shutil.move(src=base_name.name + ".tar.gz", dst=output)
    

if __name__ == "__main__":
    main(Path.cwd())