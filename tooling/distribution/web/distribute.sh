#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
exec uv run --python 3.14.2 --no-python-downloads --no-project --with packaging==25.0 python "$SCRIPT_DIR/distribute.py" "$@"
