#!/usr/bin/env sh
set -eu

if [ "$#" -lt 1 ]; then
  echo "usage: $0 /path/to/model_server [python-executable]" >&2
  exit 2
fi

MODEL_SERVER_PATH=$1
PYTHON_EXE=${2:-}

if [ -z "$PYTHON_EXE" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_EXE=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON_EXE=python
  else
    echo "Python 3 is required (python3 or python on PATH)." >&2
    exit 1
  fi
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$PYTHON_EXE" "$SCRIPT_DIR/apply_backport.py" --model-server "$MODEL_SERVER_PATH"
