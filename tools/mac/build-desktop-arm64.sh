#!/usr/bin/env bash

set -euo pipefail

# Build a native Apple Silicon Desktop Editors app from the coordinated
# ONLYOFFICE 9.4 source line. Run on an ARM64 Mac with Xcode installed.
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
UPSTREAM_BRANCH=${UPSTREAM_BRANCH:-release/v9.4.0}
LOCK_FILE=${LOCK_FILE:-"$ROOT_DIR/locks/onlyoffice-desktop-9.4.0.lock"}

cd "$ROOT_DIR"
while read -r repository commit; do
  [ -z "$repository" ] && continue
  case "$repository" in \#*) continue ;; esac
  actual=$(git -C "$ROOT_DIR/../$repository" rev-parse HEAD)
  if [ "$actual" != "$commit" ]; then
    echo "Lock mismatch for $repository: expected $commit, got $actual" >&2
    exit 1
  fi
done < "$LOCK_FILE"

python3 ./configure.py \
  --module desktop \
  --platform mac_arm64 \
  --branch "$UPSTREAM_BRANCH" \
  --git-protocol https \
  --update 0 \
  --clean 1
python3 ./make.py
