#!/usr/bin/env bash

set -euo pipefail

# Build a native Apple Silicon Desktop Editors app from the coordinated
# ONLYOFFICE 9.4 source line. Run on an ARM64 Mac with Xcode installed.
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
UPSTREAM_BRANCH=${UPSTREAM_BRANCH:-release/v9.4.0}

cd "$ROOT_DIR"
python3 ./configure.py \
  --module desktop \
  --platform mac_arm64 \
  --branch "$UPSTREAM_BRANCH" \
  --git-protocol https \
  --update 1 \
  --clean 1
python3 ./make.py
