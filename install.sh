#!/usr/bin/env bash
# Installs backup_util by symlinking backup_util.py into ~/.local/bin,
# so the command always runs the version checked out in this clone.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_SCRIPT="$SCRIPT_DIR/backup_util.py"
INSTALL_DIR="$HOME/.local/bin"
LINK_PATH="$INSTALL_DIR/backup_util"

if [[ ! -f "$TARGET_SCRIPT" ]]; then
    echo "Error: backup_util.py not found at $TARGET_SCRIPT" >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Warning: python3 not found on PATH. backup_util requires Python 3 to run." >&2
fi

chmod +x "$TARGET_SCRIPT"
mkdir -p "$INSTALL_DIR"

if [[ -L "$LINK_PATH" && "$(readlink "$LINK_PATH")" == "$TARGET_SCRIPT" ]]; then
    echo "Already installed: $LINK_PATH -> $TARGET_SCRIPT"
    exit 0
fi

if [[ -e "$LINK_PATH" || -L "$LINK_PATH" ]]; then
    echo "Error: $LINK_PATH already exists and is not a symlink to $TARGET_SCRIPT" >&2
    echo "Remove or back it up manually, then re-run this script." >&2
    exit 1
fi

ln -s "$TARGET_SCRIPT" "$LINK_PATH"
echo "Installed: $LINK_PATH -> $TARGET_SCRIPT"

case ":$PATH:" in
    *":$INSTALL_DIR:"*)
        ;;
    *)
        echo "Warning: $INSTALL_DIR is not on your PATH."
        echo "Add this to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
        echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
        ;;
esac
