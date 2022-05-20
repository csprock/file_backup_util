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

root = Path(args.config).parent

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

logger.info(f"Dry run: {config['Options']['dry_run']}")


def main(input):

    input = Path(input).resolve()
    output = Path(config['Options']['destination']).resolve()

    if not output.exists():
        raise FileExistsError(f"{str(output)} does not exist.")

    for file in config['Files']:

        filemode = config['Files'][file]

        dir = root / Path(file)

        logger.info(f"Attempting to archive {file} using {filemode}")

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