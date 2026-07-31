#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$REPO_ROOT"

if [ -n "${X2RED_PYTHON:-}" ]; then
  PYTHON_BIN=$X2RED_PYTHON
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN=python3.12
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
else
  echo "X2RED requires Python 3.12 or newer." >&2
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit(f"X2RED requires Python 3.12 or newer; found {sys.version.split()[0]}")
print(f"Using Python {sys.version.split()[0]}")
PY

if [ -d .venv ] && ! .venv/bin/python -c 'import sys; raise SystemExit(sys.version_info < (3, 12))' >/dev/null 2>&1; then
  echo "Existing .venv is invalid; recreating it."
  rm -rf .venv
fi
if [ ! -x .venv/bin/python ]; then
  "$PYTHON_BIN" -m venv .venv
fi

VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
"$VENV_PYTHON" -m ensurepip --upgrade
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install -e '.[publisher]'

if [ "${X2RED_SKIP_BROWSER_INSTALL:-0}" != "1" ] && [ ! -f .venv/.x2red-playwright-ready ]; then
  echo "Preparing Chromium for HTML/CSS card rendering and Xiaohongshu preview…"
  "$VENV_PYTHON" -m playwright install chromium
  touch .venv/.x2red-playwright-ready
fi

exec "$VENV_PYTHON" -m app.cli serve --host 127.0.0.1 --port 8787 "$@"
