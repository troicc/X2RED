#!/usr/bin/env sh
set -eu

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
python -m pip install --no-build-isolation -e .
exec x2red serve --host 127.0.0.1 --port 8787 "$@"
