#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
HOST_PYTHON=${1:-"$REPO_ROOT/.venv/bin/python"}
MEDIACRAWLER_REVISION=${X2RED_MEDIACRAWLER_REVISION:-1779dde9725f6b7ef42e29022c0054b3e678f1af}
MEDIACRAWLER_ROOT=${X2RED_MEDIACRAWLER_ROOT:-"$REPO_ROOT/.vendor/MediaCrawler"}
MARKER="$MEDIACRAWLER_ROOT/.x2red-revision"

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

if [ -x "$MEDIACRAWLER_ROOT/.venv/bin/python" ]; then
  CRAWLER_PYTHON="$MEDIACRAWLER_ROOT/.venv/bin/python"
elif [ -x "$MEDIACRAWLER_ROOT/.venv/Scripts/python.exe" ]; then
  CRAWLER_PYTHON="$MEDIACRAWLER_ROOT/.venv/Scripts/python.exe"
else
  "$HOST_PYTHON" -m venv "$MEDIACRAWLER_ROOT/.venv"
  if [ -x "$MEDIACRAWLER_ROOT/.venv/bin/python" ]; then
    CRAWLER_PYTHON="$MEDIACRAWLER_ROOT/.venv/bin/python"
  else
    CRAWLER_PYTHON="$MEDIACRAWLER_ROOT/.venv/Scripts/python.exe"
  fi
fi

INSTALLED_REVISION=$(cat "$MARKER" 2>/dev/null || true)
if [ "$INSTALLED_REVISION" != "$MEDIACRAWLER_REVISION" ]; then
  "$CRAWLER_PYTHON" -m ensurepip --upgrade
  "$CRAWLER_PYTHON" -m pip install --upgrade pip setuptools wheel
  "$CRAWLER_PYTHON" -m pip install -e "$MEDIACRAWLER_ROOT"
  printf '%s\n' "$MEDIACRAWLER_REVISION" > "$MARKER"
fi

echo "MediaCrawler ready: $MEDIACRAWLER_ROOT ($MEDIACRAWLER_REVISION)"
