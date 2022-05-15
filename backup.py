#!/usr/bin/env python3
import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description="Compress contents of a directory")
parser.add_argument("--input")

args = parser.parse_args()

def list_directories(path):
    return [Path(x) for x in Path(path).iterdir() if Path.is_dir(x)]


def main(input, output=None):
    directories = list_directories(input)
    return directories
    

if __name__ == "__main__":
    print(main(args.input))