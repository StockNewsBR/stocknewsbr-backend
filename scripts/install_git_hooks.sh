#!/usr/bin/env bash
# Install local Git hooks managed by this repository.
#
# Sets `core.hooksPath` to .githooks and ensures the hooks are executable.
# Safe to run multiple times. Fails fast if not run from the repo root.

set -euo pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[hooks] ERROR: not inside a git work tree." >&2
  exit 1
fi

repo_root=$(git rev-parse --show-toplevel)
hooks_dir="$repo_root/.githooks"

if [ ! -d "$hooks_dir" ]; then
  echo "[hooks] ERROR: $hooks_dir not found." >&2
  exit 1
fi

git config core.hooksPath .githooks

chmod +x "$hooks_dir"/* 2>/dev/null || true

echo "[hooks] OK: core.hooksPath=$(git config core.hooksPath)"
echo "[hooks] OK: hooks installed at $hooks_dir"
ls -l "$hooks_dir"
