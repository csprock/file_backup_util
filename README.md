# file-backup-util

A small, dependency-free Python command-line tool for backing up files and
directories to an external destination (e.g. an external hard drive) and
restoring them later. Backups are driven by a JSON config file and produce a
manifest so restores are exact and repeatable.

## Requirements

- Python 3 (standard library only — no third-party packages required)

## Usage

The tool has two modes: `--backup` and `--restore`.

### Backup

```bash
python3 backup_util.py --backup --config backup.json --destination /mnt/external/backups
```

- `--config` (required): path to the JSON config file describing what to back up.
- `--destination` (required): root path for the backup. The actual backup
  directory is `<destination>_<suffix>`, where `<suffix>` defaults to an ISO
  timestamp (e.g. `/mnt/external/backups_2026-06-16T10-30-00`).
- `--suffix`: override the timestamp suffix.
- `--size-limit-mb`: override the archive-splitting size limit (decimal MB,
  e.g. `2000` = 2GB). Defaults to ~1GB if omitted. See
  [Large directories](#large-directories).
- `--dry-run`: log what would happen without copying, archiving, or writing
  anything to disk.

Each run writes a `restore.json` manifest into the backup directory, which
records every item backed up, its format, and where it should be restored to.
This manifest is required for `--restore`.

### Restore

```bash
python3 backup_util.py --restore --backup-dir /mnt/external/backups_2026-06-16T10-30-00
```

- `--backup-dir` (required): the backup directory produced by a previous
  `--backup` run (it must contain `restore.json`).
- `--target`: instead of restoring each item to its original path, recreate
  every item's original path tree beneath this directory. For example, an
  item originally at `/home/user/Documents` gets restored to
  `<target>/home/user/Documents` rather than overwriting
  `/home/user/Documents`. Useful for restoring to a new machine or a
  scratch location for inspection.
- `--dry-run`: log what would be restored without writing anything.

Restoring a directory or file that was copied (uncompressed) preserves
symlinks and Unix permissions and merges into/overwrites any existing content
at the destination. Restoring a `gztar` archive extracts it in place.

### Other flags

- `--version`: print the tool's version and exit.

## Config file format

Config files are JSON:

```json
{
  "backup": [
    {"path": "~/Documents",    "format": "gztar"},
    {"path": "~/Projects/*",   "format": "gztar"},
    {"path": "~/notes.txt",    "format": null}
  ],
  "options": {
    "dry_run":        false,
    "exclude_hidden": true,
    "suffix":         null
  }
}
```

**`backup`** — a list of items to back up:

- `path`: an absolute or `~`-relative path. Glob wildcards are supported;
  each match is backed up as a separate artifact.
- `format`: `"gztar"` to compress as a `.tar.gz` archive, or `null` to copy
  the file/directory as-is. Both preserve symlinks and Unix permissions;
  `gztar` is recommended for directories.

**`options`** (all optional):

- `dry_run`: log what would happen without writing any files. Also settable
  via `--dry-run`; either one enables it.
- `exclude_hidden`: skip dotfiles and dot-directories.
- `suffix`: appended to `--destination` to form the backup directory name.
  Defaults to an ISO timestamp (e.g. `2026-06-16T10-30-00`) if not set here
  or via `--suffix`.

## Large directories

To keep individual archives manageable, directories are compressed as a
single `.tar.gz` only if their contents (respecting `exclude_hidden`) total
1 GB or less by default (override with `--size-limit-mb`, expressed in
decimal MB — e.g. `--size-limit-mb 2000` for a 2GB limit). If a directory
exceeds the limit, the tool descends into its children and archives each one
separately, recursing further into any child that is itself still too large.
A single file larger than the limit is archived as-is with a warning, since
it can't be split further.

## Behavior notes

- Copy and archive failures cause the whole run to fail loudly (no silent
  partial backups) — the exception being a `path` glob with no matches,
  which is logged as an error and skipped so the rest of the config still
  runs.
- Only `gztar` and `null` (copy) formats are supported; anything else in a
  config file is rejected at load time.
- Restoring will overwrite existing files/directories at the destination
  (with a warning logged first).

## Running tests

```bash
python3 -m unittest discover
```
