#!/usr/bin/env bash

set -euo pipefail

# Build a native Linux ARM64 Desktop Editors artifact from the coordinated
# ONLYOFFICE 9.4 source line. Run this on an ARM64 Linux Docker host.
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
IMAGE_NAME=${IMAGE_NAME:-ration-docs-desktop-builder:9.4-arm64}
OUTPUT_DIR=${OUTPUT_DIR:-"$ROOT_DIR/out"}
UPSTREAM_BRANCH=${UPSTREAM_BRANCH:-release/v9.4.0}

mkdir -p "$OUTPUT_DIR"

docker build --platform linux/arm64 --tag "$IMAGE_NAME" "$ROOT_DIR"
docker run --rm --platform linux/arm64 \
  --volume "$OUTPUT_DIR:/build_tools/out" \
  "$IMAGE_NAME" \
  sh -lc "cd /build_tools/tools/linux && python3 ./automate.py desktop --branch=$UPSTREAM_BRANCH"
