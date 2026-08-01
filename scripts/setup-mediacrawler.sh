#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
HOST_PYTHON=${1:-"$REPO_ROOT/.venv/bin/python"}
cd "$REPO_ROOT"

# Resolve the same pydantic settings used by the running application. This
# honors .env as well as exported X2RED_* variables without sourcing shell code.
eval "$("$HOST_PYTHON" - <<'PY'
import shlex
from app.core.config import Settings

settings = Settings()
print("MEDIACRAWLER_REVISION=" + shlex.quote(settings.mediacrawler_revision))
print(
    "MEDIACRAWLER_ROOT="
    + shlex.quote(str(settings.mediacrawler_root.expanduser().resolve()))
)
PY
)"

MARKER="$MEDIACRAWLER_ROOT/.x2red-revision"
INSTALL_SCHEMA="uv-no-install-project-v1"
EXPECTED_MARKER="$MEDIACRAWLER_REVISION|$INSTALL_SCHEMA"
mkdir -p "$(dirname -- "$MEDIACRAWLER_ROOT")"

if [ ! -d "$MEDIACRAWLER_ROOT/.git" ]; then
  echo "Cloning MediaCrawler at pinned revision $MEDIACRAWLER_REVISION"
  git clone --filter=blob:none https://github.com/NanmiCoder/MediaCrawler.git "$MEDIACRAWLER_ROOT"
fi

CURRENT_REVISION=$(git -C "$MEDIACRAWLER_ROOT" rev-parse HEAD 2>/dev/null || true)
if [ "$CURRENT_REVISION" != "$MEDIACRAWLER_REVISION" ]; then
  if ! git -C "$MEDIACRAWLER_ROOT" diff --quiet || ! git -C "$MEDIACRAWLER_ROOT" diff --cached --quiet; then
    echo "MediaCrawler vendor checkout has local changes; refusing to overwrite it." >&2
    exit 1
  fi
  git -C "$MEDIACRAWLER_ROOT" fetch --depth=1 origin "$MEDIACRAWLER_REVISION"
  git -C "$MEDIACRAWLER_ROOT" checkout --detach "$MEDIACRAWLER_REVISION"
fi

# MediaCrawler documents uv as its supported installer. Its pinned pyproject
# contains a non-standard `project.author` field that recent setuptools rejects
# during `pip install -e`. `--no-install-project` installs the locked runtime
# dependencies without building MediaCrawler itself; X2RED runs its source tree
# directly through scripts/run-mediacrawler.py.
if command -v uv >/dev/null 2>&1; then
  UV_BIN=$(command -v uv)
elif [ -x "$REPO_ROOT/.venv/bin/uv" ]; then
  UV_BIN="$REPO_ROOT/.venv/bin/uv"
elif [ -x "$REPO_ROOT/.venv/Scripts/uv.exe" ]; then
  UV_BIN="$REPO_ROOT/.venv/Scripts/uv.exe"
else
  echo "Installing uv for MediaCrawler dependency synchronization"
  "$HOST_PYTHON" -m pip install "uv>=0.8,<1"
  if [ -x "$REPO_ROOT/.venv/bin/uv" ]; then
    UV_BIN="$REPO_ROOT/.venv/bin/uv"
  elif [ -x "$REPO_ROOT/.venv/Scripts/uv.exe" ]; then
    UV_BIN="$REPO_ROOT/.venv/Scripts/uv.exe"
  else
    echo "uv was installed but its executable could not be located." >&2
    exit 1
  fi
fi

INSTALLED_MARKER=$(cat "$MARKER" 2>/dev/null || true)
if [ "$INSTALLED_MARKER" != "$EXPECTED_MARKER" ]; then
  echo "Synchronizing MediaCrawler dependencies from uv.lock"
  "$UV_BIN" sync \
    --project "$MEDIACRAWLER_ROOT" \
    --frozen \
    --no-install-project \
    --python "$HOST_PYTHON"
  printf '%s\n' "$EXPECTED_MARKER" > "$MARKER"
fi

if [ -x "$MEDIACRAWLER_ROOT/.venv/bin/python" ]; then
  CRAWLER_PYTHON="$MEDIACRAWLER_ROOT/.venv/bin/python"
elif [ -x "$MEDIACRAWLER_ROOT/.venv/Scripts/python.exe" ]; then
  CRAWLER_PYTHON="$MEDIACRAWLER_ROOT/.venv/Scripts/python.exe"
else
  echo "MediaCrawler environment was not created successfully." >&2
  exit 1
fi

"$CRAWLER_PYTHON" -c 'import playwright, httpx, typer' >/dev/null

echo "MediaCrawler ready: $MEDIACRAWLER_ROOT ($MEDIACRAWLER_REVISION)"
